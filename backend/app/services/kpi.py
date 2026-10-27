"""KPI engine. Each KPI function returns a KPIResult with:
  value (None when unavailable), available flag, reason when unavailable, the numerator/denominator used,
  and `records` for drill-down. Formulas and inclusion rules are documented in KPI_DEFINITIONS (seeded to
  kpi_definitions and docs/KPI_DEFINITIONS.md). Tunables come from plant.settings["kpi"].
Periods are plant-local dates [start, end] inclusive; timestamps are compared in UTC after conversion."""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.assets import Asset, DowntimeEvent
from app.models.enums import (
    OPEN_WO_STATUSES,
    ConditionStatus,
    LubeTaskStatus,
    OccurrenceStatus,
    RosterKind,
    ShutdownStatus,
    TxnType,
    WOStatus,
    WOType,
)
from app.models.identity import Membership, Role
from app.models.inventory import InventoryTransaction, PartUsage, StockoutEvent
from app.models.lubrication import LubeTask
from app.models.pdm import ConditionAlert
from app.models.pm import PMOccurrence, PMPlan
from app.models.shifts import RosterEntry
from app.models.shutdowns import Shutdown
from app.models.system import MaintenanceBudget, ProductionRecord
from app.models.tenancy import Department, Plant
from app.models.workorders import WOLabor, WorkOrder, WOService
from app.services.common import plant_today
from app.services.shutdowns import readiness

PLANNED_TYPES_DEFAULT = ["preventive", "predictive", "inspection", "lubrication", "shutdown", "improvement"]
MAX_RECORDS = 500


@dataclass
class Scope:
    plant: Plant
    start: date
    end: date
    department_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.plant.timezone)

    @property
    def t0(self) -> datetime:
        return datetime.combine(self.start, time.min, self.tz)

    @property
    def t1(self) -> datetime:
        return datetime.combine(self.end + timedelta(days=1), time.min, self.tz)

    @property
    def hours(self) -> float:
        return (self.t1 - self.t0).total_seconds() / 3600

    def cfg(self, key: str, default: Any) -> Any:
        return ((self.plant.settings or {}).get("kpi") or {}).get(key, default)


@dataclass
class KPIResult:
    code: str
    value: float | None
    unit: str
    available: bool = True
    reason: str | None = None
    numerator: float | None = None
    denominator: float | None = None
    details: dict = field(default_factory=dict)
    records: list[dict] = field(default_factory=list)

    def out(self, with_records: bool = False) -> dict:
        d = {
            "code": self.code,
            "value": None if self.value is None else round(self.value, 2),
            "unit": self.unit,
            "available": self.available,
            "reason": self.reason,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "details": self.details,
        }
        if with_records:
            d["records"] = self.records[:MAX_RECORDS]
            d["records_truncated"] = len(self.records) > MAX_RECORDS
        return d


def unavailable(code: str, unit: str, reason: str, **kw: Any) -> KPIResult:
    return KPIResult(code=code, value=None, unit=unit, available=False, reason=reason, **kw)


def ratio(code: str, unit: str, num: float, den: float, reason: str, records: list[dict], scale: float = 100, **details: Any) -> KPIResult:
    if not den:
        return unavailable(code, unit, reason, numerator=num, denominator=den, records=records, details=details)
    return KPIResult(
        code=code, value=num / den * scale, unit=unit, numerator=round(num, 4), denominator=round(den, 4), records=records, details=details
    )


def _asset_ids(db: Session, s: Scope) -> list[uuid.UUID] | None:
    """Asset scope: subtree of the selected asset, or all assets of the department; None = whole plant."""
    if s.asset_id:
        a = db.get(Asset, s.asset_id)
        if a is None or a.plant_id != s.plant.id:
            return []
        return list(db.execute(select(Asset.id).where(Asset.plant_id == s.plant.id, Asset.path.startswith(a.path))).scalars())
    if s.department_id:
        return list(db.execute(select(Asset.id).where(Asset.plant_id == s.plant.id, Asset.department_id == s.department_id)).scalars())
    return None


def _wo_scope(q: Any, s: Scope, ids: list[uuid.UUID] | None) -> Any:
    q = q.where(WorkOrder.plant_id == s.plant.id)
    if s.department_id:
        q = q.where(WorkOrder.department_id == s.department_id)
    if ids is not None and s.asset_id:
        q = q.where(WorkOrder.asset_id.in_(ids))
    return q


