"""Preventive-maintenance scheduling engine.

Idempotency and concurrency guarantees:
  * an occurrence is identified by (pm_plan_id, occurrence_key); inserts use ON CONFLICT DO NOTHING;
  * a work order references at most one occurrence (UNIQUE work_orders.pm_occurrence_id);
  * occurrences are claimed with SELECT ... FOR UPDATE SKIP LOCKED, so concurrent workers never both
    generate a WO for the same occurrence;
  * a per-plant transaction-scoped advisory lock serialises full scheduler runs.
Due dates are plant-local calendar dates; "today" is computed in the plant's timezone.
"""

import calendar
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.assets import Asset, Meter, MeterReading
from app.models.enums import FrequencyUnit, OccurrenceStatus, PMTrigger, ScheduleBasis, WOStatus
from app.models.pm import JobPlan, PMOccurrence, PMPlan
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services.common import audit, plant_today, utcnow
from app.services.notifications import notify_permission

OPEN_OCC = [
    OccurrenceStatus.SCHEDULED,
    OccurrenceStatus.GENERATED,
    OccurrenceStatus.DEFERRAL_REQUESTED,
    OccurrenceStatus.DEFERRED,
    OccurrenceStatus.CANCELLATION_REQUESTED,
]


def add_interval(d: date, unit: FrequencyUnit, n: int) -> date:
    if unit == FrequencyUnit.DAY:
        return d + timedelta(days=n)
    if unit == FrequencyUnit.WEEK:
        return d + timedelta(weeks=n)
    months = n if unit == FrequencyUnit.MONTH else 12 * n
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def fixed_schedule(start: date, unit: FrequencyUnit, n: int, lower: date, upper: date) -> list[date]:
    """All anchor-based dates in [lower, upper]. Computed from the anchor each step (no drift on month ends)."""
    out: list[date] = []
    k = 0
    while True:
        d = add_interval(start, unit, n * k)
        if d > upper:
            return out
        if d >= lower:
            out.append(d)
        k += 1
        if k > 100000:  # pragma: no cover - defensive
            return out


def _insert_occ(db: Session, plan: PMPlan, key: str, due: date, due_meter: float | None = None) -> bool:
    res = db.execute(
        pg_insert(PMOccurrence)
        .values(
            id=uuid.uuid4(),
            plant_id=plan.plant_id,
            pm_plan_id=plan.id,
            occurrence_key=key,
            due_date=due,
            original_due_date=due,
            due_meter=due_meter,
            status=OccurrenceStatus.SCHEDULED,
        )
        .on_conflict_do_nothing(index_elements=["pm_plan_id", "occurrence_key"])
        .returning(PMOccurrence.id)
    )
    return res.first() is not None


def plan_occurrences(db: Session, plant: Plant, plan: PMPlan, today: date) -> int:
    """Create missing occurrences within the plan's horizon. Safe to run any number of times."""
    if not plan.is_active or plan.trigger != PMTrigger.CALENDAR:
        return 0
    assert plan.frequency_unit and plan.frequency_interval and plan.start_date
    upper = today + timedelta(days=plan.horizon_days)
    created = 0
    if plan.schedule_basis == ScheduleBasis.FIXED:
        last = db.execute(select(func.max(PMOccurrence.original_due_date)).where(PMOccurrence.pm_plan_id == plan.id)).scalar()
        lower = (last + timedelta(days=1)) if last else max(plan.start_date, today)
        for d in fixed_schedule(plan.start_date, plan.frequency_unit, plan.frequency_interval, lower, upper):
            created += _insert_occ(db, plan, f"D:{d.isoformat()}", d)
    else:
        open_exists = db.execute(
            select(PMOccurrence.id).where(PMOccurrence.pm_plan_id == plan.id, PMOccurrence.status.in_(OPEN_OCC)).limit(1)
        ).first()
        if not open_exists:
            if plan.last_completed_date:
                due = add_interval(plan.last_completed_date, plan.frequency_unit, plan.frequency_interval)
                key = f"F:{plan.last_completed_date.isoformat()}"
            else:
                due, key = max(plan.start_date, today), "F:start"
            if due <= upper:
                created += _insert_occ(db, plan, key, due)
    _refresh_next_due(db, plan)
    return created


def _refresh_next_due(db: Session, plan: PMPlan) -> None:
    plan.next_due_date = db.execute(
        select(func.min(PMOccurrence.due_date)).where(PMOccurrence.pm_plan_id == plan.id, PMOccurrence.status.in_(OPEN_OCC))
    ).scalar()
    if plan.next_due_date is None and plan.trigger == PMTrigger.CALENDAR and plan.frequency_unit and plan.frequency_interval:
        base = plan.last_completed_date or plan.start_date
        if base:
            plan.next_due_date = add_interval(base, plan.frequency_unit, plan.frequency_interval) if plan.last_completed_date else base


