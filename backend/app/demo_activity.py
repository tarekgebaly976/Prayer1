"""A living plant for the public demo: six months of maintenance history and today's open work, generated relative to
the day the demo is loaded (scripts/demo.sh reloads it every night, so the demo always looks like "now").

SAMPLE data only, in the DEMO organization created by app.seed.seed_demo. The numbers are illustrative and must not be
presented as the performance of a real plant. Deterministic (fixed random seed) apart from the dates."""

import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import Asset, DowntimeEvent, FailureCode
from app.models.enums import (
    AlertStatus,
    FailureCodeKind,
    FrequencyUnit,
    LubeTaskStatus,
    OccurrenceStatus,
    PMTrigger,
    Priority,
    RequestStatus,
    Technique,
    WOStatus,
    WOType,
)
from app.models.identity import User
from app.models.inventory import PartUsage
from app.models.lubrication import LubeRoute, LubeTask, Lubricant, LubricationPoint
from app.models.pdm import ConditionAlert, MeasurementPoint
from app.models.pm import PMOccurrence, PMPlan
from app.models.system import MaintenanceBudget, ProductionRecord
from app.models.tenancy import Plant
from app.models.workorders import WOAssignment, WOLabor, WorkOrder, WorkRequest, WOService, WOStatusHistory
from app.services.assets import new_qr_token
from app.services.common import next_number, plant_today, utcnow
from app.services.pdm import record_reading
from app.services.pm import plan_occurrences

D = Decimal

# Breakdowns of the last six months: (asset, title, problem, cause, remedy, downtime h, labour h, parts SAR, trade tech)
BREAKDOWNS = [
    ("PM1-WIRE-UTW-DR1-BRG-DS", "DR1 drive-side bearing running hot, machine stopped", "OVH", "LUB", "RELUB", 3.5, 5, 0, "tech1"),
    ("SP-L1-PULP-MTR", "Pulper motor tripped on overload", "TRIP", "ELEC", "REPAIR", 2.0, 3, 0, "tech3"),
    ("PM1-PRESS-SHOE-HPU", "Shoe press HPU oil leak at pressure line", "LEAK", "WEAR", "REPL", 4.0, 6, 1450, "tech2"),
    ("SP-L1-REF1", "Refiner high vibration, stopped by operator", "VIB", "MIS", "ALIGN", 5.5, 8, 380, "tech1"),
    ("SP-L1-REF1", "Refiner vibration again after restart", "VIB", "MIS", "ALIGN", 3.0, 5, 0, "tech1"),
    ("PM1-DRY-G1-CYL01-JNT", "Rotary joint leaking steam", "LEAK", "WEAR", "REPL", 2.5, 4, 2200, "tech2"),
    ("UTIL-AIR-C1", "Air compressor 1 stopped on high temperature", "OVH", "CONT", "REPAIR", 3.0, 4, 610, "tech3"),
    ("PM1-WIRE-UTW-DR1-GBX", "DR1 gearbox abnormal noise", "NOISE", "WEAR", "REPL", 7.0, 12, 9800, "tech1"),
    ("FH-L1-WIND", "Winder drive fault, line stopped", "TRIP", "ELEC", "ADJ", 1.5, 2, 0, "tech3"),
    ("WWTP-L1-AER1", "Aeration blower 1 high vibration", "VIB", "LUB", "RELUB", 2.0, 3, 0, "tech2"),
    ("PM1-PRESS-SHOE-HPU", "HPU filter blocked, low pressure trip", "TRIP", "CONT", "REPL", 1.5, 2, 610, "tech2"),
    ("PM1-WIRE-UTW-DR1-BRG-TS", "DR1 tending-side bearing noise", "NOISE", "LUB", "RELUB", 2.0, 3, 0, "tech1"),
    ("SP-L1-PULP-MTR", "Pulper motor earth fault alarm", "TRIP", "ELEC", "REPAIR", 4.5, 6, 5200, "tech3"),
    ("UTIL-AIR-C1", "Compressor oil carry-over, stopped", "LEAK", "WEAR", "REPL", 2.5, 4, 610, "tech2"),
    ("PM1-DRY-G1-CYL01-JNT", "Rotary joint leak, second time this quarter", "LEAK", "WEAR", "REPL", 3.0, 4, 2200, "tech2"),
    ("FH-L1-WIND", "Winder unwind brake overheating", "OVH", "WEAR", "ADJ", 1.0, 2, 0, "tech1"),
    ("PM1-WIRE-UTW-DR1-BRG-DS", "DR1 DS bearing temperature alarm", "OVH", "LUB", "RELUB", 1.5, 2, 0, "tech1"),
    ("SP-L1-REF1", "Refiner plates worn, low efficiency and vibration", "VIB", "WEAR", "REPL", 6.0, 10, 3800, "tech.sp"),
]