def wo_rec(w: WorkOrder) -> dict:
    return {
        "id": str(w.id),
        "number": w.number,
        "type": w.type.value,
        "status": w.status.value,
        "title": w.title,
        "due_date": w.due_date.isoformat() if w.due_date else None,
        "completed_at": w.completed_at.isoformat() if w.completed_at else None,
    }


# 1 ---------------------------------------------------------------------------
def pm_compliance(db: Session, s: Scope) -> KPIResult:
    q = (
        select(PMOccurrence, PMPlan, Asset)
        .join(PMPlan, PMPlan.id == PMOccurrence.pm_plan_id)
        .join(Asset, Asset.id == PMPlan.asset_id)
        .where(
            PMOccurrence.plant_id == s.plant.id,
            PMOccurrence.due_date >= s.start,
            PMOccurrence.due_date <= s.end,
            PMOccurrence.status != OccurrenceStatus.CANCELLED,
        )
    )
    ids = _asset_ids(db, s)
    if ids is not None:
        q = q.where(PMPlan.asset_id.in_(ids))
    today = plant_today(s.plant)
    total = ontime = late = 0
    pending_not_due = 0
    recs = []
    for occ, plan, asset in db.execute(q).all():
        deadline = occ.due_date + timedelta(days=plan.tolerance_days)
        done = occ.status == OccurrenceStatus.COMPLETED and occ.completed_date is not None
        if not done and deadline >= today:
            pending_not_due += 1  # not yet past its window: excluded until it is late or completed
            continue
        total += 1
        ok = done and occ.completed_date <= deadline  # type: ignore[operator]
        ontime += ok
        late += done and not ok
        recs.append(
            {
                "occurrence_id": str(occ.id),
                "plan": plan.code,
                "asset": asset.code,
                "due_date": occ.due_date.isoformat(),
                "completed_date": occ.completed_date.isoformat() if occ.completed_date else None,
                "status": occ.status.value,
                "compliant": bool(ok),
                "work_order_id": str(occ.work_order_id) if occ.work_order_id else None,
            }
        )
    return ratio(
        "pm_compliance",
        "%",
        ontime,
        total,
        "No eligible PMs were due in the period",
        recs,
        completed_late=late,
        not_completed=total - ontime - late,
        excluded_not_yet_due=pending_not_due,
    )


# 2 ---------------------------------------------------------------------------
def schedule_compliance(db: Session, s: Scope) -> KPIResult:
    ids = _asset_ids(db, s)
    q = _wo_scope(select(WorkOrder), s, ids).where(
        WorkOrder.planned_start >= s.t0, WorkOrder.planned_start < s.t1, WorkOrder.status != WOStatus.CANCELLED
    )
    total = ok = 0
    recs = []
    for w in db.execute(q).scalars():
        assert w.planned_start is not None
        deadline = w.planned_end or datetime.combine(w.planned_start.astimezone(s.tz).date() + timedelta(days=1), time.min, s.tz)
        done = w.completed_at is not None and w.completed_at <= deadline
        total += 1
        ok += done
        r = wo_rec(w)
        r["compliant"] = done
        recs.append(r)
    return ratio("schedule_compliance", "%", ok, total, "No work orders were scheduled in the period", recs)


# 3 ---------------------------------------------------------------------------
def _labor_rows(db: Session, s: Scope) -> list[tuple[WOLabor, WorkOrder]]:
    ids = _asset_ids(db, s)
    q = _wo_scope(select(WOLabor, WorkOrder).join(WorkOrder, WorkOrder.id == WOLabor.work_order_id), s, ids).where(
        WOLabor.work_date >= s.start, WOLabor.work_date <= s.end
    )
    return list(db.execute(q).all())


def planned_maintenance_pct(db: Session, s: Scope) -> KPIResult:
    planned = set(s.cfg("planned_types", PLANNED_TYPES_DEFAULT))
    tot = pl = 0.0
    by_type: dict[str, float] = defaultdict(float)
    for lab, w in _labor_rows(db, s):
        h = float(lab.hours)
        tot += h
        by_type[w.type.value] += h
        if w.type.value in planned:
            pl += h
    recs = [{"type": k, "hours": round(v, 2), "planned": k in planned} for k, v in sorted(by_type.items())]
    return ratio("planned_maintenance_pct", "%", pl, tot, "No labor hours were recorded in the period", recs, planned_types=sorted(planned))


