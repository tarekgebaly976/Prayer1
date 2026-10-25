"""Realistic paper-mill SAMPLE data, loaded into a separate DEMO organization/plant flagged
settings.demo = true. It never touches production organizations. Values are illustrative only and
must not be presented as actual plant performance."""

from datetime import date, time, timedelta

from sqlalchemy import select

from app.cli import DEFAULT_DEPTS
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.assets import Asset, AssetBOM, FailureCode, Meter
from app.models.enums import (
    AssetLevel,
    ChecklistKind,
    Criticality,
    FailureCodeKind,
    FrequencyUnit,
    PMTrigger,
    ShiftKind,
    Technique,
)
from app.models.identity import Membership, Role, User
from app.models.inventory import Part, Supplier, Warehouse
from app.models.lubrication import LubeRoute, Lubricant, LubricationPoint
from app.models.pdm import MeasurementPoint
from app.models.pm import JobPlan, JobPlanTask, PMPlan
from app.models.shifts import ShiftDefinition, ShiftPattern, Team, TeamMember
from app.models.tenancy import Department, Organization, Plant
from app.services.assets import compute_path, new_qr_token
from app.services.common import plant_today, sync_rbac, utcnow
from app.services.inventory import receive
from app.services.pm import plan_occurrences
from app.services.workflow import ensure_default_transitions

USERS = [
    ("admin@demo.example.com", "Demo Administrator", "system_admin", None, None),
    ("manager@demo.example.com", "Khalid Al-Harbi", "maintenance_manager", None, None),
    ("planner@demo.example.com", "Sara Al-Qahtani", "planner", None, None),
    ("mech.sup@demo.example.com", "Omar Al-Shehri", "mech_supervisor", None, "mechanical"),
    ("elec.sup@demo.example.com", "Faisal Al-Dosari", "elec_supervisor", None, "electrical"),
    ("reliability@demo.example.com", "Nora Al-Mutairi", "reliability_engineer", None, None),
    ("engineer@demo.example.com", "Yousef Al-Ghamdi", "engineer", None, "mechanical"),
    ("tech1@demo.example.com", "Ahmed Saleh", "technician", None, "mechanical"),
    ("tech2@demo.example.com", "Rashid Nasser", "technician", None, "mechanical"),
    ("tech3@demo.example.com", "Imran Khan", "technician", None, "electrical"),
    ("tech.sp@demo.example.com", "Hassan Ali", "technician", "SP", "mechanical"),
    ("store@demo.example.com", "Majed Al-Otaibi", "storekeeper", None, None),
    ("production@demo.example.com", "PM1 Shift Leader", "production_user", None, None),
    ("viewer@demo.example.com", "Plant Director", "management_viewer", None, None),
]

