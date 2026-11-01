"""Removing maintenance plans: PM plans (and PdM rounds), PdM measurement points and lubrication points.

One rule for all of them, so nobody has to choose:
  * never used (no work order, no reading, no lubrication done) -> deleted completely;
  * has history -> deactivated: nothing is generated from it any more, its waiting occurrences / pending tasks are
    cancelled, and its code gets a "~OFF" suffix so the same code can be imported again. Its work orders,
    readings and history stay as they were.

`replace_for_import` uses the same rule to clear the plans of the equipment in an import file before the file is
imported ("Replace existing plans")."""

import uuid
from typing import Any

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.enums import OPEN_WO_STATUSES, LubeTaskStatus, OccurrenceStatus, WOType
from app.models.lubrication import LubeTask, LubricationPoint
from app.models.pdm import ConditionReading, MeasurementPoint
from app.models.pm import JobPlan, PMOccurrence, PMPlan
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services.common import audit
from app.services.imports import _s

DELETED, DEACTIVATED = "deleted", "deactivated"
WAITING_OCC = [
    OccurrenceStatus.SCHEDULED,
    OccurrenceStatus.DEFERRED,
    OccurrenceStatus.DEFERRAL_REQUESTED,
    OccurrenceStatus.CANCELLATION_REQUESTED,
]


def _retired_code(db: Session, model: Any, plant_id: uuid.UUID, code: str, max_len: int) -> str:
    """CODE~OFF, CODE~OFF2, ... : a free code within the column length, so the original code can be reused."""
    n = 1
    while True:
        tag = "~OFF" if n == 1 else f"~OFF{n}"
        cand = code[: max_len - len(tag)] + tag
        if not db.execute(select(model.id).where(model.plant_id == plant_id, func.upper(model.code) == cand.upper())).first():
            return cand
        n += 1


def _open_wos(db: Session, wo_ids: list[uuid.UUID]) -> int:
    if not wo_ids:
        return 0
    return db.execute(select(func.count()).where(WorkOrder.id.in_(wo_ids), WorkOrder.status.in_(OPEN_WO_STATUSES))).scalar_one()


# ---------- PM plans (also the PdM rounds, which are PM plans of type predictive) ----------
def remove_pm_plan(db: Session, plan: PMPlan) -> tuple[str, int]:
    """Returns (deleted | deactivated, open work orders the plan still has)."""
    occ_ids = select(PMOccurrence.id).where(PMOccurrence.pm_plan_id == plan.id)
    wo_ids = list(db.execute(select(WorkOrder.id).where(WorkOrder.pm_occurrence_id.in_(occ_ids))).scalars())
    used = (
        bool(wo_ids)
        or db.execute(
            select(
                exists().where(
                    PMOccurrence.pm_plan_id == plan.id,
                    or_(PMOccurrence.work_order_id.is_not(None), PMOccurrence.status == OccurrenceStatus.COMPLETED),
                )
            )
        ).scalar_one()
    )
    jp = db.get(JobPlan, plan.job_plan_id)
    shared_jp = db.execute(select(exists().where(PMPlan.job_plan_id == plan.job_plan_id, PMPlan.id != plan.id))).scalar_one()
    if not used:
        db.execute(delete(PMOccurrence).where(PMOccurrence.pm_plan_id == plan.id))
        db.delete(plan)
        db.flush()
        if jp is not None and not shared_jp:
            db.delete(jp)
            db.flush()
        return DELETED, 0
    db.execute(
        update(PMOccurrence)
        .where(PMOccurrence.pm_plan_id == plan.id, PMOccurrence.work_order_id.is_(None), PMOccurrence.status.in_(WAITING_OCC))
        .values(status=OccurrenceStatus.CANCELLED)
    )
    if "~OFF" not in plan.code.upper():
        plan.code = _retired_code(db, PMPlan, plan.plant_id, plan.code, 40)
    plan.is_active = False
    if jp is not None and not shared_jp and "~OFF" not in jp.code.upper():
        jp.code = _retired_code(db, JobPlan, jp.plant_id, jp.code, 40)
        jp.is_active = False
    db.flush()
    return DEACTIVATED, _open_wos(db, wo_ids)


# ---------- PdM measurement points ----------
def remove_pdm_point(db: Session, point: MeasurementPoint) -> tuple[str, int]:
    used = db.execute(select(exists().where(ConditionReading.point_id == point.id))).scalar_one()
    if not used:
        db.delete(point)
        db.flush()
        return DELETED, 0
    point.is_active = False
    point.auto_create_wo = False
    point.external_tag = None  # a gateway must not keep feeding a retired point
    if "~OFF" not in point.code.upper():
        point.code = _retired_code(db, MeasurementPoint, point.plant_id, point.code, 60)
    db.flush()
    return DEACTIVATED, 0