# 4 ---------------------------------------------------------------------------
def _wo_cols():  # type: ignore[no-untyped-def]
    return (
        WorkOrder.id,
        WorkOrder.number,
        WorkOrder.type,
        WorkOrder.status,
        WorkOrder.title,
        WorkOrder.due_date,
        WorkOrder.completed_at,
        WorkOrder.estimated_hours,
        WorkOrder.actual_labor_hours,
    )


def _row_rec(r: Any) -> dict:
    return {
        "id": str(r.id),
        "number": r.number,
        "type": r.type.value,
        "status": r.status.value,
        "title": r.title,
        "due_date": r.due_date.isoformat() if r.due_date else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


def backlog(db: Session, s: Scope) -> KPIResult:
    """Aggregated in SQL; only the first MAX_RECORDS rows are fetched for drill-down."""
    ids = _asset_ids(db, s)
    statuses = [WOStatus.APPROVED, WOStatus.PLANNED, WOStatus.SCHEDULED, WOStatus.IN_PROGRESS, WOStatus.ON_HOLD]
    remaining = func.greatest(WorkOrder.estimated_hours - func.coalesce(WorkOrder.actual_labor_hours, 0), 0)
    agg = _wo_scope(
        select(func.count(), func.count(WorkOrder.estimated_hours), func.coalesce(func.sum(remaining), 0)).select_from(WorkOrder), s, ids
    ).where(WorkOrder.status.in_(statuses))
    n_open, n_est, hours_d = db.execute(agg).one()
    hours = float(hours_d or 0)
    missing = n_open - n_est
    rows = db.execute(
        _wo_scope(select(*_wo_cols(), remaining.label("rem")), s, ids)
        .where(WorkOrder.status.in_(statuses), WorkOrder.estimated_hours.is_not(None))
        .order_by(WorkOrder.due_date.asc().nulls_last())
        .limit(MAX_RECORDS + 1)
    ).all()
    recs = [{**_row_rec(r), "remaining_hours": round(float(r.rem or 0), 2)} for r in rows]
    tech_roles = s.cfg("capacity_roles", ["technician"])
    q = (
        select(func.count())
        .select_from(Membership)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.plant_id == s.plant.id, Membership.is_active.is_(True), Role.code.in_(tech_roles))
    )
    if s.department_id:
        q = q.where(Membership.department_id == s.department_id)
    techs = db.execute(q).scalar_one()
    weekly = techs * float(s.plant.working_hours_per_day) * len(s.plant.working_days or [])
    weeks = hours / weekly if weekly else None
    res = KPIResult(
        code="backlog",
        value=hours,
        unit="h",
        numerator=round(hours, 2),
        denominator=weekly or None,
        records=recs,
        details={
            "weeks": round(weeks, 2) if weeks is not None else None,
            "weekly_capacity_hours": weekly,
            "technicians": techs,
            "excluded_missing_estimate": missing,
            "open_work_orders": n_open,
        },
    )
    if weeks is None:
        res.details["weeks_unavailable_reason"] = "No technician capacity configured"
    return res


# 5 ---------------------------------------------------------------------------
def overdue_work_orders(db: Session, s: Scope) -> KPIResult:
    today = plant_today(s.plant)
    ids = _asset_ids(db, s)
    cond = (WorkOrder.status.in_(OPEN_WO_STATUSES), WorkOrder.due_date < today)
    n = db.execute(_wo_scope(select(func.count()).select_from(WorkOrder), s, ids).where(*cond)).scalar_one()
    rows = db.execute(_wo_scope(select(*_wo_cols()), s, ids).where(*cond).order_by(WorkOrder.due_date).limit(MAX_RECORDS + 1)).all()
    return KPIResult(
        code="overdue_work_orders",
        value=float(n),
        unit="count",
        numerator=n,
        records=[_row_rec(r) for r in rows],
        details={"as_of": today.isoformat()},
    )


# 6 ---------------------------------------------------------------------------
def emergency_pct(db: Session, s: Scope) -> KPIResult:
    basis = s.cfg("emergency_basis", "hours")
    if basis == "count":
        ids = _asset_ids(db, s)
        rows = (
            db.execute(
                _wo_scope(select(WorkOrder), s, ids).where(
                    WorkOrder.created_at >= s.t0, WorkOrder.created_at < s.t1, WorkOrder.status != WOStatus.CANCELLED
                )
            )
            .scalars()
            .all()
        )
        em = [w for w in rows if w.type == WOType.EMERGENCY]
        return ratio(
            "emergency_pct", "%", len(em), len(rows), "No work orders created in the period", [wo_rec(w) for w in em], basis="count"
        )
    tot = em_h = 0.0
    recs = {}
    for lab, w in _labor_rows(db, s):
        tot += float(lab.hours)
        if w.type == WOType.EMERGENCY:
            em_h += float(lab.hours)
            recs[w.id] = wo_rec(w)
    return ratio("emergency_pct", "%", em_h, tot, "No labor hours were recorded in the period", list(recs.values()), basis="hours")