def generate_work_orders(db: Session, plant: Plant, today: date, plan_id: uuid.UUID | None = None) -> list[WorkOrder]:
    from app.services.workorders import create_work_order

    q = (
        select(PMOccurrence)
        .join(PMPlan, PMPlan.id == PMOccurrence.pm_plan_id)
        .where(
            PMOccurrence.plant_id == plant.id,
            PMOccurrence.work_order_id.is_(None),
            PMOccurrence.status.in_([OccurrenceStatus.SCHEDULED, OccurrenceStatus.DEFERRED]),
            PMOccurrence.due_date - PMPlan.lead_days <= today,
            PMPlan.is_active.is_(True),
        )
        .order_by(PMOccurrence.due_date)
        .with_for_update(of=PMOccurrence, skip_locked=True, key_share=True)
    )
    if plan_id:
        q = q.where(PMOccurrence.pm_plan_id == plan_id)
    created: list[WorkOrder] = []
    for occ in db.execute(q).scalars().all():
        plan = db.get(PMPlan, occ.pm_plan_id)
        assert plan is not None
        asset = db.get(Asset, plan.asset_id)
        jp = db.get(JobPlan, plan.job_plan_id)
        assert asset is not None and jp is not None
        nested = db.begin_nested()
        try:
            wo = create_work_order(
                db,
                plant,
                asset=asset,
                type=plan.wo_type,
                title=f"{plan.code} {plan.name}",
                user_id=None,
                priority=plan.priority,
                job_plan=jp,
                due_date=occ.due_date,
                pm_occurrence_id=occ.id,
            )
            nested.commit()
        except Exception:
            nested.rollback()
            raise
        occ.work_order_id = wo.id
        if occ.status == OccurrenceStatus.SCHEDULED:
            occ.status = OccurrenceStatus.GENERATED
        created.append(wo)
    return created


def run_scheduler(db: Session, plant: Plant, today: date | None = None) -> dict:
    """One full scheduler pass for a plant: plan occurrences, generate WOs, flag overdue."""
    today = today or plant_today(plant)
    lock_key = int(uuid.UUID(str(plant.id)).int % (2**62))
    got = db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": lock_key}).scalar()
    if not got:
        return {"skipped": True, "reason": "another scheduler run holds the lock"}
    plans = db.execute(select(PMPlan).where(PMPlan.plant_id == plant.id, PMPlan.is_active.is_(True))).scalars().all()
    occ_created = sum(plan_occurrences(db, plant, p, today) for p in plans)
    for p in plans:
        if p.trigger == PMTrigger.METER:
            check_meter_plan(db, plant, p, today)
    wos = generate_work_orders(db, plant, today)
    overdue = flag_overdue(db, plant, today)
    for p in plans:
        _refresh_next_due(db, p)
    return {
        "occurrences_created": occ_created,
        "work_orders_created": len(wos),
        "work_orders": [w.number for w in wos],
        "overdue_flagged": overdue,
        "today": today.isoformat(),
    }


def flag_overdue(db: Session, plant: Plant, today: date) -> int:
    rows = db.execute(
        select(PMOccurrence, WorkOrder)
        .join(WorkOrder, WorkOrder.id == PMOccurrence.work_order_id)
        .where(
            PMOccurrence.plant_id == plant.id,
            PMOccurrence.status.in_(OPEN_OCC),
            PMOccurrence.due_date < today,
            WorkOrder.status.not_in([WOStatus.COMPLETED, WOStatus.CLOSED, WOStatus.CANCELLED]),
        )
    ).all()
    n = 0
    for occ, wo in rows:
        n += (
            notify_permission(
                db,
                plant.id,
                "wo.plan",
                kind="pm_overdue",
                severity="warning",
                title=f"PM overdue: {wo.number}",
                body=f"Due {occ.due_date.isoformat()} — {wo.title}",
                link=f"/work-orders/{wo.id}",
                dedupe_key=f"pm-overdue:{occ.id}",
            )
            > 0
        )
    return n


# ---------------- meter-based PM ----------------
def record_meter_reading(
    db: Session, plant: Plant, meter: Meter, value: float, at: datetime, user_id: uuid.UUID | None, source: str = "manual"
) -> None:
    if Decimal(str(value)) < Decimal(str(meter.current_value or 0)):
        raise DomainError("Meter readings must not decrease (replace the meter to reset)", "meter_decrease", 422)
    db.add(MeterReading(meter_id=meter.id, value=value, read_at=at, recorded_by_id=user_id, source=source))
    meter.current_value = value
    meter.last_read_at = at
    if meter.is_operating_hours:
        asset = db.get(Asset, meter.asset_id)
        if asset:
            asset.operating_hours = value
    db.flush()
    today = plant_today(plant)
    for plan in db.execute(
        select(PMPlan).where(PMPlan.meter_id == meter.id, PMPlan.is_active.is_(True), PMPlan.trigger == PMTrigger.METER)
    ).scalars():
        if check_meter_plan(db, plant, plan, today):
            generate_work_orders(db, plant, today, plan_id=plan.id)