# Planned / corrective work completed in the last six months: (asset, type, title, labour h, parts SAR, tech)
COMPLETED_WORK = [
    ("PM1-WIRE-UTW-DR1-GBX", WOType.PREVENTIVE, "DR1 gearbox oil sample and top-up", 1.5, 120, "tech1"),
    ("PM1-PRESS-SHOE-HPU", WOType.PREVENTIVE, "HPU filter change (planned)", 2, 1220, "tech2"),
    ("SP-L1-PULP-MTR", WOType.INSPECTION, "Pulper motor thermography", 1, 0, "tech3"),
    ("UTIL-AIR-C1", WOType.PREVENTIVE, "Compressor 4,000 h service", 6, 2400, "tech2"),
    ("FH-L1-WIND", WOType.CORRECTIVE, "Replace worn winder core chuck", 4, 1800, "tech1"),
    ("WWTP-L1-AER1", WOType.PREVENTIVE, "Blower belt tension and alignment", 2, 0, "tech2"),
    ("EAI-DCS-SUB1", WOType.INSPECTION, "MV substation infrared survey", 3, 0, "tech3"),
    ("PM1-DRY-G1", WOType.CORRECTIVE, "Replace dryer doctor blade holder", 5, 2600, "tech1"),
    ("SP-L1-REF1", WOType.PREDICTIVE, "Refiner vibration analysis route", 1, 0, "tech.sp"),
    ("PM1-REEL", WOType.CORRECTIVE, "Reel spool arm hydraulic hose replacement", 3, 450, "tech2"),
    ("EAI-DCS", WOType.IMPROVEMENT, "Add bearing temperature trend to DCS screen", 6, 0, "tech3"),
    ("UTIL-AIR", WOType.CORRECTIVE, "Repair compressed air leak in PM1 header", 3, 300, "tech2"),
    ("PM1-WIRE", WOType.INSPECTION, "Wire section shutdown inspection", 8, 0, "tech1"),
    ("FH-L1", WOType.PREVENTIVE, "Finishing line conveyor lubrication and check", 2, 90, "tech1"),
    ("SP-L1-PULP", WOType.CORRECTIVE, "Pulper rotor bolts re-torque", 2, 0, "tech.sp"),
    ("WWTP-L1", WOType.CORRECTIVE, "Effluent pump seal replacement", 4, 950, "tech2"),
]

# Today's open work: (asset, type, priority, status, title, due in days (None = no date), assigned tech, lead tech)
OPEN_WORK = [
    (
        "SP-L1-PULP-MTR",
        WOType.EMERGENCY,
        Priority.P1_EMERGENCY,
        WOStatus.IN_PROGRESS,
        "Pulper motor tripped, will not restart",
        0,
        "tech3",
        None,
    ),
    (
        "PM1-WIRE-UTW-DR1-BRG-DS",
        WOType.PREDICTIVE,
        Priority.P2_HIGH,
        WOStatus.SCHEDULED,
        "Vibration rising on DR1 DS bearing: plan bearing change",
        3,
        "tech1",
        None,
    ),
    (
        "PM1-PRESS-SHOE-HPU",
        WOType.CORRECTIVE,
        Priority.P2_HIGH,
        WOStatus.IN_PROGRESS,
        "HPU return line weeping at fitting",
        1,
        "tech2",
        None,
    ),
    (
        "UTIL-AIR-C1",
        WOType.CORRECTIVE,
        Priority.P3_MEDIUM,
        WOStatus.ON_HOLD,
        "Replace compressor intake valve (waiting for part)",
        5,
        "tech2",
        None,
    ),
    ("FH-L1-WIND", WOType.CORRECTIVE, Priority.P3_MEDIUM, WOStatus.SCHEDULED, "Winder rider roll bearing noise", -2, "tech1", None),
    (
        "PM1-DRY-G1-CYL01-JNT",
        WOType.CORRECTIVE,
        Priority.P3_MEDIUM,
        WOStatus.PLANNED,
        "Rotary joint: replace carbon seal ring",
        6,
        None,
        None,
    ),
    ("WWTP-L1-AER1", WOType.PREVENTIVE, Priority.P3_MEDIUM, WOStatus.APPROVED, "Blower 1 quarterly service", 4, "tech2", None),
    (
        "SP-L1-REF1",
        WOType.CORRECTIVE,
        Priority.P2_HIGH,
        WOStatus.AWAITING_APPROVAL,
        "Replace refiner plates (cost above limit)",
        10,
        None,
        None,
    ),
    (
        "EAI-DCS-SUB1",
        WOType.IMPROVEMENT,
        Priority.P4_LOW,
        WOStatus.AWAITING_APPROVAL,
        "Install arc-flash labels on MV panels",
        21,
        None,
        None,
    ),
    (
        "PM1-REEL",
        WOType.CORRECTIVE,
        Priority.P3_MEDIUM,
        WOStatus.AWAITING_REVIEW,
        "Reel spool clamp adjusted: supervisor check",
        0,
        "tech1",
        None,
    ),
    (
        "PM1-WIRE-UTW-DR1-GBX",
        WOType.INSPECTION,
        Priority.P3_MEDIUM,
        WOStatus.SCHEDULED,
        "Gearbox oil sample for analysis",
        -4,
        "tech1",
        None,
    ),
    ("FH-L1", WOType.CORRECTIVE, Priority.P4_LOW, WOStatus.TRIAGE, "Guard on conveyor 3 loose", None, None, None),
    ("UTIL-AIR", WOType.CORRECTIVE, Priority.P3_MEDIUM, WOStatus.TRIAGE, "Air leak near PM1 reel", None, None, None),
]