# 7-9, 14 ---------------------------------------------------------------------
def _downtime(db: Session, s: Scope, failures_only: bool, include_planned: bool) -> list[DowntimeEvent]:
    ids = _asset_ids(db, s)
    q = select(DowntimeEvent).where(
        DowntimeEvent.plant_id == s.plant.id,
        DowntimeEvent.started_at < s.t1,
        or_(DowntimeEvent.ended_at.is_(None), DowntimeEvent.ended_at > s.t0),
    )
    if ids is not None:
        q = q.where(DowntimeEvent.asset_id.in_(ids))
    if failures_only:
        q = q.where(DowntimeEvent.is_failure.is_(True))
    if not include_planned:
        q = q.where(DowntimeEvent.is_planned.is_(False))
    return list(db.execute(q.order_by(DowntimeEvent.started_at)).scalars())


def _merged_hours(events: list[DowntimeEvent], t0: datetime, t1: datetime, now: datetime) -> float:
    """Union of downtime intervals clipped to the period (overlapping events on the same system are not double counted)."""
    iv = sorted((max(e.started_at, t0), min(e.ended_at or min(now, t1), t1)) for e in events)
    total, cur_s, cur_e = 0.0, None, None
    for a, b in iv:
        if b <= a:
            continue
        if cur_e is None or a > cur_e:
            if cur_e is not None and cur_s is not None:
                total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = a, b
        else:
            cur_e = max(cur_e, b)
    if cur_e is not None and cur_s is not None:
        total += (cur_e - cur_s).total_seconds()
    return total / 3600


def _dt_rec(e: DowntimeEvent) -> dict:
    return {
        "id": str(e.id),
        "asset_id": str(e.asset_id),
        "started_at": e.started_at.isoformat(),
        "ended_at": e.ended_at.isoformat() if e.ended_at else None,
        "is_failure": e.is_failure,
        "work_order_id": str(e.work_order_id) if e.work_order_id else None,
        "reason": e.reason,
    }


def _now_clip(s: Scope) -> datetime:
    from app.services.common import utcnow

    return min(utcnow(), s.t1)


def _observed_hours(s: Scope) -> float:
    return max((_now_clip(s) - s.t0).total_seconds() / 3600, 0)


def mtbf(db: Session, s: Scope) -> KPIResult:
    inc_planned = s.cfg("include_planned_downtime", False)
    all_dt = _downtime(db, s, failures_only=False, include_planned=inc_planned)
    fails = [e for e in all_dt if e.is_failure and e.started_at >= s.t0]
    observed = _observed_hours(s)
    down = _merged_hours(all_dt, s.t0, s.t1, _now_clip(s))
    op = max(observed - down, 0)
    if not fails:
        return unavailable(
            "mtbf",
            "h",
            "No failure events in the period (MTBF exceeds the observed operating time)",
            numerator=round(op, 2),
            denominator=0,
            details={"operating_hours": round(op, 2)},
        )
    return KPIResult(
        code="mtbf",
        value=op / len(fails),
        unit="h",
        numerator=round(op, 2),
        denominator=len(fails),
        records=[_dt_rec(e) for e in fails],
        details={"operating_hours": round(op, 2), "failures": len(fails), "model": "system (scope treated as one series system)"},
    )


def mttr(db: Session, s: Scope) -> KPIResult:
    ev = [e for e in _downtime(db, s, failures_only=True, include_planned=False) if e.ended_at is not None and s.t0 <= e.ended_at < s.t1]
    if not ev:
        return unavailable("mttr", "h", "No completed repairs (failure downtime with an end time) in the period")
    tot = sum((e.ended_at - e.started_at).total_seconds() / 3600 for e in ev if e.ended_at)
    return KPIResult(
        code="mttr", value=tot / len(ev), unit="h", numerator=round(tot, 2), denominator=len(ev), records=[_dt_rec(e) for e in ev]
    )