# (code, name, level, parent_code, dept, criticality, oem, model)
ASSETS = [
    ("PM1", "Paper Machine 1", "production_line", None, "PM", "A", "Valmet", "OptiConcept M"),
    ("PM1-WIRE", "Wire Part (Forming Section)", "unit", "PM1", "PM", "A", "Valmet", None),
    ("PM1-WIRE-UTW", "Under Top Wire", "assembly", "PM1-WIRE", "PM", "A", None, None),
    ("PM1-WIRE-UTW-DR1", "Drive Roll No. 1", "sub_assembly", "PM1-WIRE-UTW", "PM", "A", None, None),
    (
        "PM1-WIRE-UTW-DR1-BRG-DS",
        "Drive Roll No. 1 Bearing (Drive Side)",
        "component",
        "PM1-WIRE-UTW-DR1",
        "PM",
        "A",
        "SKF",
        "23148 CCK/W33",
    ),
    (
        "PM1-WIRE-UTW-DR1-BRG-TS",
        "Drive Roll No. 1 Bearing (Tending Side)",
        "component",
        "PM1-WIRE-UTW-DR1",
        "PM",
        "A",
        "SKF",
        "23148 CCK/W33",
    ),
    ("PM1-WIRE-UTW-DR1-GBX", "Drive Roll No. 1 Gearbox", "component", "PM1-WIRE-UTW-DR1", "PM", "A", "Flender", "H2SH"),
    ("PM1-PRESS", "Press Section", "unit", "PM1", "PM", "A", "Valmet", None),
    ("PM1-PRESS-SHOE", "Shoe Press", "assembly", "PM1-PRESS", "PM", "A", "Valmet", "SymBelt"),
    ("PM1-PRESS-SHOE-HPU", "Shoe Press Hydraulic Unit", "sub_assembly", "PM1-PRESS-SHOE", "PM", "A", "Bosch Rexroth", None),
    ("PM1-DRY", "Dryer Section", "unit", "PM1", "PM", "A", None, None),
    ("PM1-DRY-G1", "Dryer Group 1", "assembly", "PM1-DRY", "PM", "B", None, None),
    ("PM1-DRY-G1-CYL01", "Dryer Cylinder 01", "sub_assembly", "PM1-DRY-G1", "PM", "B", None, None),
    ("PM1-DRY-G1-CYL01-JNT", "Rotary Joint Cyl 01", "component", "PM1-DRY-G1-CYL01", "PM", "B", "Kadant", None),
    ("PM1-REEL", "Reel", "unit", "PM1", "PM", "B", None, None),
    ("SP-L1", "Stock Preparation Line 1", "production_line", None, "SP", "A", None, None),
    ("SP-L1-PULP", "Pulper", "unit", "SP-L1", "SP", "A", "Andritz", None),
    ("SP-L1-PULP-MTR", "Pulper Main Motor 800 kW", "assembly", "SP-L1-PULP", "SP", "A", "ABB", "M3BP 450"),
    ("SP-L1-REF1", "Refiner No. 1", "unit", "SP-L1", "SP", "A", "Andritz", "TwinFlo"),
    ("FH-L1", "Finishing Line 1", "production_line", None, "FH", "B", None, None),
    ("FH-L1-WIND", "Winder", "unit", "FH-L1", "FH", "B", "Valmet", None),
    ("WWTP-L1", "Effluent Treatment Line", "production_line", None, "WWTP", "B", None, None),
    ("WWTP-L1-AER1", "Aeration Blower 1", "unit", "WWTP-L1", "WWTP", "B", "Aerzen", None),
    ("EAI-DCS", "Distributed Control System", "production_line", None, "EAI", "A", "ABB", "800xA"),
    ("EAI-DCS-SUB1", "MV Substation 1", "unit", "EAI-DCS", "EAI", "A", None, None),
    ("UTIL-AIR", "Compressed Air System", "production_line", None, "UTIL", "B", None, None),
    ("UTIL-AIR-C1", "Air Compressor 1", "unit", "UTIL-AIR", "UTIL", "B", "Atlas Copco", "ZR 160"),
]


