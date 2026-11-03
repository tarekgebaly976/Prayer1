"""A few invented examples in every section of an (empty) plant, after scripts/reset-to-examples.sh wiped its
operational data: assets with QR codes, PM (calendar and meter), condition monitoring (PdM) with readings,
lubrication, corrective work orders (CM) and a work request. Codes start with EX- and names say "example".

Run inside the API container:  python - < app/plant_examples.py   (it only uses the app's own models and services,
so it also works with an image built before this file existed)."""

import os
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.assets import Asset, Meter
from app.models.enums import (
    AssetLevel,
    ChecklistKind,
    Criticality,
    FrequencyUnit,
    PMTrigger,
    Priority,
    RequestStatus,
    Technique,
    WOStatus,
    WOType,
)
from app.models.identity import User
from app.models.lubrication import LubeRoute, Lubricant, LubricationPoint
from app.models.pdm import MeasurementPoint
from app.models.pm import JobPlan, JobPlanTask, PMPlan
from app.models.tenancy import Department, Organization, Plant
from app.models.workorders import WorkRequest
from app.services.assets import compute_path, new_qr_token
from app.services.common import next_number, plant_today, utcnow
from app.services.pdm import record_reading
from app.services.pm import plan_occurrences
from app.services.workorders import create_work_order

UTILITY_TYPES = {"UTILITIES", "UTIL", "FACILITIES"}  # compared as text: works with older versions of the enum