def availability(db: Session, s: Scope) -> KPIResult:
    inc_planned = s.cfg("include_planned_downtime", False)
    ev = _downtime(db, s, failures_only=False, include_planned=inc_planned)
    observed = _observed_hours(s)
    if observed <= 0:
        return unavailable("availability", "%", "Period has not started")
    down = _merged_hours(ev, s.t0, s.t1, _now_clip(s))
    op = observed - down
    res = ratio(
        "availability",
        "%",
        op,
        op + down,
        "No observed time",
        [_dt_rec(e) for e in ev],
        operating_hours=round(op, 2),
        downtime_hours=round(down, 2),
        include_planned_downtime=inc_planned,
    )
    if not ev:
        res.details["note"] = "No downtime events recorded in scope; the value is only as complete as downtime logging."
    return res


def breakdown_downtime(db: Session, s: Scope) -> KPIResult:
    ev = _downtime(db, s, failures_only=True, include_planned=False)
    h = _merged_hours(ev, s.t0, s.t1, _now_clip(s))
    loss = sum(float(e.production_loss_tons or 0) for e in ev)
    return KPIResult(
        code="breakdown_downtime",
        value=h,
        unit="h",
        numerator=round(h, 2),
        records=[_dt_rec(e) for e in ev],
        details={"events": len(ev), "production_loss_tons": round(loss, 2)},
    )


# 10 --------------------------------------------------------------------------
def _production(db: Session, s: Scope) -> list[ProductionRecord]:
    q = select(ProductionRecord).where(
        ProductionRecord.plant_id == s.plant.id, ProductionRecord.record_date >= s.start, ProductionRecord.record_date <= s.end
    )
    if s.department_id:
        q = q.where(ProductionRecord.department_id == s.department_id)
    if s.asset_id:
        q = q.where(ProductionRecord.asset_id == s.asset_id)
    return list(db.execute(q).scalars())


def oee(db: Session, s: Scope) -> KPIResult:
    rows = _production(db, s)
    usable = [
        r
        for r in rows
        if r.planned_production_hours
        and r.run_hours is not None
        and r.ideal_rate_tph
        and r.good_tons is not None
        and float(r.planned_production_hours) > 0
        and float(r.ideal_rate_tph) > 0
    ]
    if not usable:
        return unavailable(
            "oee",
            "%",
            "OEE requires production records with planned hours, run hours, ideal rate and good tons",
            details={"records_in_period": len(rows)},
        )
    ph = sum(float(r.planned_production_hours or 0) for r in usable)
    rh = sum(float(r.run_hours or 0) for r in usable)
    tons = sum(float(r.tons_produced) for r in usable)
    good = sum(float(r.good_tons or 0) for r in usable)
    ideal = sum(float(r.run_hours or 0) * float(r.ideal_rate_tph or 0) for r in usable)
    a = rh / ph
    p = tons / ideal if ideal else 0
    q = good / tons if tons else 0
    return KPIResult(
        code="oee",
        value=a * p * q * 100,
        unit="%",
        records=[
            {
                "date": r.record_date.isoformat(),
                "tons": float(r.tons_produced),
                "good_tons": float(r.good_tons or 0),
                "run_hours": float(r.run_hours or 0),
                "planned_hours": float(r.planned_production_hours or 0),
            }
            for r in usable
        ],
        details={
            "availability": round(a * 100, 2),
            "performance": round(p * 100, 2),
            "quality": round(q * 100, 2),
            "excluded_incomplete_records": len(rows) - len(usable),
        },
    )


