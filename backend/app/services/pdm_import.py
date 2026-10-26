"""Bulk import of condition-monitoring (PdM) points with their reading rounds.

Each row creates a measurement point with its alarm limits. Points of the same asset + frequency + trade
are grouped into one predictive PM plan whose checklist asks for each reading, so the round is scheduled
and closed like any other work order. Preview validates; commit is all-or-nothing."""

import uuid
from collections import Counter, OrderedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.assets import Asset
from app.models.enums import ChecklistKind, PMTrigger, Priority, ScheduleBasis, Technique, WOType
from app.models.pdm import MeasurementPoint
from app.models.pm import JobPlan, JobPlanTask, PMPlan
from app.models.tenancy import Plant
from app.services import pdm as pdmsvc
from app.services import pm as pmsvc
from app.services.common import audit, plant_today
from app.services.imports import _date, _num, _s
from app.services.lube_import import UNIT_DAYS
from app.services.pm_import import _plan_code, parse_frequency, spread_start

LIMITS = ("warning_high", "alarm_high", "warning_low", "alarm_low", "baseline")


def validate_pdm_plans(db: Session, plant: Plant, rows: list[dict]) -> dict:
    assets = {a.code.upper(): a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    point_codes = {c.upper() for c in db.execute(select(MeasurementPoint.code).where(MeasurementPoint.plant_id == plant.id)).scalars()}
    plan_codes = {c.upper() for c in db.execute(select(PMPlan.code).where(PMPlan.plant_id == plant.id)).scalars()}
    plan_codes |= {c.upper() for c in db.execute(select(JobPlan.code).where(JobPlan.plant_id == plant.id)).scalars()}
    per_asset = Counter(a for a in db.execute(select(MeasurementPoint.asset_id).where(MeasurementPoint.plant_id == plant.id)).scalars())
    seen: dict[str, int] = {}
    groups: OrderedDict[str, dict] = OrderedDict()
    out = []
    for i, r in enumerate(rows, start=2):
        errs: list[str] = []
        asset = assets.get((_s(r.get("asset_code")) or "").upper())
        if asset is None:
            errs.append(f"asset {_s(r.get('asset_code')) or '(blank)'} not found")
        name = _s(r.get("point_name"))
        if not name:
            errs.append("point_name is required")
        try:
            tech = Technique((_s(r.get("technique")) or "other").lower().replace(" ", "_"))
        except ValueError:
            errs.append("technique must be one of: " + ", ".join(t.value for t in Technique))
            tech = Technique.OTHER
        unit = _s(r.get("unit"))
        if not unit:
            errs.append("unit is required")
        freq = parse_frequency(r.get("frequency"))
        if freq is None:
            errs.append("frequency must be weekly/monthly/quarterly/semiannual/yearly or a number of days")
        limits = {k: _num(r.get(k), k, errs) for k in LIMITS}
        probe = MeasurementPoint(**{k: limits[k] for k in LIMITS})
        try:
            pdmsvc.validate_limits(probe)
        except DomainError as e:
            errs.append(str(e))
        start = _date(r.get("start_date"), errs, "start_date")
        trade = (_s(r.get("trade")) or "Reliability").strip().title()
        pcode = _s(r.get("point_code"))
        if not pcode and asset is not None:
            per_asset[asset.id] += 1
            pcode = f"{asset.code}-CM{per_asset[asset.id]:02d}"
            while pcode.upper() in point_codes or pcode.upper() in seen:
                per_asset[asset.id] += 1
                pcode = f"{asset.code}-CM{per_asset[asset.id]:02d}"
        if pcode:
            if pcode.upper() in point_codes:
                errs.append(f"measurement point {pcode} already exists (imported before?)")
            if pcode.upper() in seen:
                errs.append(f"duplicate point_code in file (also row {seen[pcode.upper()]})")
            seen.setdefault(pcode.upper(), i)
        rec = {
            "row": i,
            "code": pcode,
            "errors": errs,
            "asset": asset,
            "name": name,
            "technique": tech,
            "unit": unit,
            "limits": limits,
            "freq": freq,
        }
        out.append(rec)
        if asset is None or freq is None:
            continue
        gcode = _plan_code(asset.code, f"CM{freq[2]}", trade)
        g = groups.setdefault(gcode.upper(), {"code": gcode, "asset": asset, "freq": freq, "trade": trade, "rows": [], "start": None})
        g["rows"].append(rec)
        if start:
            g["start"] = min(g["start"] or start, start)
    for g in groups.values():
        if g["code"].upper() in plan_codes:
            for rec in g["rows"]:
                rec["errors"].append(f"PdM round {g['code']} already exists (imported before?)")
    errors = [{"row": r["row"], "code": r["code"], "errors": r["errors"]} for r in out if r["errors"]]
    return {
        "rows": out,
        "groups": list(groups.values()),
        "total": len(out),
        "valid": len(out) - len(errors),
        "invalid": len(errors),
        "errors": errors,
        "plans": len(groups),
    }


def preview_dict(v: dict) -> dict:
    return {k: v[k] for k in ("total", "valid", "invalid", "errors", "plans")}


def commit_pdm_plans(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID) -> int:
    v = validate_pdm_plans(db, plant, rows)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    today = plant_today(plant)
    for g in v["groups"]:
        unit, n, _, label = g["freq"]
        interval_h = UNIT_DAYS[unit] * n * 24
        asset: Asset = g["asset"]
        name = f"{label} condition monitoring – {asset.name}"[:200]
        jp = JobPlan(
            plant_id=plant.id,
            code=g["code"],
            name=name,
            trade=g["trade"],
            created_by_id=user_id,
            estimated_hours=max(round(len(g["rows"]) * 10 / 60, 2), 0.25),
            description="Take each reading and enter it in Condition monitoring so alarms are evaluated.",
        )
        db.add(jp)
        db.flush()
        for seq, rec in enumerate(g["rows"], start=1):
            lim = rec["limits"]
            db.add(
                MeasurementPoint(
                    plant_id=plant.id,
                    code=rec["code"],
                    name=rec["name"][:200],
                    asset_id=asset.id,
                    technique=rec["technique"],
                    unit=rec["unit"],
                    stale_after_hours=int(interval_h * 1.5),
                    **lim,
                )
            )
            db.add(
                JobPlanTask(
                    job_plan_id=jp.id,
                    seq=seq,
                    kind=ChecklistKind.READING,
                    unit=rec["unit"][:20],
                    description=f"{rec['code']}: {rec['name']}"[:400],
                    min_value=lim["alarm_low"],
                    max_value=lim["alarm_high"],
                )
            )
        plan = PMPlan(
            plant_id=plant.id,
            code=g["code"],
            name=name,
            asset_id=asset.id,
            job_plan_id=jp.id,
            trigger=PMTrigger.CALENDAR,
            wo_type=WOType.PREDICTIVE,
            priority=Priority.P3_MEDIUM,
            frequency_unit=unit,
            frequency_interval=n,
            schedule_basis=ScheduleBasis.FIXED,
            start_date=g["start"] or spread_start(g["code"], unit, n, today),
            lead_days=min(7, max(UNIT_DAYS[unit] * n - 1, 0)),
            created_by_id=user_id,
        )
        db.add(plan)
        db.flush()
        pmsvc.plan_occurrences(db, plant, plan, today)
    audit(db, "pdm.import", user_id=user_id, plant_id=plant.id, data={"points": len(v["rows"]), "rounds": len(v["groups"])})
    return len(v["rows"])