def add_examples(db: Session, plant: Plant) -> str:
    depts = list(db.execute(select(Department).where(Department.plant_id == plant.id).order_by(Department.code)).scalars())
    if not depts:
        return f"{plant.code}: no departments, examples skipped"
    main = next((d for d in depts if str(getattr(d.type, "value", d.type)) not in UTILITY_TYPES), depts[0])
    util = next((d for d in depts if str(getattr(d.type, "value", d.type)) in UTILITY_TYPES), main)
    admin = (
        db.execute(select(User).where(User.organization_id == plant.organization_id).order_by(User.is_system_admin.desc(), User.email))
        .scalars()
        .first()
    )
    uid = admin.id if admin else None
    today = plant_today(plant)
    now = utcnow()

    assets: dict[str, Asset] = {}
    for code, name, level, parent, dept, crit, oem in [
        ("EX-L1", "Example production line (sample)", AssetLevel.PRODUCTION_LINE, None, main, "A", None),
        ("EX-L1-P101", "Example centrifugal pump P-101", AssetLevel.UNIT, "EX-L1", main, "A", "KSB"),
        ("EX-L1-P101-MTR", "P-101 motor 55 kW (example)", AssetLevel.ASSEMBLY, "EX-L1-P101", main, "A", "ABB"),
        ("EX-L1-P101-BRG", "P-101 pump bearing, drive end (example)", AssetLevel.COMPONENT, "EX-L1-P101", main, "A", "SKF"),
        ("EX-L1-GBX1", "Example conveyor gearbox", AssetLevel.UNIT, "EX-L1", main, "B", "Flender"),
        ("EX-UT", "Example utilities (sample)", AssetLevel.PRODUCTION_LINE, None, util, "B", None),
        ("EX-UT-AC1", "Example air compressor AC-1", AssetLevel.UNIT, "EX-UT", util, "B", "Atlas Copco"),
    ]:
        p = assets.get(parent) if parent else None
        a = Asset(
            plant_id=plant.id,
            department_id=dept.id,
            parent_id=p.id if p else None,
            level=level,
            code=code,
            name=name,
            criticality=Criticality(crit),
            oem=oem,
            qr_token=new_qr_token(),
            location="Example area",
        )
        db.add(a)
        db.flush()
        a.path = compute_path(p, a.id)
        assets[code] = a

    # PM: weekly inspection (calendar) and an oil change every 4,000 running hours (meter)
    meter = Meter(plant_id=plant.id, asset_id=assets["EX-L1-GBX1"].id, name="Running hours", unit="h", current_value=Decimal(3600))
    jp = JobPlan(
        plant_id=plant.id,
        code="JP-EX-PUMP",
        name="Pump weekly inspection (example)",
        trade="mechanical",
        estimated_hours=Decimal("1"),
        description="Example job plan: check noise, temperature, leaks.",
    )
    jp2 = JobPlan(
        plant_id=plant.id,
        code="JP-EX-OIL",
        name="Gearbox oil change (example)",
        trade="mechanical",
        estimated_hours=Decimal("3"),
        requires_loto=True,
        safety_precautions="Lock out the drive before work.",
    )
    db.add_all([meter, jp, jp2])
    db.flush()
    for i, (desc, kind, unit, hi) in enumerate(
        [
            ("Listen for abnormal noise", ChecklistKind.CHECK, None, None),
            ("Bearing temperature (IR gun)", ChecklistKind.READING, "°C", 75),
            ("Check mechanical seal for leaks", ChecklistKind.CHECK, None, None),
        ],
        start=1,
    ):
        db.add(JobPlanTask(job_plan_id=jp.id, seq=i * 10, description=desc, kind=kind, unit=unit, max_value=hi))
    pm1 = PMPlan(
        plant_id=plant.id,
        code="PM-EX-P101-W",
        name="P-101 weekly inspection (example)",
        asset_id=assets["EX-L1-P101"].id,
        job_plan_id=jp.id,
        trigger=PMTrigger.CALENDAR,
        frequency_unit=FrequencyUnit.WEEK,
        frequency_interval=1,
        start_date=today + timedelta(days=1),
        horizon_days=28,
        lead_days=2,
    )
    pm2 = PMPlan(
        plant_id=plant.id,
        code="PM-EX-GBX-OIL",
        name="Gearbox oil change every 4,000 h (example)",
        asset_id=assets["EX-L1-GBX1"].id,
        job_plan_id=jp2.id,
        trigger=PMTrigger.METER,
        meter_id=meter.id,
        meter_interval=4000,
        last_meter_value=0,
    )
    db.add_all([pm1, pm2])
    db.flush()
    plan_occurrences(db, plant, pm1, today)

    # PdM: two points with a month of readings; the pump bearing ends in WARNING
    for code, name, asset, tech, unit, warn, alarm, values in [
        (
            "VIB-EX-P101",
            "P-101 bearing vibration (example)",
            "EX-L1-P101-BRG",
            Technique.VIBRATION,
            "mm/s",
            4.5,
            7.1,
            [2.1, 2.3, 2.6, 3.1, 3.8, 4.9],
        ),
        (
            "TMP-EX-P101-MTR",
            "P-101 motor temperature (example)",
            "EX-L1-P101-MTR",
            Technique.TEMPERATURE,
            "°C",
            75,
            85,
            [58, 60, 59, 61, 62, 61],
        ),
    ]:
        mp = MeasurementPoint(
            plant_id=plant.id,
            code=code,
            name=name,
            asset_id=assets[asset].id,
            technique=tech,
            unit=unit,
            warning_high=warn,
            alarm_high=alarm,
            stale_after_hours=24 * 8,
            recommended_action="Example: check lubrication and alignment; plan a repair if it keeps rising.",
        )
        db.add(mp)
        db.flush()
        series: list[float] = list(values)  # type: ignore[call-overload]
        for k, v in enumerate(series):
            record_reading(db, plant, mp, v, now - timedelta(days=30 - k * 6, hours=1), uid, source="import")

    # Lubrication: one route, two points
    lub = Lubricant(
        plant_id=plant.id,
        code="EX-EP2",
        manufacturer="Example",
        product="Grease EP2 (example)",
        kind="grease",
        specification="NLGI 2, lithium complex",
    )
    db.add(lub)
    db.flush()
    route = LubeRoute(plant_id=plant.id, code="LR-EX-1", name="Example greasing route", department_id=main.id, lead_days=1)
    db.add(route)
    db.flush()
    for i, (code, asset, comp, qty, every) in enumerate(
        [
            ("LP-EX-P101-DE", "EX-L1-P101-BRG", "Pump bearing, drive end", 20, 14),
            ("LP-EX-P101-MTR", "EX-L1-P101-MTR", "Motor bearings", 15, 30),
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
                method="Grease gun",
                frequency_days=every,
                route_id=route.id,
                route_seq=i,
                qr_token=new_qr_token(),
                next_due_date=today + timedelta(days=i),
            )
        )

    # CM: corrective work orders in three states, and one work request
    create_work_order(
        db,
        plant,
        asset=assets["EX-L1-P101"],
        type=WOType.CORRECTIVE,
        user_id=uid,
        priority=Priority.P2_HIGH,
        title="Example: P-101 mechanical seal leaking",
        symptoms="Drops of water under the pump",
    )
    create_work_order(
        db,
        plant,
        asset=assets["EX-L1-GBX1"],
        type=WOType.CORRECTIVE,
        user_id=uid,
        status=WOStatus.APPROVED,
        title="Example: replace gearbox breather",
        due_date=today + timedelta(days=5),
    )
    create_work_order(
        db,
        plant,
        asset=assets["EX-UT-AC1"],
        type=WOType.CORRECTIVE,
        user_id=uid,
        status=WOStatus.CLOSED,
        title="Example: compressor air filter replaced",
        actual_start=now - timedelta(days=3, hours=2),
        actual_end=now - timedelta(days=3),
        completed_at=now - timedelta(days=3),
        closed_at=now - timedelta(days=2),
    )
    db.add(
        WorkRequest(
            id=uuid.uuid4(),
            plant_id=plant.id,
            number=next_number(db, plant, "WR"),
            asset_id=assets["EX-L1-P101-MTR"].id,
            title="Example: motor sounds louder than usual",
            symptoms="Humming noise since this morning",
            suggested_priority=Priority.P3_MEDIUM,
            status=RequestStatus.SUBMITTED,
            created_by_id=uid,
        )
    )
    db.flush()
    return f"{plant.code}: examples added (7 assets, 2 PM plans, 2 PdM points, 2 lube points, 3 work orders, 1 request)"


def main() -> None:
    """DRY_RUN=1: add the examples and roll back (a check that this works before anything is wiped)."""
    dry = os.environ.get("DRY_RUN") == "1"
    with SessionLocal() as db:
        db.begin()
        plants = (
            db.execute(select(Plant).join(Organization, Organization.id == Plant.organization_id).where(Organization.code != "DEMO"))
            .scalars()
            .all()
        )
        if not plants:
            raise SystemExit("No plant found (other than the DEMO organisation).")
        for plant in plants:
            print(("[dry run] " if dry else "") + add_examples(db, plant))
        if dry:
            db.rollback()
            print("Dry run OK: the examples can be added; nothing was changed.")
        else:
            db.commit()


if __name__ == "__main__":
    main()