REQUESTS = [  # new work requests waiting for triage: (asset, title, symptoms, priority, breakdown, by)
    (
        "PM1-DRY-G1-CYL01-JNT",
        "Steam leak at dryer cylinder 01",
        "Visible steam at the joint, hissing noise",
        Priority.P2_HIGH,
        False,
        "production",
    ),
    ("SP-L1-PULP", "Pulper discharge valve slow to open", "Takes about 20 s to open fully", Priority.P3_MEDIUM, False, "tech.sp"),
    ("WWTP-L1-AER1", "Oil drops under blower 1", "Small puddle under the gearbox", Priority.P3_MEDIUM, False, "tech2"),
]

EXTRA_PM = [  # (code, name, asset, unit, interval)
    ("PM-REF1-M", "Refiner No. 1 monthly inspection", "SP-L1-REF1", FrequencyUnit.MONTH, 1),
    ("PM-C1-W", "Air compressor 1 weekly checks", "UTIL-AIR-C1", FrequencyUnit.WEEK, 1),
    ("PM-AER1-M", "Aeration blower 1 monthly service", "WWTP-L1-AER1", FrequencyUnit.MONTH, 1),
]

EXTRA_LUBE = [  # (code, asset, component, grams, every n days)
    ("LP-REF1-NDE", "SP-L1-REF1", "Refiner non-drive-end bearing", 30, 7),
    ("LP-PULP-MTR", "SP-L1-PULP-MTR", "Pulper motor bearings", 45, 14),
    ("LP-AER1", "WWTP-L1-AER1", "Blower 1 bearings", 20, 7),
    ("LP-WIND", "FH-L1-WIND", "Winder drum bearings", 25, 14),
]

EXTRA_POINTS = [  # (code, name, asset, technique, unit, warning, alarm)
    ("VIB-REF1-NDE", "Refiner NDE bearing velocity", "SP-L1-REF1", Technique.VIBRATION, "mm/s", 4.5, 7.1),
    ("TMP-C1-OUT", "Compressor 1 discharge temperature", "UTIL-AIR-C1", Technique.TEMPERATURE, "°C", 95, 105),
    ("VIB-AER1", "Blower 1 bearing velocity", "WWTP-L1-AER1", Technique.VIBRATION, "mm/s", 4.5, 7.1),
]


