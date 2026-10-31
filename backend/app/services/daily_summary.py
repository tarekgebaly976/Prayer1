"""Daily summary e-mail: one message each morning per recipient, with the state of their departments.

Administrators decide everything: the plant switch, send days (frequency) and time (plant.admin) and who receives it (user.manage,
`Membership.daily_summary`). A member limited to departments gets those departments; a member with no department
restriction (planners, managers) gets the whole plant. Delivery goes through `notify()`: an in-app notification plus
the e-mail outbox, de-duplicated per user, plant and day, so a worker restart or a second replica never sends twice.
Nothing is sent from a test copy (CMMS_INSTANCE_LABEL set)."""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.assets import Asset
from app.models.enums import DONE_WO_STATUSES, OPEN_WO_STATUSES, AlertStatus, ConditionStatus, WOType
from app.models.identity import Membership, User
from app.models.pdm import ConditionAlert
from app.models.tenancy import Department, Plant
from app.models.workorders import WorkOrder
from app.services import kpi
from app.services.common import utcnow
from app.services.notifications import notify

KIND = "daily_summary"
TOP_OVERDUE = 10
COUNTERS = ("due_today", "overdue", "closed_yesterday", "open_breakdowns", "critical_alerts")

LABELS = {
    "en": {
        "subject": "Daily summary",
        "plant": "Whole plant",
        "due_today": "Work orders due today",
        "overdue": "Overdue work orders",
        "closed_yesterday": "Completed / closed yesterday",
        "closed_since": "Completed / closed since {d}",
        "open_breakdowns": "Open breakdowns",
        "critical_alerts": "Critical condition alerts",
        "pm_compliance": "PM compliance (month to date)",
        "na": "n/a",
        "most_overdue": "Most overdue",
        "days": "days",
        "open": "Open PlantPulse",
        "footer": "You receive this because an administrator added you to the daily summary.",
    },
    "ar": {
        "subject": "الملخص اليومي",
        "plant": "المصنع كله",
        "due_today": "Work orders مستحقة اليوم",
        "overdue": "Work orders متأخرة",
        "closed_yesterday": "أُنجزت / أُغلقت أمس",
        "closed_since": "أُنجزت / أُغلقت منذ {d}",
        "open_breakdowns": "أعطال (Breakdowns) مفتوحة",
        "critical_alerts": "Critical condition alerts",
        "pm_compliance": "PM compliance (من بداية الشهر)",
        "na": "غير متاح",
        "most_overdue": "الأكثر تأخيرًا",
        "days": "يوم",
        "open": "افتح PlantPulse",
        "footer": "يصلك هذا البريد لأن مسؤول النظام أضافك إلى الملخص اليومي.",
    },
}


@dataclass
class DeptStats:
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNTERS, 0))
    pm_compliance: float | None = None


@dataclass
class PlantStats:
    today: date
    since: date  # start of the "completed / closed" period: the day after the previous send day (yesterday when daily)
    departments: list[Department]
    by_dept: dict[uuid.UUID, DeptStats]
    overdue: list[tuple[uuid.UUID, str, str, date]]  # (department_id, number, title, due_date), most overdue first

    def total(self, dept_ids: list[uuid.UUID] | None) -> dict[str, int]:
        ids = dept_ids if dept_ids is not None else list(self.by_dept)
        return {c: sum(self.by_dept[d].counts[c] for d in ids if d in self.by_dept) for c in COUNTERS}


def suppressed_reason() -> str | None:
    """Why nothing may be sent from this installation, or None."""
    if get_settings().instance_label.strip():
        return "test copy (CMMS_INSTANCE_LABEL set)"
    return None


def send_days(plant: Plant) -> list[int]:
    return sorted({int(d) for d in (plant.daily_summary_days or []) if 1 <= int(d) <= 7}) or [1, 2, 3, 4, 5, 6, 7]


def period_start(plant: Plant, today: date) -> date:
    """First day covered by "completed / closed": the previous send day (yesterday when sent daily, a week ago weekly)."""
    days = send_days(plant)
    for back in range(1, 8):
        if (today - timedelta(days=back)).isoweekday() in days:
            return today - timedelta(days=back)
    return today - timedelta(days=1)


def collect(db: Session, plant: Plant, today: date) -> PlantStats:
    """All counters per department in a handful of grouped queries (not one query per recipient)."""
    tz = ZoneInfo(plant.timezone)
    since = period_start(plant, today)
    depts = list(
        db.execute(
            select(Department).where(Department.plant_id == plant.id, Department.is_active.is_(True)).order_by(Department.code)
        ).scalars()
    )
    by_dept = {d.id: DeptStats() for d in depts}

    def grouped(name: str, *conds) -> None:
        q = select(WorkOrder.department_id, func.count()).where(WorkOrder.plant_id == plant.id, *conds).group_by(WorkOrder.department_id)
        for dept_id, n in db.execute(q).all():
            if dept_id in by_dept:
                by_dept[dept_id].counts[name] = n

    is_open = WorkOrder.status.in_(OPEN_WO_STATUSES)
    grouped("due_today", is_open, WorkOrder.due_date == today)
    grouped("overdue", is_open, WorkOrder.due_date < today)
    grouped("open_breakdowns", is_open, WorkOrder.type == WOType.EMERGENCY)
    y0 = datetime.combine(since, time.min, tz)
    y1 = datetime.combine(today, time.min, tz)
    finished = func.coalesce(WorkOrder.completed_at, WorkOrder.closed_at)
    grouped("closed_yesterday", WorkOrder.status.in_(DONE_WO_STATUSES), finished >= y0, finished < y1)

    alerts = db.execute(
        select(Asset.department_id, func.count())
        .select_from(ConditionAlert)
        .join(Asset, Asset.id == ConditionAlert.asset_id)
        .where(
            ConditionAlert.plant_id == plant.id,
            ConditionAlert.severity == ConditionStatus.CRITICAL,
            ConditionAlert.status != AlertStatus.RESOLVED,
        )
        .group_by(Asset.department_id)
    ).all()
    for dept_id, n in alerts:
        if dept_id in by_dept:
            by_dept[dept_id].counts["critical_alerts"] = n

    month_start = today.replace(day=1)
    for d in depts:
        by_dept[d.id].pm_compliance = kpi.pm_compliance(db, kpi.Scope(plant=plant, start=month_start, end=today, department_id=d.id)).value

    overdue = [
        (r.department_id, r.number, r.title, r.due_date)
        for r in db.execute(
            select(WorkOrder.department_id, WorkOrder.number, WorkOrder.title, WorkOrder.due_date)
            .where(WorkOrder.plant_id == plant.id, is_open, WorkOrder.due_date < today)
            .order_by(WorkOrder.due_date, WorkOrder.number)
            .limit(500)
        ).all()
    ]
    return PlantStats(today=today, since=since, departments=depts, by_dept=by_dept, overdue=overdue)


