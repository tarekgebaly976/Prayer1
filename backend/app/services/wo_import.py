"""Work-order plan import: a planner or engineer uploads the work for their team (one row per work order).

Used with Manual work-order generation (the team plans its own PM / PdM work) and for any planned job list.
A row with `pm_plan_code` releases that plan's next waiting occurrence (so PM compliance keeps counting it);
other rows create new work orders. Rows outside the user's departments are refused. Preview validates; commit is
all-or-nothing, like the other imports."""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Ctx
from app.core.errors import DomainError
from app.models.assets import Asset
from app.models.enums import OccurrenceStatus, Priority, WOType
from app.models.identity import Membership, User
from app.models.pm import PMOccurrence, PMPlan
from app.models.tenancy import Plant
from app.services.common import audit
from app.services.imports import _date, _num, _s

TYPE_ALIASES = {"pm": "preventive", "pdm": "predictive", "cm": "corrective", "breakdown": "emergency", "lube": "lubrication"}
PRIO_ALIASES = {"high": "P2", "medium": "P3", "low": "P4", "emergency": "P1", "urgent": "P1"}


def _people(db: Session, plant: Plant) -> dict[str, uuid.UUID]:
    """Active members by e-mail and by employee number (lower case)."""
    out: dict[str, uuid.UUID] = {}
    rows = db.execute(
        select(User).join(Membership, Membership.user_id == User.id).where(Membership.plant_id == plant.id, Membership.is_active.is_(True))
    ).scalars()
    for u in rows:
        out[u.email.lower()] = u.id
        if u.employee_no:
            out[u.employee_no.strip().lower()] = u.id
    return out


def validate_work_orders(db: Session, plant: Plant, rows: list[dict], ctx: Ctx | None = None) -> dict:
    assets = {a.code.upper(): a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    plans = {p.code.upper(): p for p in db.execute(select(PMPlan).where(PMPlan.plant_id == plant.id)).scalars()}
    people = _people(db, plant)
    used_plans: dict[str, int] = {}
    out: list[dict] = []
    for i, r in enumerate(rows, start=2):
        errs: list[str] = []
        pcode = (_s(r.get("pm_plan_code")) or "").upper()
        plan = plans.get(pcode) if pcode else None
        if pcode and plan is None:
            errs.append(f"PM plan {pcode} not found")
        acode = (_s(r.get("asset_code")) or "").upper()
        asset = assets.get(acode) if acode else None
        if plan is not None and asset is None:
            asset = db.get(Asset, plan.asset_id)
        if asset is None:
            errs.append(f"asset {acode or '(blank)'} not found")
        elif ctx is not None and not ctx.dept_ok(asset.department_id):
            errs.append(f"asset {asset.code} is not in your departments")
        title = _s(r.get("title")) or (f"{plan.code} {plan.name}" if plan else None)
        if not title:
            errs.append("title is required")
        raw_type = (_s(r.get("type")) or ("" if plan else "corrective")).lower()
        wtype: WOType | None = plan.wo_type if plan and not raw_type else None
        if raw_type:
            try:
                wtype = WOType(TYPE_ALIASES.get(raw_type, raw_type))
            except ValueError:
                errs.append("type must be one of: " + ", ".join(t.value for t in WOType))
        raw_p = (_s(r.get("priority")) or (plan.priority.value if plan else "P3")).upper()
        try:
            prio = Priority(PRIO_ALIASES.get(raw_p.lower(), raw_p))
        except ValueError:
            errs.append("priority must be P1, P2, P3 or P4")
            prio = Priority.P3_MEDIUM
        due = _date(r.get("due_date"), errs, "due_date")
        start = _date(r.get("planned_start"), errs, "planned_start")
        hours = _num(r.get("estimated_hours"), "estimated_hours", errs)
        assignees: list[uuid.UUID] = []
        for who in [w.strip().lower() for w in (_s(r.get("assign_to")) or "").replace(";", ",").split(",") if w.strip()]:
            if who in people:
                assignees.append(people[who])
            else:
                errs.append(f"assign_to: {who} is not an active member of this plant")
        if assignees and ctx is not None and not ctx.has("wo.assign"):
            errs.append("assign_to needs the permission to assign technicians; leave it blank")
        occ = None
        if plan is not None:
            n = used_plans.get(pcode, 0)
            waiting = list(
                db.execute(
                    select(PMOccurrence)
                    .where(
                        PMOccurrence.pm_plan_id == plan.id,
                        PMOccurrence.work_order_id.is_(None),
                        PMOccurrence.status.in_([OccurrenceStatus.SCHEDULED, OccurrenceStatus.DEFERRED]),
                    )
                    .order_by(PMOccurrence.due_date)
                    .limit(n + 1)
                ).scalars()
            )
            if len(waiting) <= n:
                errs.append(f"PM plan {pcode} has no waiting occurrence to release")
            else:
                occ = waiting[n]
                used_plans[pcode] = n + 1
        out.append(
            {
                "row": i,
                "code": pcode or acode or None,
                "errors": errs,
                "asset": asset,
                "plan": plan,
                "occurrence": occ,
                "title": title,
                "type": wtype,
                "priority": prio,
                "due": due,
                "start": start,
                "hours": hours,
                "description": _s(r.get("description")),
                "assignees": assignees,
            }
        )
    errors = [{"row": r["row"], "code": r["code"], "errors": r["errors"]} for r in out if r["errors"]]
    return {
        "rows": out,
        "total": len(out),
        "valid": len(out) - len(errors),
        "invalid": len(errors),
        "errors": errors,
        "plans": sum(1 for r in out if r["occurrence"] is not None),  # shown as "PM releases"
    }


def preview_dict(v: dict) -> dict:
    return {k: v[k] for k in ("total", "valid", "invalid", "errors", "plans")}


def commit_work_orders(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID, ctx: Ctx | None = None) -> int:
    from app.services import pm as pmsvc
    from app.services import workorders as wosvc

    v = validate_work_orders(db, plant, rows, ctx)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    tz = ZoneInfo(plant.timezone)
    numbers: list[str] = []
    for rec in v["rows"]:
        if rec["occurrence"] is not None:
            occ = rec["occurrence"]
            if rec["due"]:
                occ.due_date = rec["due"]
            (wo,) = pmsvc.generate_work_orders(db, plant, rec["due"] or occ.due_date, occurrence_ids=[occ.id], user_id=user_id)
            wo.title, wo.priority = rec["title"], rec["priority"]
        else:
            wo = wosvc.create_work_order(
                db,
                plant,
                asset=rec["asset"],
                type=rec["type"],
                title=rec["title"],
                user_id=user_id,
                priority=rec["priority"],
                description=rec["description"],
                due_date=rec["due"],
            )
        if rec["start"]:
            wo.planned_start = datetime.combine(rec["start"], time(7, 0), tz)
            wo.planned_end = wo.planned_start + timedelta(hours=float(rec["hours"] or 8))
        if rec["hours"] is not None:
            wo.estimated_hours = rec["hours"]
        if rec["description"] and rec["occurrence"] is not None:
            wo.description = rec["description"]
        db.flush()
        if rec["assignees"] and ctx is not None:
            try:
                wosvc.assign(db, ctx, wo, rec["assignees"], rec["assignees"][0], force=True)
            except DomainError as e:
                raise ValueError(f"Row {rec['row']}: {e}") from e
        numbers.append(wo.number)
    audit(db, "wo.import", user_id=user_id, plant_id=plant.id, data={"work_orders": numbers})
    return len(numbers)