# 11, 12, 19 ------------------------------------------------------------------
def cost_rows(db: Session, s: Scope) -> list[dict]:
    """Maintenance cost on a transaction-date basis: labor (work date), materials (issue/return or used-on date),
    contractor services (entry date). Each row is attributed to its work order's department and asset."""
    ids = _asset_ids(db, s)
    rows: list[dict] = []
    for lab, w in _labor_rows(db, s):
        rows.append({"kind": "labor", "amount": float(lab.cost), "wo": w})
    q = _wo_scope(
        select(InventoryTransaction, WorkOrder).join(WorkOrder, WorkOrder.id == InventoryTransaction.work_order_id), s, ids
    ).where(
        InventoryTransaction.created_at >= s.t0,
        InventoryTransaction.created_at < s.t1,
        InventoryTransaction.type.in_([TxnType.ISSUE, TxnType.RETURN]),
    )
    for tx, w in db.execute(q).all():
        rows.append({"kind": "material", "amount": -float(tx.total_cost), "wo": w})
    # Parts recorded as used without a stock movement (store not connected, or migrated history).
    qp = _wo_scope(select(PartUsage, WorkOrder).join(WorkOrder, WorkOrder.id == PartUsage.work_order_id), s, ids).where(
        PartUsage.used_on >= s.start, PartUsage.used_on <= s.end
    )
    for pu, w in db.execute(qp).all():
        rows.append({"kind": "material", "amount": float(pu.total_cost), "wo": w})
    q2 = _wo_scope(select(WOService, WorkOrder).join(WorkOrder, WorkOrder.id == WOService.work_order_id), s, ids).where(
        WOService.created_at >= s.t0, WOService.created_at < s.t1
    )
    for sv, w in db.execute(q2).all():
        rows.append({"kind": "service", "amount": float(sv.cost), "wo": w})
    return rows


def _cost_summary(rows: list[dict]) -> dict:
    by: dict[str, float] = defaultdict(float)
    for r in rows:
        by[r["kind"]] += r["amount"]
    return {k: round(v, 2) for k, v in by.items()}


def _cost_records(rows: list[dict]) -> list[dict]:
    agg: dict[uuid.UUID, dict] = {}
    for r in rows:
        w = r["wo"]
        a = agg.setdefault(w.id, {**wo_rec(w), "labor": 0.0, "material": 0.0, "service": 0.0})
        a[r["kind"]] += r["amount"]
    for a in agg.values():
        a["total"] = round(a["labor"] + a["material"] + a["service"], 2)
    return sorted(agg.values(), key=lambda x: -x["total"])


def cost_per_ton(db: Session, s: Scope) -> KPIResult:
    rows = cost_rows(db, s)
    cost = sum(r["amount"] for r in rows)
    tons = sum(float(r.tons_produced) for r in _production(db, s))
    return ratio(
        "cost_per_ton",
        f"{s.plant.currency}/t",
        cost,
        tons,
        "No production tonnage recorded for the scope and period",
        _cost_records(rows),
        scale=1,
        breakdown=_cost_summary(rows),
        tons=tons,
    )


def cost_by_department(db: Session, s: Scope) -> KPIResult:
    rows = cost_rows(db, s)
    depts = {d.id: d for d in db.execute(select(Department).where(Department.plant_id == s.plant.id)).scalars()}
    by_dept: dict[str, float] = defaultdict(float)
    by_asset: dict[uuid.UUID, float] = defaultdict(float)
    for r in rows:
        w = r["wo"]
        by_dept[depts[w.department_id].code if w.department_id in depts else "?"] += r["amount"]
        by_asset[w.asset_id] += r["amount"]
    assets = {a.id: a for a in db.execute(select(Asset).where(Asset.id.in_(list(by_asset)))).scalars()} if by_asset else {}
    top = sorted(by_asset.items(), key=lambda kv: -kv[1])[:15]
    total = sum(r["amount"] for r in rows)
    return KPIResult(
        code="cost_by_department",
        value=total,
        unit=s.plant.currency,
        numerator=round(total, 2),
        records=_cost_records(rows),
        details={
            "by_department": {k: round(v, 2) for k, v in sorted(by_dept.items())},
            "top_assets": [
                {
                    "asset_id": str(k),
                    "code": assets[k].code if k in assets else "?",
                    "name": assets[k].name if k in assets else "",
                    "cost": round(v, 2),
                }
                for k, v in top
            ],
            "breakdown": _cost_summary(rows),
        },
    )


def budget_vs_actual(db: Session, s: Scope) -> KPIResult:
    months = set()
    d = s.start.replace(day=1)
    while d <= s.end:
        months.add((d.year, d.month))
        d = (d + timedelta(days=32)).replace(day=1)
    q = select(MaintenanceBudget).where(MaintenanceBudget.plant_id == s.plant.id)
    q = (
        q.where(MaintenanceBudget.department_id == s.department_id)
        if s.department_id
        else q.where(MaintenanceBudget.department_id.is_(None))
    )
    budgets = [b for b in db.execute(q).scalars() if (b.year, b.month) in months]
    rows = cost_rows(db, s)
    actual = sum(r["amount"] for r in rows)
    budget = sum(float(b.amount) for b in budgets)
    res = ratio(
        "budget_vs_actual",
        "%",
        actual,
        budget,
        "No maintenance budget entered for the period/scope",
        _cost_records(rows),
        actual=round(actual, 2),
        budget=round(budget, 2),
        variance=round(budget - actual, 2),
        months_with_budget=len(budgets),
        months_in_period=len(months),
    )
    if res.available and len(budgets) < len(months):
        res.details["warning"] = "Budget missing for some months in the period"
    return res