def _pct(v: float | None, lab: dict) -> str:
    return lab["na"] if v is None else f"{v:.0f}%"


def compose(db: Session, plant: Plant, stats: PlantStats, user: User, dept_ids: list[uuid.UUID]) -> tuple[str, str]:
    """Subject and plain-text body for one recipient. `dept_ids` = [] means the whole plant."""
    lab = dict(LABELS["ar" if (user.locale or "").startswith("ar") else "en"])
    if stats.since != stats.today - timedelta(days=1):
        lab["closed_yesterday"] = lab["closed_since"].format(d=stats.since.isoformat())
    whole = not dept_ids
    depts = [d for d in stats.departments if whole or d.id in dept_ids]
    scope_ids = None if whole else [d.id for d in depts]
    width = max(len(lab[c]) for c in (*COUNTERS, "pm_compliance")) + 2
    lines = [f"{plant.name} — {lab['subject']} — {stats.today.isoformat()}", ""]

    def block(title: str, counts: dict[str, int], pm: str) -> None:
        lines.append(title)
        lines.append("-" * len(title))
        for c in COUNTERS:
            lines.append(f"  {lab[c]:<{width}}{counts[c]}")
        lines.append(f"  {lab['pm_compliance']:<{width}}{pm}")
        lines.append("")

    if whole or len(depts) > 1:
        pm_scope = kpi.Scope(plant=plant, start=stats.today.replace(day=1), end=stats.today, department_ids=tuple(scope_ids or ()))
        block(
            lab["plant"] if whole else ", ".join(d.code for d in depts),
            stats.total(scope_ids),
            _pct(kpi.pm_compliance(db, pm_scope).value, lab),
        )
    for d in depts:
        st = stats.by_dept[d.id]
        if whole and not any(st.counts.values()):
            continue  # whole-plant readers: departments with nothing to report are left out
        name = (d.name_ar or d.name) if lab["plant"] == LABELS["ar"]["plant"] else d.name
        block(f"{d.code} — {name}" if name != d.code else d.code, st.counts, _pct(st.pm_compliance, lab))

    codes = {d.id: d.code for d in depts}
    late = [o for o in stats.overdue if o[0] in codes][:TOP_OVERDUE]
    if late:
        lines.append(lab["most_overdue"])
        for dept_id, number, title, due in late:
            lines.append(f"  {number}  [{codes[dept_id]}]  {(stats.today - due).days} {lab['days']}  {title[:80]}")
        lines.append("")
    url = get_settings().public_url.rstrip("/")
    if url:
        lines.append(f"{lab['open']}: {url}/")
    lines.append(lab["footer"])
    totals = stats.total(scope_ids)
    subject = f"{lab['subject']} {stats.today.isoformat()}: {totals['overdue']} overdue, {totals['open_breakdowns']} breakdowns"
    return subject, "\n".join(lines)


def recipients(db: Session, plant: Plant) -> list[tuple[User, list[uuid.UUID]]]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.plant_id == plant.id, Membership.daily_summary.is_(True), Membership.is_active.is_(True), User.is_active.is_(True)
        )
        .order_by(User.full_name)
    ).all()
    return [(u, m.department_ids) for m, u in rows]


def due(plant: Plant, now: datetime) -> bool:
    """True once the plant-local clock has passed today's send time."""
    local = now.astimezone(ZoneInfo(plant.timezone))
    return local.time() >= plant.daily_summary_time


def run(db: Session, plant: Plant, now: datetime | None = None) -> dict:
    """Worker entry point (every few minutes): sends today's summary once the send time has passed."""
    now = now or utcnow()
    if (why := suppressed_reason()) is not None:
        return {"skipped": why}
    if not plant.daily_summary_enabled:
        return {"skipped": "disabled"}
    if now.astimezone(ZoneInfo(plant.timezone)).isoweekday() not in send_days(plant):
        return {"skipped": "not a send day"}
    if not due(plant, now):
        return {"skipped": "not yet"}
    people = recipients(db, plant)
    if not people:
        return {"sent": 0, "recipients": 0}
    today = now.astimezone(ZoneInfo(plant.timezone)).date()
    stats = collect(db, plant, today)
    sent = 0
    for user, dept_ids in people:
        subject, body = compose(db, plant, stats, user, dept_ids)
        sent += notify(
            db,
            plant.id,
            [user.id],
            kind=KIND,
            title=subject,
            body=body,
            dedupe_key=f"{KIND}:{plant.id}:{today.isoformat()}",
            email=True,
        )
    return {"sent": sent, "recipients": len(people)}
