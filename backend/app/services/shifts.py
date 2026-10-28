import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.enums import OPEN_WO_STATUSES, HandoverStatus, RosterKind, WOType
from app.models.identity import User
from app.models.pm import JobPlan, PMOccurrence, PMPlan
from app.models.shifts import RosterEntry, ShiftDefinition, ShiftHandover, ShiftPattern, Team, TeamMember
from app.models.tenancy import Plant
from app.models.workorders import WOAssignment, WorkOrder
from app.services.common import audit, utcnow
from app.services.notifications import notify, notify_permission


def generate_roster(db: Session, plant: Plant, team: Team, start: date, end: date) -> int:
    """Expand a team's rotation pattern into roster entries. Existing entries (e.g. leave) are never overwritten."""
    if team.pattern_id is None or team.pattern_anchor_date is None:
        raise DomainError("Team has no rotation pattern", "no_pattern", 422)
    if (end - start).days > 366:
        raise DomainError("Range too long (max 1 year)", "range", 422)
    pattern = db.get(ShiftPattern, team.pattern_id)
    assert pattern is not None
    shifts = {s.code: s for s in db.execute(select(ShiftDefinition).where(ShiftDefinition.plant_id == plant.id)).scalars()}
    members = list(db.execute(select(TeamMember.user_id).where(TeamMember.team_id == team.id)).scalars())
    n = 0
    d = start
    while d <= end:
        code = pattern.cycle[(d - team.pattern_anchor_date).days % len(pattern.cycle)]
        if code != "OFF":
            sd = shifts.get(code)
            if sd is None:
                raise DomainError(f"Pattern references unknown shift {code}", "bad_pattern", 422)
            for uid in members:
                res = db.execute(
                    pg_insert(RosterEntry)
                    .values(
                        id=uuid.uuid4(),
                        plant_id=plant.id,
                        user_id=uid,
                        work_date=d,
                        shift_id=sd.id,
                        kind=RosterKind.WORK,
                        hours=sd.paid_hours,
                        team_id=team.id,
                        source="pattern",
                    )
                    .on_conflict_do_nothing(index_elements=["user_id", "work_date"])
                    .returning(RosterEntry.id)
                )
                n += res.first() is not None
        d += timedelta(days=1)
    return n