# 13 --------------------------------------------------------------------------
def repeat_failure_rate(db: Session, s: Scope) -> KPIResult:
    ids = _asset_ids(db, s)
    rows = (
        db.execute(
            _wo_scope(select(WorkOrder), s, ids).where(
                WorkOrder.type.in_([WOType.CORRECTIVE, WOType.EMERGENCY]), WorkOrder.completed_at >= s.t0, WorkOrder.completed_at < s.t1
            )
        )
        .scalars()
        .all()
    )
    rep = [w for w in rows if w.is_repeat_failure]
    return ratio(
        "repeat_failure_rate",
        "%",
        len(rep),
        len(rows),
        "No corrective/emergency work completed in the period",
        [wo_rec(w) for w in rep],
        window_days=(s.plant.settings or {}).get("repeat_failure_days", 30),
    )


# 15 --------------------------------------------------------------------------
def lubrication_compliance(db: Session, s: Scope) -> KPIResult:
    from app.models.lubrication import LubricationPoint

    today = plant_today(s.plant)
    tol = int(s.cfg("lube_tolerance_days", 1))
    q = (
        select(LubeTask, LubricationPoint)
        .join(LubricationPoint, LubricationPoint.id == LubeTask.point_id)
        .where(LubeTask.plant_id == s.plant.id, LubeTask.due_date >= s.start, LubeTask.due_date <= s.end)
    )
    ids = _asset_ids(db, s)
    if ids is not None:
        q = q.where(LubricationPoint.asset_id.in_(ids))
    total = ok = 0
    recs = []
    for t, p in db.execute(q).all():
        deadline = t.due_date + timedelta(days=tol)
        if t.status == LubeTaskStatus.PENDING and deadline >= today:
            continue
        total += 1
        good = t.status == LubeTaskStatus.DONE and t.done_date is not None and t.done_date <= deadline
        ok += good
        recs.append(
            {
                "task_id": str(t.id),
                "point": p.code,
                "due_date": t.due_date.isoformat(),
                "status": t.status.value,
                "done_date": t.done_date.isoformat() if t.done_date else None,
                "compliant": good,
            }
        )
    return ratio("lubrication_compliance", "%", ok, total, "No lubrication tasks were due in the period", recs, tolerance_days=tol)