def add_demo_activity(db: Session, plant: Plant) -> dict:
    rnd = random.Random(20261102)
    tz = ZoneInfo(plant.timezone)
    today = plant_today(plant)
    now = utcnow()

    def at(day: date, hour: float) -> datetime:
        return datetime.combine(day, time(int(hour), int((hour % 1) * 60)), tzinfo=tz)

    assets = {a.code: a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    users = {u.email.split("@")[0]: u for u in db.execute(select(User).where(User.email.like("%@demo.example.com"))).scalars()}
    codes = {(c.kind, c.code): c for c in db.execute(select(FailureCode).where(FailureCode.plant_id == plant.id)).scalars()}
    planner, sup = users["planner"], users["mech.sup"]

    def labor(wo: WorkOrder, tech: User, day: date, hours: float) -> None:
        rate = D(str(tech.hourly_rate or 85))
        cost = (rate * D(str(hours))).quantize(D("0.01"))
        db.add(
            WOLabor(
                work_order_id=wo.id,
                user_id=tech.id,
                work_date=day,
                hours=D(str(hours)),
                rate=rate,
                cost=cost,
                created_at=at(day, 15),
                created_by_id=tech.id,
            )
        )
        wo.actual_labor_hours = (wo.actual_labor_hours or 0) + D(str(hours))
        wo.actual_labor_cost = (wo.actual_labor_cost or 0) + cost

    def parts_used(wo: WorkOrder, day: date, amount: float, what: str) -> None:
        if amount:
            db.add(
                PartUsage(
                    plant_id=plant.id,
                    work_order_id=wo.id,
                    asset_id=wo.asset_id,
                    description=what,
                    quantity=D(1),
                    uom="EA",
                    unit_cost=D(str(amount)),
                    total_cost=D(str(amount)),
                    used_on=day,
                    created_at=at(day, 16),
                    created_by_id=planner.id,
                )
            )

    def history(wo: WorkOrder, steps: list[tuple[WOStatus, datetime, User]]) -> None:
        prev = None
        for st, when, who in steps:
            db.add(WOStatusHistory(work_order_id=wo.id, from_status=prev, to_status=st.value, changed_by_id=who.id, changed_at=when))
            prev = st.value

    def new_wo(asset_code: str, wtype: WOType, title: str, prio: Priority, status: WOStatus, created: datetime, **kw) -> WorkOrder:
        a = assets[asset_code]
        wo = WorkOrder(
            id=uuid.uuid4(),
            plant_id=plant.id,
            number=next_number(db, plant, "WO"),
            type=wtype,
            status=status,
            priority=prio,
            asset_id=a.id,
            department_id=a.department_id,
            title=title,
            currency=plant.currency,
            created_by_id=planner.id,
            actual_labor_hours=D(0),
            actual_labor_cost=D(0),
            **kw,
        )
        db.add(wo)
        db.flush()
        wo.created_at = created
        return wo

    # ---- 1. History: everything that happened in the last 180 days, oldest first -----------------------------------
    events: list[tuple[date, str, tuple]] = []
    for i, b in enumerate(BREAKDOWNS):
        events.append((today - timedelta(days=175 - i * 9 - rnd.randint(0, 4)), "bd", b))
    for i, c in enumerate(COMPLETED_WORK):
        events.append((today - timedelta(days=170 - i * 10 - rnd.randint(0, 5)), "wk", c))
    seen_assets: dict[str, date] = {}
    for day, kind, row in sorted(events, key=lambda e: e[0]):
        if kind == "bd":
            code, title, prob, cause, rem, down_h, lab_h, parts, tk = row
            start = at(day, rnd.choice([2.5, 7.25, 10.5, 14.0, 19.75, 23.0]))
            end = start + timedelta(hours=down_h)
            repeat = code in seen_assets and (day - seen_assets[code]).days <= 30
            seen_assets[code] = day
            wo = new_wo(
                code,
                WOType.EMERGENCY,
                title,
                Priority.P1_EMERGENCY,
                WOStatus.CLOSED,
                start,
                problem_code_id=codes[(FailureCodeKind.PROBLEM, prob)].id,
                cause_code_id=codes[(FailureCodeKind.CAUSE, cause)].id,
                remedy_code_id=codes[(FailureCodeKind.REMEDY, rem)].id,
                actual_start=start + timedelta(minutes=20),
                actual_end=end,
                completed_at=end,
                closed_at=end + timedelta(hours=20),
                downtime_hours=D(str(down_h)),
                actual_material_cost=D(parts),
                is_repeat_failure=repeat,
                supervisor_id=sup.id,
                findings="Found on arrival: " + title.lower() + ".",
                corrective_action="Repaired and tested; machine returned to production.",
                production_loss_tons=D(str(round(down_h * 9.5, 1))),
            )
            db.add(
                DowntimeEvent(
                    plant_id=plant.id,
                    asset_id=assets[code].id,
                    work_order_id=wo.id,
                    started_at=start,
                    ended_at=end,
                    is_failure=True,
                    is_planned=False,
                    reason=title,
                    production_loss_tons=wo.production_loss_tons,
                    created_by_id=sup.id,
                )
            )
            labor(wo, users[tk], day, lab_h)
            parts_used(wo, day, parts, "Spare parts used in the repair")
            history(
                wo,
                [
                    (WOStatus.TRIAGE, start, users["production"]),
                    (WOStatus.IN_PROGRESS, start + timedelta(minutes=20), users[tk]),
                    (WOStatus.COMPLETED, end, users[tk]),
                    (WOStatus.CLOSED, end + timedelta(hours=20), sup),
                ],
            )
        else:
            code, wtype, title, lab_h, parts, tk = row
            start = at(day, 8.0)
            end = start + timedelta(hours=lab_h)
            wo = new_wo(
                code,
                wtype,
                title,
                Priority.P3_MEDIUM,
                WOStatus.CLOSED,
                start - timedelta(days=3),
                due_date=day,
                planned_start=at(day, 7),
                planned_end=at(day, 17) + timedelta(days=1 if rnd.random() < 0.8 else -1),
                actual_start=start,
                actual_end=end,
                completed_at=end,
                closed_at=end + timedelta(days=1),
                actual_material_cost=D(parts),
                supervisor_id=sup.id,
                estimated_hours=D(str(lab_h)),
            )
            labor(wo, users[tk], day, lab_h)
            parts_used(wo, day, parts, "Materials")
            history(
                wo,
                [
                    (WOStatus.APPROVED, start - timedelta(days=3), planner),
                    (WOStatus.SCHEDULED, start - timedelta(days=2), planner),
                    (WOStatus.IN_PROGRESS, start, users[tk]),
                    (WOStatus.COMPLETED, end, users[tk]),
                    (WOStatus.CLOSED, end + timedelta(days=1), sup),
                ],
            )

    # Contractor work: the big jobs of the half year (cost per ton, budget).
    for days_ago, code, title, supplier_work, cost in [
        (150, "PM1-PRESS-SHOE", "Shoe press belt change (planned stop)", "OEM service team, 2 days", 186000),
        (118, "PM1-WIRE-UTW-DR1-GBX", "DR1 gearbox overhaul", "Gearbox workshop overhaul", 94500),
        (83, "PM1-DRY-G1", "Dryer group 1 felt change", "Felt supplier installation", 72000),
        (41, "SP-L1-PULP-MTR", "Pulper motor rewinding", "Motor repair workshop", 58000),
        (12, "EAI-DCS-SUB1", "MV substation annual testing", "Electrical testing contractor", 36500),
    ]:
        day = today - timedelta(days=days_ago)
        wo = new_wo(
            code,
            WOType.SHUTDOWN if "planned stop" in title else WOType.CORRECTIVE,
            title,
            Priority.P2_HIGH,
            WOStatus.CLOSED,
            at(day - timedelta(days=10), 8),
            due_date=day,
            planned_start=at(day, 6),
            planned_end=at(day + timedelta(days=2), 18),
            actual_start=at(day, 6),
            actual_end=at(day + timedelta(days=1), 17),
            completed_at=at(day + timedelta(days=1), 17),
            closed_at=at(day + timedelta(days=2), 10),
            supervisor_id=sup.id,
            estimated_hours=D(16),
        )
        labor(wo, users["tech1"], day, 8)
        labor(wo, users["tech2"], day, 8)
        db.add(
            WOService(
                work_order_id=wo.id,
                description=supplier_work,
                cost=D(cost),
                po_reference=f"PO-DEMO-{days_ago:03d}",
                created_at=at(day + timedelta(days=1), 17),
                created_by_id=planner.id,
            )
        )

    # ---- 2. Weekly PM on Drive Roll No.1: twelve past weeks, mostly on time (PM compliance) ------------------------
    pm1 = db.execute(select(PMPlan).where(PMPlan.plant_id == plant.id, PMPlan.code == "PM-DR1-W")).scalar_one()
    for wk in range(12, 0, -1):
        due = today - timedelta(weeks=wk)
        late = wk == 7
        missed = wk == 3
        occ = PMOccurrence(
            plant_id=plant.id,
            pm_plan_id=pm1.id,
            occurrence_key=f"D:{due.isoformat()}",
            due_date=due,
            original_due_date=due,
            status=OccurrenceStatus.GENERATED if missed else OccurrenceStatus.COMPLETED,
        )
        if not missed:
            done = due + timedelta(days=5) if late else due
            wo = new_wo(
                "PM1-WIRE-UTW-DR1",
                WOType.PREVENTIVE,
                pm1.name,
                Priority.P3_MEDIUM,
                WOStatus.CLOSED,
                at(due - timedelta(days=2), 6),
                due_date=due,
                planned_start=at(due, 8),
                planned_end=at(due, 17),
                actual_start=at(done, 9),
                actual_end=at(done, 10.5),
                completed_at=at(done, 10.5),
                closed_at=at(done, 16),
                estimated_hours=D("1.5"),
            )
            labor(wo, users["tech1"], done, 1.5)
            occ.completed_date, occ.completed_at, occ.work_order_id = done, at(done, 10.5), wo.id
        db.add(occ)
    db.flush()
    pm1.last_completed_date = today - timedelta(weeks=1)
    # One planner request waiting for the manager: postpone next week's PM (PM approvals pending).
    nxt = (
        db.execute(
            select(PMOccurrence).where(PMOccurrence.pm_plan_id == pm1.id, PMOccurrence.due_date > today).order_by(PMOccurrence.due_date)
        )
        .scalars()
        .first()
    )
    if nxt is not None:
        nxt.status = OccurrenceStatus.DEFERRAL_REQUESTED
        nxt.requested_by_id, nxt.requested_new_date = planner.id, nxt.due_date + timedelta(days=4)
        nxt.request_reason = "Machine stop moved to Thursday: inspect during the planned stop."
    jp = pm1.job_plan_id
    for code, name, asset, funit, interval in EXTRA_PM:
        plan = PMPlan(
            plant_id=plant.id,
            code=code,
            name=name,
            asset_id=assets[asset].id,
            job_plan_id=jp,
            trigger=PMTrigger.CALENDAR,
            frequency_unit=funit,
            frequency_interval=interval,
            start_date=today + timedelta(days=rnd.randint(1, 9)),
            horizon_days=60,
            lead_days=3,
        )
        db.add(plan)
        db.flush()
        plan_occurrences(db, plant, plan, today)

    # Routine rounds: short planned inspections and PMs on the main machines, about twice a week.
    rounds = [
        ("UTIL-AIR-C1", WOType.PREVENTIVE, "Air compressor 1 weekly checks"),
        ("SP-L1-REF1", WOType.INSPECTION, "Refiner condition round"),
        ("WWTP-L1-AER1", WOType.PREVENTIVE, "Blower 1 weekly checks"),
        ("PM1-PRESS-SHOE-HPU", WOType.INSPECTION, "HPU oil level and filter check"),
        ("FH-L1-WIND", WOType.INSPECTION, "Winder safety and condition round"),
        ("SP-L1-PULP-MTR", WOType.INSPECTION, "Pulper motor round"),
    ]
    for k in range(48):
        day = today - timedelta(days=170 - k * 3.5)
        if day >= today:
            break
        code, wtype, title = rounds[k % len(rounds)]
        tk = users[("tech2", "tech.sp", "tech2", "tech2", "tech1", "tech3")[k % 6]]
        hrs = rnd.choice([1, 1, 1.5, 2])
        done = day + timedelta(days=1 if rnd.random() < 0.1 else 0)
        wo = new_wo(
            code,
            wtype,
            title,
            Priority.P4_LOW,
            WOStatus.CLOSED,
            at(day - timedelta(days=4), 6),
            due_date=day,
            planned_start=at(day, 8),
            planned_end=at(day, 17),
            actual_start=at(done, 9),
            actual_end=at(done, 9 + hrs),
            completed_at=at(done, 9 + hrs),
            closed_at=at(done, 16),
            estimated_hours=D(str(hrs)),
        )
        labor(wo, tk, done, hrs)

    # Production of Paper Machine 1 (OEE, cost per ton): 24 h planned, minus the breakdowns of that day and small stops.
    pm_dept = assets["PM1"].department_id
    lost: dict[date, float] = {}
    for e in db.execute(select(DowntimeEvent).where(DowntimeEvent.plant_id == plant.id, DowntimeEvent.ended_at.is_not(None))).scalars():
        if e.asset_id in {a.id for c, a in assets.items() if c.startswith("PM1")}:
            d0 = e.started_at.astimezone(tz).date()
            lost[d0] = lost.get(d0, 0) + ((e.ended_at or e.started_at) - e.started_at).total_seconds() / 3600
    for k in range(180, 0, -1):
        d0 = today - timedelta(days=k)
        run = max(0.0, 24 - lost.get(d0, 0) - rnd.uniform(0.2, 1.2))
        tons = run * 9.5 * rnd.uniform(0.9, 0.97)
        db.add(
            ProductionRecord(
                plant_id=plant.id,
                department_id=pm_dept,
                asset_id=assets["PM1"].id,
                record_date=d0,
                tons_produced=D(str(round(tons, 1))),
                good_tons=D(str(round(tons * rnd.uniform(0.96, 0.985), 1))),
                planned_production_hours=D(24),
                run_hours=D(str(round(run, 2))),
                ideal_rate_tph=D("9.5"),
                created_by_id=users["production"].id,
            )
        )
    # Maintenance budget for the plant, month by month.
    m = (today - timedelta(days=185)).replace(day=1)
    while m <= today:
        db.add(
            MaintenanceBudget(plant_id=plant.id, department_id=None, year=m.year, month=m.month, amount=D(85000), currency=plant.currency)
        )
        m = (m + timedelta(days=32)).replace(day=1)
    db.flush()

    # ---- 3. Today's open work ---------------------------------------------------------------------------------------
    open_count = 0
    for code, wtype, prio, status, title, due_in, tk, _ in OPEN_WORK:
        created = (
            now - timedelta(hours=3) if wtype == WOType.EMERGENCY else now - timedelta(days=rnd.randint(2, 9), hours=rnd.randint(0, 8))
        )
        wo = new_wo(
            code,
            wtype,
            title,
            prio,
            status,
            created,
            due_date=today + timedelta(days=due_in) if due_in is not None else None,
            supervisor_id=(users["elec.sup"] if tk == "tech3" else sup).id if tk else None,
            estimated_hours=D(str(rnd.choice([2, 3, 4, 6]))),
        )
        steps = [(WOStatus.TRIAGE, created, users["production"])]
        if status not in (WOStatus.TRIAGE,):
            steps.append(
                (
                    WOStatus.AWAITING_APPROVAL if status == WOStatus.AWAITING_APPROVAL else WOStatus.APPROVED,
                    created + timedelta(hours=2),
                    planner,
                )
            )
        if status in (WOStatus.PLANNED, WOStatus.SCHEDULED, WOStatus.IN_PROGRESS, WOStatus.ON_HOLD, WOStatus.AWAITING_REVIEW):
            steps.append((WOStatus.PLANNED, created + timedelta(hours=5), planner))
        if status in (WOStatus.SCHEDULED, WOStatus.IN_PROGRESS, WOStatus.ON_HOLD, WOStatus.AWAITING_REVIEW):
            steps.append((WOStatus.SCHEDULED, created + timedelta(hours=8), planner))
        tech = users[tk] if tk else planner
        if status in (WOStatus.IN_PROGRESS, WOStatus.ON_HOLD, WOStatus.AWAITING_REVIEW):
            started = now - timedelta(hours=2 if wtype == WOType.EMERGENCY else 20)
            wo.actual_start = started
            steps.append((WOStatus.IN_PROGRESS, started, tech))
        if status == WOStatus.ON_HOLD:
            steps.append((WOStatus.ON_HOLD, now - timedelta(hours=6), tech))
        if status == WOStatus.AWAITING_REVIEW:
            steps.append((WOStatus.AWAITING_REVIEW, now - timedelta(hours=1), tech))
            labor(wo, tech, today, 2.5)
        if wtype == WOType.EMERGENCY:
            wo.symptoms = "Motor tripped on overload during start-up; smell of burning at terminal box."
            db.add(
                DowntimeEvent(
                    plant_id=plant.id,
                    asset_id=assets[code].id,
                    work_order_id=wo.id,
                    started_at=created,
                    ended_at=None,
                    is_failure=True,
                    is_planned=False,
                    reason=title,
                    created_by_id=sup.id,
                )
            )
        if tk:
            db.add(
                WOAssignment(
                    work_order_id=wo.id,
                    user_id=users[tk].id,
                    is_lead=True,
                    assigned_at=created + timedelta(hours=8),
                    assigned_by_id=planner.id,
                )
            )
        history(wo, steps)
        open_count += 1

    # ---- 4. New work requests ---------------------------------------------------------------------------------------
    for i, (code, title, symptoms, prio, bd, by) in enumerate(REQUESTS):
        r = WorkRequest(
            plant_id=plant.id,
            number=next_number(db, plant, "WR"),
            asset_id=assets[code].id,
            title=title,
            symptoms=symptoms,
            suggested_priority=prio,
            is_breakdown=bd,
            status=RequestStatus.SUBMITTED,
            created_by_id=users[by].id,
        )
        db.add(r)
        db.flush()
        r.created_at = now - timedelta(hours=2 + i * 5)

    # ---- 5. Condition monitoring: 60 days of readings, one bearing going bad ----------------------------------------
    for code, name, asset, technique, punit, warn, alarm in EXTRA_POINTS:
        db.add(
            MeasurementPoint(
                plant_id=plant.id,
                code=code,
                name=name,
                asset_id=assets[asset].id,
                technique=technique,
                unit=punit,
                warning_high=warn,
                alarm_high=alarm,
                stale_after_hours=24 * 8,
                external_tag=f"demo/{code}",
                recommended_action="Check lubrication, alignment and condition; plan a repair if the trend continues.",
            )
        )
    db.flush()
    points = {p.code: p for p in db.execute(select(MeasurementPoint).where(MeasurementPoint.plant_id == plant.id)).scalars()}
    trends = {  # (start, end, noise): a value per reading from 60 days ago to today
        "VIB-DR1-DS": (2.1, 7.6, 0.25),  # rising into alarm: the story of the demo
        "TMP-DR1-DS": (58, 79, 1.5),  # warning
        "CUR-PULP-MTR": (1180, 1230, 25),
        "VIB-REF1-NDE": (2.8, 3.4, 0.3),
        "TMP-C1-OUT": (84, 97, 1.2),  # warning
        "VIB-AER1": (1.9, 2.2, 0.2),
    }
    for code, (v0, v1, noise) in trends.items():
        mp = points.get(code)
        if mp is None:
            continue
        n = 20
        for k in range(n + 1):
            frac = k / n
            val = v0 + (v1 - v0) * (frac**2.2) + rnd.uniform(-noise, noise) * (0.4 if k == n else 1)
            when = now - timedelta(days=60 * (1 - frac), hours=rnd.randint(0, 3)) - timedelta(minutes=30)
            record_reading(db, plant, mp, round(val, 2), when, users["reliability"].id, source="import")
    # The temperature alert on the compressor has been looked at already.
    for al in db.execute(select(ConditionAlert).where(ConditionAlert.plant_id == plant.id)).scalars():
        if al.point_id == points["TMP-C1-OUT"].id:
            al.status, al.acknowledged_by_id, al.acknowledged_at = (
                AlertStatus.ACKNOWLEDGED,
                users["reliability"].id,
                now - timedelta(hours=5),
            )

    # ---- 6. Lubrication: more points, eight weeks of rounds, a few overdue today ------------------------------------
    grease = db.execute(select(Lubricant).where(Lubricant.plant_id == plant.id, Lubricant.code == "EP2")).scalar_one()
    route = LubeRoute(
        plant_id=plant.id,
        code="LR-SP-UTIL",
        name="Stock prep and utilities greasing",
        department_id=assets["SP-L1-REF1"].department_id,
        lead_days=1,
    )
    db.add(route)
    db.flush()
    for i, (code, asset, comp, qty, every) in enumerate(EXTRA_LUBE, start=1):
        db.add(
            LubricationPoint(
                plant_id=plant.id,
                code=code,
                asset_id=assets[asset].id,
                component=comp,
                lubricant_id=grease.id,
                quantity=qty,
                unit="g",
                method="Grease gun",
                frequency_days=every,
                route_id=route.id,
                route_seq=i,
                qr_token=new_qr_token(),
                next_due_date=today,
                responsible_user_id=users["tech.sp"].id,
            )
        )
    db.flush()
    lube_points = list(db.execute(select(LubricationPoint).where(LubricationPoint.plant_id == plant.id)).scalars())
    overdue = 0
    for lp in lube_points:
        every = lp.frequency_days or 14
        due = today - timedelta(days=3 + every * (53 // every))  # the last round fell due 3 days ago
        while due < today:
            late_now = due == today - timedelta(days=3) and lp.code in ("LP-DR1-DS", "LP-DR1-TS", "LP-PULP-MTR")
            if late_now:
                db.add(LubeTask(plant_id=plant.id, point_id=lp.id, route_id=lp.route_id, due_date=due, status=LubeTaskStatus.PENDING))
                overdue += 1
            else:
                skipped = rnd.random() < 0.06
                done = due + timedelta(days=rnd.choice([0, 0, 0, 1]))
                db.add(
                    LubeTask(
                        plant_id=plant.id,
                        point_id=lp.id,
                        route_id=lp.route_id,
                        due_date=due,
                        status=LubeTaskStatus.MISSED if skipped else LubeTaskStatus.DONE,
                        done_at=None if skipped else at(done, 9),
                        done_date=None if skipped else done,
                        done_by_id=None if skipped else (lp.responsible_user_id or users["tech1"].id),
                        quantity_actual=None if skipped else lp.quantity,
                        lubricant_used_id=None if skipped else lp.lubricant_id,
                    )
                )
                if not skipped:
                    lp.last_done_date = done
            due += timedelta(days=every)
        lp.next_due_date = due
    db.flush()
    return {
        "history": db.execute(select(WorkOrder).where(WorkOrder.plant_id == plant.id, WorkOrder.status == WOStatus.CLOSED))
        .scalars()
        .all()
        .__len__(),
        "open": open_count,
        "requests": len(REQUESTS),
        "lube_overdue": overdue,
    }