def shift_window(plant: Plant, sd: ShiftDefinition, day: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(plant.timezone)
    s = datetime.combine(day, sd.start_time, tz)
    e = datetime.combine(day + timedelta(days=1) if sd.end_time <= sd.start_time else day, sd.end_time, tz)
    return s, e


def manpower(db: Session, plant: Plant, start: date, end: date, department_id: uuid.UUID | None = None) -> list[dict]:
    """Per-day supply (rostered hours by trade) vs demand (estimated hours of WOs planned that day).
    Flags shortages and trades with demand but no rostered technician."""
    tz = ZoneInfo(plant.timezone)
    supply: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    people: dict[date, int] = defaultdict(int)
    rows = db.execute(
        select(RosterEntry, User)
        .join(User, User.id == RosterEntry.user_id)
        .where(RosterEntry.plant_id == plant.id, RosterEntry.work_date >= start, RosterEntry.work_date <= end)
    ).all()
    for r, u in rows:
        if r.kind in (RosterKind.WORK, RosterKind.OVERTIME, RosterKind.CALLOUT):
            supply[r.work_date][u.trade or "general"] += float(r.hours) + float(r.overtime_hours) + float(r.callout_hours)
            people[r.work_date] += 1
    demand: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    s_utc = datetime.combine(start, time.min, tz)
    e_utc = datetime.combine(end + timedelta(days=1), time.min, tz)
    q = select(WorkOrder).where(
        WorkOrder.plant_id == plant.id,
        WorkOrder.status.in_(OPEN_WO_STATUSES),
        or_(  # planned start when scheduled; otherwise the due date (e.g. PM work orders the scheduler created)
            and_(WorkOrder.planned_start >= s_utc, WorkOrder.planned_start < e_utc),
            and_(WorkOrder.planned_start.is_(None), WorkOrder.due_date >= start, WorkOrder.due_date <= end),
        ),
    )
    if department_id:
        q = q.where(WorkOrder.department_id == department_id)
    for wo in db.execute(q).scalars():
        day = wo.planned_start.astimezone(tz).date() if wo.planned_start else wo.due_date
        assert day is not None
        trade = "general"
        if wo.pm_occurrence_id:
            jp = db.execute(
                select(JobPlan)
                .join(PMPlan, PMPlan.job_plan_id == JobPlan.id)
                .join(PMOccurrence, PMOccurrence.pm_plan_id == PMPlan.id)
                .where(PMOccurrence.id == wo.pm_occurrence_id)
            ).scalar_one_or_none()
            trade = jp.trade if jp and jp.trade else "general"
        remaining = max(float(wo.estimated_hours or 0) - float(wo.actual_labor_hours or 0), 0)
        demand[day][trade] += remaining
    out = []
    d = start
    while d <= end:
        sup, dem = supply.get(d, {}), demand.get(d, {})
        flags = []
        for trade, hrs in dem.items():
            have = sup.get(trade, 0) + (sup.get("general", 0) if trade == "general" else 0)
            if have == 0 and hrs > 0:
                flags.append(f"No rostered {trade} technician for {hrs:.1f} h of planned work")
            elif hrs > have:
                flags.append(f"{trade}: demand {hrs:.1f} h exceeds rostered {have:.1f} h")
        out.append(
            {
                "date": d.isoformat(),
                "people": people.get(d, 0),
                "supply_hours": dict(sup),
                "demand_hours": dict(dem),
                "total_supply": round(sum(sup.values()), 2),
                "total_demand": round(sum(dem.values()), 2),
                "flags": flags,
            }
        )
        d += timedelta(days=1)
    return out


def open_breakdowns(db: Session, plant: Plant, department_id: uuid.UUID) -> list[WorkOrder]:
    return list(
        db.execute(
            select(WorkOrder)
            .where(
                WorkOrder.plant_id == plant.id,
                WorkOrder.department_id == department_id,
                WorkOrder.type.in_([WOType.EMERGENCY, WOType.CORRECTIVE]),
                WorkOrder.status.in_(OPEN_WO_STATUSES),
            )
            .order_by(WorkOrder.priority, WorkOrder.created_at)
        ).scalars()
    )


def submit_handover(db: Session, plant: Plant, h: ShiftHandover, user_id: uuid.UUID) -> ShiftHandover:
    if h.status != HandoverStatus.DRAFT:
        raise DomainError("Handover already submitted", "invalid_state", 409)
    if h.outgoing_user_id != user_id:
        raise DomainError("Only the outgoing person can submit the handover", "forbidden", 403)
    h.open_work_order_ids = [str(w.id) for w in open_breakdowns(db, plant, h.department_id)]
    h.status = HandoverStatus.SUBMITTED
    h.submitted_at = utcnow()
    if h.incoming_user_id:
        notify(
            db,
            plant.id,
            [h.incoming_user_id],
            kind="handover",
            title="Shift handover submitted",
            body=h.summary[:200],
            link=f"/shifts/handovers/{h.id}",
            dedupe_key=f"handover:{h.id}",
        )
    notify_permission(
        db,
        plant.id,
        "handover.confirm",
        kind="handover",
        title="Shift handover awaiting confirmation",
        body=h.summary[:200],
        link=f"/shifts/handovers/{h.id}",
        dedupe_key=f"handover:{h.id}",
    )
    audit(db, "handover.submit", user_id=user_id, plant_id=plant.id, entity_type="handover", entity_id=h.id)
    return h


def confirm_handover(db: Session, plant: Plant, h: ShiftHandover, user_id: uuid.UUID, comment: str | None) -> ShiftHandover:
    if h.status != HandoverStatus.SUBMITTED:
        raise DomainError("Handover must be submitted before confirmation", "invalid_state", 409)
    if h.outgoing_user_id == user_id:
        raise DomainError("The outgoing person cannot confirm their own handover", "four_eyes", 403)
    h.status = HandoverStatus.CONFIRMED
    h.confirmed_by_id = user_id
    h.confirmed_at = utcnow()
    h.supervisor_comment = comment
    h.is_locked = True
    audit(db, "handover.confirm", user_id=user_id, plant_id=plant.id, entity_type="handover", entity_id=h.id)
    return h


def user_assignments_on(db: Session, user_id: uuid.UUID, start: datetime, end: datetime) -> list[WorkOrder]:
    return list(
        db.execute(
            select(WorkOrder)
            .join(WOAssignment, WOAssignment.work_order_id == WorkOrder.id)
            .where(
                WOAssignment.user_id == user_id,
                WorkOrder.status.in_(OPEN_WO_STATUSES),
                WorkOrder.planned_start < end,
                WorkOrder.planned_end > start,
            )
        ).scalars()
    )