def seed_demo(password: str) -> None:
    with SessionLocal() as db, db.begin():
        sync_rbac(db)
        if db.execute(select(Organization).where(Organization.code == "DEMO")).scalar_one_or_none():
            print("Demo organization already exists; nothing to do.")
            return
        org = Organization(code="DEMO", name="Demo Paper Company (SAMPLE DATA)")
        db.add(org)
        db.flush()
        plant = Plant(
            organization_id=org.id,
            code="DMO",
            name="Demo Paper Mill (sample data)",
            timezone="Asia/Riyadh",
            currency="SAR",
            settings={"demo": True, "default_labor_rate": 85, "overtime_multiplier": 1.5, "repeat_failure_days": 30},
        )
        db.add(plant)
        db.flush()
        ensure_default_transitions(db, plant.id)
        depts = {}
        for code, name, ar, t in DEFAULT_DEPTS:
            d = Department(plant_id=plant.id, code=code, name=name, name_ar=ar, type=t)
            db.add(d)
            depts[code] = d
        db.flush()
        roles = {r.code: r for r in db.execute(select(Role)).scalars()}
        users = {}
        pw_hash = hash_password(password)
        for email, name, role, dept, trade in USERS:
            u = User(
                organization_id=org.id,
                email=email,
                full_name=name,
                password_hash=pw_hash,
                trade=trade,
                hourly_rate=85 if role == "technician" else 120,
                is_system_admin=role == "system_admin",
                password_changed_at=utcnow(),
            )
            db.add(u)
            db.flush()
            db.add(Membership(user_id=u.id, plant_id=plant.id, role_id=roles[role].id, department_id=depts[dept].id if dept else None))
            users[email.split("@")[0]] = u
        assets: dict[str, Asset] = {}
        for code, name, level, parent, dept, crit, oem, model in ASSETS:
            p = assets.get(parent) if parent else None
            a = Asset(
                plant_id=plant.id,
                department_id=depts[dept].id,
                parent_id=p.id if p else None,
                level=AssetLevel(level),
                code=code,
                name=name,
                criticality=Criticality(crit),
                oem=oem,
                model=model,
                qr_token=new_qr_token(),
                install_date=date(2016, 3, 1),
                location=f"{dept} hall",
            )
            db.add(a)
            db.flush()
            a.path = compute_path(p, a.id)
            assets[code] = a
        for kind, rows in {
            FailureCodeKind.PROBLEM: [
                ("VIB", "High vibration"),
                ("OVH", "Overheating"),
                ("LEAK", "Leakage"),
                ("NOISE", "Abnormal noise"),
                ("TRIP", "Electrical trip"),
            ],
            FailureCodeKind.CAUSE: [
                ("LUB", "Lubrication failure"),
                ("WEAR", "Wear / fatigue"),
                ("MIS", "Misalignment"),
                ("CONT", "Contamination"),
                ("ELEC", "Electrical fault"),
            ],
            FailureCodeKind.REMEDY: [
                ("REPL", "Replaced component"),
                ("ALIGN", "Re-aligned"),
                ("RELUB", "Re-lubricated"),
                ("ADJ", "Adjusted"),
                ("REPAIR", "Repaired"),
            ],
        }.items():
            for c, d in rows:
                db.add(FailureCode(plant_id=plant.id, kind=kind, code=c, description=d))
        wh = Warehouse(plant_id=plant.id, code="MAIN", name="Main Maintenance Store")
        db.add(wh)
        sup = Supplier(plant_id=plant.id, code="SKF-SA", name="Bearing distributor (sample)", default_lead_time_days=21)
        db.add(sup)
        db.flush()
        parts = {}
        for code, desc, pn, mfr, uom, crit, critspare, rop, mx, price, qty in [
            ("BRG-23148", "Spherical roller bearing 23148 CCK/W33", "23148 CCK/W33", "SKF", "EA", "A", True, 2, 4, 9800.0, 3),
            ("SEAL-DR1", "Drive roll housing seal kit", "SK-DR1", "Valmet", "EA", "A", False, 2, 6, 1450.0, 4),
            ("GRS-EP2", "Grease EP2 lithium complex 18 kg pail", "LGEP2/18", "SKF", "KG", "B", False, 36, 144, 32.0, 90),
            ("OIL-VG220", "Gear oil ISO VG 220 (208 L drum)", "VG220", "Mobil", "L", "B", False, 208, 832, 18.5, 416),
            ("FLT-HPU", "Hydraulic filter element 10 µm", "R928006", "Bosch Rexroth", "EA", "B", False, 4, 12, 610.0, 8),
            ("CPL-ELEM", "Coupling elastomer element", "N-EUPEX 225", "Flender", "EA", "B", False, 2, 6, 380.0, 5),
            ("MTR-CB-400A", "MCCB 400 A spare", "T5N400", "ABB", "EA", "A", True, 1, 2, 5200.0, 1),
        ]:
            p = Part(
                plant_id=plant.id,
                code=code,
                description=desc,
                oem_part_number=pn,
                manufacturer=mfr,
                uom=uom,
                criticality=Criticality(crit),
                is_critical_spare=critspare,
                reorder_point=rop,
                max_qty=mx,
                min_qty=rop,
                unit_price=price,
                average_cost=price,
                currency="SAR",
                preferred_supplier_id=sup.id,
                lead_time_days=21,
            )
            db.add(p)
            db.flush()
            receive(db, plant, p, wh, qty, price, None, "Opening balance (sample)")
            parts[code] = p
        for asset_code, part_code, q in [
            ("PM1-WIRE-UTW-DR1-BRG-DS", "BRG-23148", 1),
            ("PM1-WIRE-UTW-DR1-BRG-TS", "BRG-23148", 1),
            ("PM1-WIRE-UTW-DR1", "SEAL-DR1", 2),
            ("PM1-WIRE-UTW-DR1-GBX", "OIL-VG220", 60),
            ("PM1-PRESS-SHOE-HPU", "FLT-HPU", 2),
        ]:
            db.add(AssetBOM(asset_id=assets[asset_code].id, part_id=parts[part_code].id, quantity=q))
        meter = Meter(plant_id=plant.id, asset_id=assets["PM1-WIRE-UTW-DR1-GBX"].id, name="Running hours", unit="h", current_value=41250)
        db.add(meter)
        jp = JobPlan(
            plant_id=plant.id,
            code="JP-DR-INSP",
            name="Drive roll weekly inspection",
            trade="mechanical",
            estimated_hours=1.5,
            safety_precautions="Machine running inspection: keep clear of nips; no guards removed.",
            description="Inspect drive roll bearings, seals and gearbox.",
        )
        jp2 = JobPlan(
            plant_id=plant.id,
            code="JP-GBX-OIL",
            name="Gearbox oil change",
            trade="mechanical",
            estimated_hours=4,
            requires_loto=True,
            requires_testing=True,
            safety_precautions="Apply LOTO on drive motor MCC. Verify zero energy.",
        )
        db.add_all([jp, jp2])
        db.flush()
        for i, (desc, kind, unit, lo, hi) in enumerate(
            [
                ("Check bearing housings for abnormal noise", ChecklistKind.CHECK, None, None, None),
                ("Bearing temperature DS (IR gun)", ChecklistKind.READING, "°C", None, 75),
                ("Bearing temperature TS (IR gun)", ChecklistKind.READING, "°C", None, 75),
                ("Check seals for leakage", ChecklistKind.CHECK, None, None, None),
                ("Gearbox oil level sight glass", ChecklistKind.CHECK, None, None, None),
            ],
            start=1,
        ):
            db.add(JobPlanTask(job_plan_id=jp.id, seq=i * 10, description=desc, kind=kind, unit=unit, min_value=lo, max_value=hi))
        for i, desc in enumerate(
            [
                "Drain oil and inspect for particles",
                "Replace breather",
                "Refill ISO VG 220 to level",
                "Run test: check temperature and leaks",
            ],
            start=1,
        ):
            db.add(JobPlanTask(job_plan_id=jp2.id, seq=i * 10, description=desc))
        today = plant_today(plant)
        pm1 = PMPlan(
            plant_id=plant.id,
            code="PM-DR1-W",
            name="Drive Roll No.1 weekly inspection",
            asset_id=assets["PM1-WIRE-UTW-DR1"].id,
            job_plan_id=jp.id,
            trigger=PMTrigger.CALENDAR,
            frequency_unit=FrequencyUnit.WEEK,
            frequency_interval=1,
            start_date=today,
            horizon_days=28,
            lead_days=2,
        )
        pm2 = PMPlan(
            plant_id=plant.id,
            code="PM-GBX-OIL",
            name="DR1 gearbox oil change (8,000 h)",
            asset_id=assets["PM1-WIRE-UTW-DR1-GBX"].id,
            job_plan_id=jp2.id,
            trigger=PMTrigger.METER,
            meter_id=meter.id,
            meter_interval=8000,
            last_meter_value=36000,
        )
        db.add_all([pm1, pm2])
        db.flush()
        plan_occurrences(db, plant, pm1, today)
        lub = Lubricant(
            plant_id=plant.id,
            code="EP2",
            manufacturer="SKF",
            product="LGEP 2",
            kind="grease",
            specification="NLGI 2, lithium, EP",
            part_id=parts["GRS-EP2"].id,
        )
        oil = Lubricant(
            plant_id=plant.id,
            code="VG220",
            manufacturer="Mobil",
            product="Mobilgear 600 XP 220",
            kind="oil",
            viscosity_grade="ISO VG 220",
            part_id=parts["OIL-VG220"].id,
        )
        db.add_all([lub, oil])
        db.flush()
        route = LubeRoute(
            plant_id=plant.id, code="LR-PM1-WIRE", name="PM1 wire section greasing", department_id=depts["PM"].id, lead_days=1
        )
        db.add(route)
        db.flush()
        for i, (code, asset, comp, qty) in enumerate(
            [
                ("LP-DR1-DS", "PM1-WIRE-UTW-DR1-BRG-DS", "Drive-side bearing", 40),
                ("LP-DR1-TS", "PM1-WIRE-UTW-DR1-BRG-TS", "Tending-side bearing", 40),
            ],
            start=1,
        ):
            db.add(
                LubricationPoint(
                    plant_id=plant.id,
                    code=code,
                    asset_id=assets[asset].id,
                    component=comp,
                    lubricant_id=lub.id,
                    quantity=qty,
                    unit="g",
                    method="Grease gun, 2 strokes = 4 g",
                    frequency_days=14,
                    route_id=route.id,
                    route_seq=i,
                    qr_token=new_qr_token(),
                    next_due_date=today,
                    responsible_user_id=users["tech1"].id,
                    oem_recommendation="Relubrication interval per SKF calculation at 450 rpm",
                )
            )
        for code, name, asset, tech, unit, wh_, ah in [
            ("VIB-DR1-DS", "DR1 DS bearing velocity", "PM1-WIRE-UTW-DR1-BRG-DS", Technique.VIBRATION, "mm/s", 4.5, 7.1),
            ("TMP-DR1-DS", "DR1 DS bearing temperature", "PM1-WIRE-UTW-DR1-BRG-DS", Technique.TEMPERATURE, "°C", 75, 85),
            ("CUR-PULP-MTR", "Pulper motor current", "SP-L1-PULP-MTR", Technique.MOTOR_CURRENT, "A", 1350, 1450),
        ]:
            db.add(
                MeasurementPoint(
                    plant_id=plant.id,
                    code=code,
                    name=name,
                    asset_id=assets[asset].id,
                    technique=tech,
                    unit=unit,
                    warning_high=wh_,
                    alarm_high=ah,
                    stale_after_hours=24 * 8,
                    external_tag=f"demo/{code}",
                    recommended_action="Check lubrication, alignment and bearing condition; plan replacement if trend continues.",
                )
            )
        shifts = {}
        for code, name, kind, s, e in [
            ("D", "Day", ShiftKind.DAY, time(6), time(14)),
            ("E", "Evening", ShiftKind.EVENING, time(14), time(22)),
            ("N", "Night", ShiftKind.NIGHT, time(22), time(6)),
            ("G", "General", ShiftKind.GENERAL, time(7), time(15)),
        ]:
            sd = ShiftDefinition(plant_id=plant.id, code=code, name=name, kind=kind, start_time=s, end_time=e, paid_hours=8)
            db.add(sd)
            shifts[code] = sd
        pat = ShiftPattern(plant_id=plant.id, code="2D2E2N2O", name="8-day rotation", cycle=["D", "D", "E", "E", "N", "N", "OFF", "OFF"])
        db.add(pat)
        db.flush()
        team = Team(
            plant_id=plant.id,
            code="A",
            name="Mechanical Crew A",
            department_id=depts["PM"].id,
            supervisor_id=users["mech.sup"].id,
            pattern_id=pat.id,
            pattern_anchor_date=today - timedelta(days=today.weekday()),
        )
        db.add(team)
        db.flush()
        for k in ("tech1", "tech2", "tech3"):
            db.add(TeamMember(team_id=team.id, user_id=users[k].id))
    print("Demo data loaded: organization DEMO, plant DMO. Users: " + ", ".join(e for e, *_ in USERS))