def check_meter_plan(db: Session, plant: Plant, plan: PMPlan, today: date) -> bool:
    if plan.meter_id is None or plan.meter_interval is None:
        return False
    meter = db.get(Meter, plan.meter_id)
    if meter is None:
        return False
    base = Decimal(str(plan.last_meter_value if plan.last_meter_value is not None else 0))
    due_at = base + Decimal(str(plan.meter_interval))
    if Decimal(str(meter.current_value)) >= due_at:
        open_exists = db.execute(
            select(PMOccurrence.id).where(PMOccurrence.pm_plan_id == plan.id, PMOccurrence.status.in_(OPEN_OCC)).limit(1)
        ).first()
        if open_exists:
            return False
        created = _insert_occ(db, plan, f"M:{due_at}", today, float(due_at))
        plan.next_due_date = today
        return created
    return False


# ---------------- completion / deferral ----------------
def on_occurrence_completed(db: Session, plant: Plant, wo: WorkOrder) -> None:
    occ = db.get(PMOccurrence, wo.pm_occurrence_id)
    if occ is None:
        return
    plan = db.get(PMPlan, occ.pm_plan_id)
    assert plan is not None
    now = wo.completed_at or utcnow()
    occ.status = OccurrenceStatus.COMPLETED
    occ.completed_at = now
    occ.completed_date = plant_today(plant, now)
    if plan.last_completed_date is None or occ.completed_date > plan.last_completed_date:
        plan.last_completed_date = occ.completed_date
    if plan.trigger == PMTrigger.METER:
        meter = db.get(Meter, plan.meter_id) if plan.meter_id else None
        plan.last_meter_value = meter.current_value if meter else occ.due_meter
    db.flush()
    plan_occurrences(db, plant, plan, plant_today(plant))
    _refresh_next_due(db, plan)


def request_change(
    db: Session, plant: Plant, occ: PMOccurrence, user_id: uuid.UUID, kind: str, reason: str, new_date: date | None
) -> PMOccurrence:
    if occ.status not in (OccurrenceStatus.SCHEDULED, OccurrenceStatus.GENERATED, OccurrenceStatus.DEFERRED):
        raise DomainError("Only open occurrences can be deferred or cancelled", "invalid_state", 409)
    if kind == "defer":
        if new_date is None or new_date <= occ.due_date:
            raise DomainError("Deferral requires a new date later than the current due date", "invalid_date", 422)
        occ.status = OccurrenceStatus.DEFERRAL_REQUESTED
    else:
        occ.status = OccurrenceStatus.CANCELLATION_REQUESTED
    occ.requested_by_id, occ.request_reason, occ.requested_new_date = user_id, reason, new_date
    notify_permission(
        db,
        plant.id,
        "pm.approve_deferral",
        kind="approval",
        title=f"PM {kind} requested",
        body=reason,
        link="/pm?tab=approvals",
        dedupe_key=f"pm-{kind}:{occ.id}:{occ.requested_new_date}",
    )
    audit(
        db,
        f"pm.{kind}_requested",
        user_id=user_id,
        plant_id=plant.id,
        entity_type="pm_occurrence",
        entity_id=occ.id,
        data={"reason": reason, "new_date": new_date},
    )
    return occ


def decide_change(db: Session, plant: Plant, occ: PMOccurrence, user_id: uuid.UUID, approve: bool) -> PMOccurrence:
    if occ.status not in (OccurrenceStatus.DEFERRAL_REQUESTED, OccurrenceStatus.CANCELLATION_REQUESTED):
        raise DomainError("No pending request", "invalid_state", 409)
    if occ.requested_by_id == user_id:
        raise DomainError("A request cannot be approved by the person who raised it", "four_eyes", 403)
    kind = "defer" if occ.status == OccurrenceStatus.DEFERRAL_REQUESTED else "cancel"
    wo = db.get(WorkOrder, occ.work_order_id) if occ.work_order_id else None
    occ.decided_by_id, occ.decided_at = user_id, utcnow()
    if not approve:
        occ.status = OccurrenceStatus.GENERATED if wo else OccurrenceStatus.SCHEDULED
    elif kind == "defer":
        assert occ.requested_new_date is not None
        occ.due_date = occ.requested_new_date
        occ.status = OccurrenceStatus.DEFERRED
        if wo:
            wo.due_date = occ.due_date
    else:
        occ.status = OccurrenceStatus.CANCELLED
        if wo and wo.status not in (WOStatus.COMPLETED, WOStatus.CLOSED, WOStatus.CANCELLED):
            from app.models.workorders import WOStatusHistory

            db.add(
                WOStatusHistory(
                    work_order_id=wo.id,
                    from_status=wo.status.value,
                    to_status=WOStatus.CANCELLED.value,
                    changed_by_id=user_id,
                    changed_at=utcnow(),
                    comment=f"PM cancelled: {occ.request_reason}",
                )
            )
            wo.status = WOStatus.CANCELLED
    plan = db.get(PMPlan, occ.pm_plan_id)
    if plan:
        _refresh_next_due(db, plan)
    audit(
        db,
        f"pm.{kind}_{'approved' if approve else 'rejected'}",
        user_id=user_id,
        plant_id=plant.id,
        entity_type="pm_occurrence",
        entity_id=occ.id,
    )
    return occ