# 16 --------------------------------------------------------------------------
def pdm_alerts(db: Session, s: Scope) -> KPIResult:
    ids = _asset_ids(db, s)
    q = select(ConditionAlert).where(
        ConditionAlert.plant_id == s.plant.id, ConditionAlert.created_at >= s.t0, ConditionAlert.created_at < s.t1
    )
    if ids is not None:
        q = q.where(ConditionAlert.asset_id.in_(ids))
    rows = db.execute(q).scalars().all()
    by = {"warning": 0, "critical": 0}
    for a in rows:
        by[a.severity.value] = by.get(a.severity.value, 0) + 1
    open_q = (
        select(ConditionAlert.severity, func.count())
        .where(ConditionAlert.plant_id == s.plant.id, ConditionAlert.status.not_in(["resolved"]))
        .group_by(ConditionAlert.severity)
    )
    open_by = {sev.value: n for sev, n in db.execute(open_q).all()}
    return KPIResult(
        code="pdm_alerts",
        value=float(len(rows)),
        unit="count",
        numerator=len(rows),
        records=[
            {
                "id": str(a.id),
                "severity": a.severity.value,
                "status": a.status.value,
                "message": a.message,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ],
        details={"by_severity": by, "open_by_severity": open_by, "critical": by.get(ConditionStatus.CRITICAL.value, 0)},
    )


# 17 --------------------------------------------------------------------------
def stockout_rate(db: Session, s: Scope) -> KPIResult:
    so = (
        db.execute(
            select(StockoutEvent).where(
                StockoutEvent.plant_id == s.plant.id, StockoutEvent.created_at >= s.t0, StockoutEvent.created_at < s.t1
            )
        )
        .scalars()
        .all()
    )
    issues = db.execute(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(
            InventoryTransaction.plant_id == s.plant.id,
            InventoryTransaction.type == TxnType.ISSUE,
            InventoryTransaction.created_at >= s.t0,
            InventoryTransaction.created_at < s.t1,
        )
    ).scalar_one()
    return ratio(
        "stockout_rate",
        "%",
        len(so),
        len(so) + issues,
        "No material demand (issues or stockouts) in the period",
        [
            {
                "part_id": str(e.part_id),
                "work_order_id": str(e.work_order_id) if e.work_order_id else None,
                "requested": float(e.requested_qty),
                "available": float(e.available_qty),
                "at": e.created_at.isoformat(),
            }
            for e in so
        ],
        issues=issues,
        stockouts=len(so),
    )


# 18 --------------------------------------------------------------------------
def labor_utilization(db: Session, s: Scope) -> KPIResult:
    q = select(RosterEntry).where(
        RosterEntry.plant_id == s.plant.id,
        RosterEntry.work_date >= s.start,
        RosterEntry.work_date <= s.end,
        RosterEntry.kind.in_([RosterKind.WORK, RosterKind.OVERTIME, RosterKind.CALLOUT]),
    )
    if s.department_id:
        q = q.join(Membership, and_(Membership.user_id == RosterEntry.user_id, Membership.plant_id == s.plant.id)).where(
            Membership.department_id == s.department_id
        )
    avail = sum(float(r.hours) + float(r.overtime_hours) + float(r.callout_hours) for r in db.execute(q).scalars())
    booked = sum(float(lab.hours) for lab, _ in _labor_rows(db, s))
    return ratio(
        "labor_utilization",
        "%",
        booked,
        avail,
        "No rostered hours in the period (roster required)",
        [],
        booked_hours=round(booked, 2),
        available_hours=round(avail, 2),
    )


# 20 --------------------------------------------------------------------------
def shutdown_progress(db: Session, s: Scope) -> KPIResult:
    q = select(Shutdown).where(
        Shutdown.plant_id == s.plant.id,
        Shutdown.status != ShutdownStatus.CANCELLED,
        Shutdown.planned_start < s.t1,
        Shutdown.planned_end >= s.t0,
    )
    if s.department_id:
        q = q.where(Shutdown.department_id == s.department_id)
    sds = db.execute(q.order_by(Shutdown.planned_start.desc())).scalars().all()
    if not sds:
        return unavailable("shutdown_progress", "%", "No shutdown overlaps the period")
    recs = []
    for sd in sds:
        r = readiness(db, sd)
        recs.append({"id": str(sd.id), "code": sd.code, "name": sd.name, "status": sd.status.value, **r})
    cur = recs[0]
    if cur["weighted_progress_pct"] is None:
        return unavailable("shutdown_progress", "%", "Shutdown has no work packages", records=recs)
    return KPIResult(
        code="shutdown_progress", value=cur["weighted_progress_pct"], unit="%", records=recs, details={"shutdown": cur["code"]}
    )


KPI_FUNCS = {
    "pm_compliance": pm_compliance,
    "schedule_compliance": schedule_compliance,
    "planned_maintenance_pct": planned_maintenance_pct,
    "backlog": backlog,
    "overdue_work_orders": overdue_work_orders,
    "emergency_pct": emergency_pct,
    "mtbf": mtbf,
    "mttr": mttr,
    "availability": availability,
    "oee": oee,
    "cost_per_ton": cost_per_ton,
    "cost_by_department": cost_by_department,
    "repeat_failure_rate": repeat_failure_rate,
    "breakdown_downtime": breakdown_downtime,
    "lubrication_compliance": lubrication_compliance,
    "pdm_alerts": pdm_alerts,
    "stockout_rate": stockout_rate,
    "labor_utilization": labor_utilization,
    "budget_vs_actual": budget_vs_actual,
    "shutdown_progress": shutdown_progress,
}


def compute_all(db: Session, s: Scope) -> list[dict]:
    return [f(db, s).out() for f in KPI_FUNCS.values()]


def asset_reliability(db: Session, plant: Plant, asset: Asset, start: date | None, end: date | None) -> dict:
    today = plant_today(plant)
    s = Scope(plant=plant, start=start or today - timedelta(days=365), end=end or today, asset_id=asset.id)
    return {
        "period": {"start": s.start.isoformat(), "end": s.end.isoformat()},
        **{k: KPI_FUNCS[k](db, s).out() for k in ("mtbf", "mttr", "availability", "breakdown_downtime")},
    }