# ---------- lubrication points ----------
def remove_lube_point(db: Session, point: LubricationPoint) -> tuple[str, int]:
    used = db.execute(
        select(
            exists().where(
                LubeTask.point_id == point.id, or_(LubeTask.status != LubeTaskStatus.PENDING, LubeTask.work_order_id.is_not(None))
            )
        )
    ).scalar_one()
    if not used:
        db.delete(point)
        db.flush()
        return DELETED, 0
    db.execute(
        delete(LubeTask).where(LubeTask.point_id == point.id, LubeTask.status == LubeTaskStatus.PENDING, LubeTask.work_order_id.is_(None))
    )
    wo_ids = [w for w in db.execute(select(LubeTask.work_order_id).where(LubeTask.point_id == point.id)).scalars() if w]
    point.is_active = False
    point.next_due_date = None
    if "~OFF" not in point.code.upper():
        point.code = _retired_code(db, LubricationPoint, point.plant_id, point.code, 40)
    db.flush()
    return DEACTIVATED, _open_wos(db, list(set(wo_ids)))


REMOVERS: dict[str, tuple[Any, Any]] = {
    "pm_plan": (PMPlan, remove_pm_plan),
    "pdm_point": (MeasurementPoint, remove_pdm_point),
    "lube_point": (LubricationPoint, remove_lube_point),
}


def remove_many(db: Session, plant: Plant, kind: str, ids: list[uuid.UUID], user_id: uuid.UUID, dept_ok: Any) -> dict[str, Any]:
    """Remove the listed records of one kind. `dept_ok(department_id)` limits a department-restricted user;
    records of other plants / departments are skipped as not found."""
    model, remover = REMOVERS[kind]
    out: dict[str, Any] = {"deleted": 0, "deactivated": 0, "not_found": 0, "open_work_orders": 0, "codes": []}
    rows = db.execute(
        select(model, Asset.department_id).join(Asset, Asset.id == model.asset_id).where(model.plant_id == plant.id, model.id.in_(ids))
    ).all()
    out["not_found"] = len(set(ids)) - len(rows)
    for rec, dept_id in rows:
        if not dept_ok(dept_id):
            out["not_found"] += 1
            continue
        code = rec.code
        result, open_wos = remover(db, rec)
        out[result] += 1
        out["open_work_orders"] += open_wos
        out["codes"].append(code)
    audit(
        db,
        f"{kind}.remove",
        user_id=user_id,
        plant_id=plant.id,
        data={k: v for k, v in out.items() if k != "codes"} | {"codes": out["codes"][:200]},
    )
    return out


# ---------- "Replace existing plans" on import ----------
def replace_for_import(db: Session, plant: Plant, kind: str, rows: list[dict], user_id: uuid.UUID, dept_ok: Any) -> dict[str, Any]:
    """Before importing `kind` (pm_plans | pdm_plans | lube_plans), remove the current plans of every asset named in
    the file (column asset_code). PM import replaces the asset's PM plans (not its PdM rounds); PdM import replaces
    the asset's measurement points and PdM rounds; lubrication import replaces the asset's lubrication points."""
    codes = {(_s(r.get("asset_code")) or "").upper() for r in rows} - {""}
    if not codes:
        return {"assets": 0, "deleted": 0, "deactivated": 0, "open_work_orders": 0}
    assets = db.execute(select(Asset.id, Asset.department_id).where(Asset.plant_id == plant.id, func.upper(Asset.code).in_(codes))).all()
    asset_ids = [a for a, d in assets if dept_ok(d)]
    total = {"assets": len(asset_ids), "deleted": 0, "deactivated": 0, "open_work_orders": 0}

    def run(k: str, ids: list[uuid.UUID]) -> None:
        if ids:
            r = remove_many(db, plant, k, ids, user_id, dept_ok)
            for f in ("deleted", "deactivated", "open_work_orders"):
                total[f] += r[f]

    if not asset_ids:
        return total
    if kind in ("pm_plans", "pdm_plans"):
        is_pdm = PMPlan.wo_type == WOType.PREDICTIVE
        q = select(PMPlan.id).where(PMPlan.plant_id == plant.id, PMPlan.asset_id.in_(asset_ids), PMPlan.is_active.is_(True))
        run("pm_plan", list(db.execute(q.where(is_pdm if kind == "pdm_plans" else ~is_pdm)).scalars()))
    if kind == "pdm_plans":
        q = select(MeasurementPoint.id).where(
            MeasurementPoint.plant_id == plant.id, MeasurementPoint.asset_id.in_(asset_ids), MeasurementPoint.is_active.is_(True)
        )
        run("pdm_point", list(db.execute(q).scalars()))
    if kind == "lube_plans":
        q = select(LubricationPoint.id).where(
            LubricationPoint.plant_id == plant.id, LubricationPoint.asset_id.in_(asset_ids), LubricationPoint.is_active.is_(True)
        )
        run("lube_point", list(db.execute(q).scalars()))
    return total
