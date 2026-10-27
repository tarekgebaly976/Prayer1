"""Bulk import of PM plans from a task list (one row per task).

Rows of the same asset + frequency + trade are grouped into one PM plan whose job plan holds every
task as checklist items, so a monthly mechanical round on a machine is one work order, not one per task.
Same contract as the other imports: preview validates, commit is all-or-nothing."""

import re
import uuid
import zlib
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.enums import FrequencyUnit, PMTrigger, Priority, ScheduleBasis
from app.models.pm import JobPlan, JobPlanTask, PMPlan
from app.models.tenancy import Plant
from app.models.workorders import PERMIT_TYPES
from app.services import pm as pmsvc
from app.services.common import audit, plant_today
from app.services.imports import _date, _num, _s

NAMED_FREQ: dict[str, tuple[FrequencyUnit, int, str, str]] = {
    "daily": (FrequencyUnit.DAY, 1, "D", "Daily"),
    "weekly": (FrequencyUnit.WEEK, 1, "W", "Weekly"),
    "biweekly": (FrequencyUnit.WEEK, 2, "2W", "Biweekly"),
    "monthly": (FrequencyUnit.MONTH, 1, "M", "Monthly"),
    "bimonthly": (FrequencyUnit.MONTH, 2, "2M", "Bimonthly"),
    "quarterly": (FrequencyUnit.MONTH, 3, "Q", "Quarterly"),
    "semiannual": (FrequencyUnit.MONTH, 6, "H", "Semi-annual"),
    "yearly": (FrequencyUnit.YEAR, 1, "Y", "Yearly"),
    "biennial": (FrequencyUnit.YEAR, 2, "2Y", "Every 2 years"),
}
ALIASES = {
    "annual": "yearly",
    "annually": "yearly",
    "half-yearly": "semiannual",
    "halfyearly": "semiannual",
    "semi-annual": "semiannual",
    "6 monthly": "semiannual",
    "fortnightly": "biweekly",
    "every 2 weeks": "biweekly",
}
DAYS_TO_NAMED = {
    1: "daily",
    7: "weekly",
    14: "biweekly",
    15: "biweekly",
    30: "monthly",
    31: "monthly",
    60: "bimonthly",
    90: "quarterly",
    91: "quarterly",
    120: None,
    180: "semiannual",
    182: "semiannual",
    183: "semiannual",
    365: "yearly",
    730: "biennial",
}
TRADE_CODES = {"mechanical": "MECH", "electrical": "ELEC", "instrumentation": "INST", "operations": "OPS", "lubrication": "LUBE"}
STEP_SPLIT = re.compile(r"(?:^|\s)\d{1,2}\s*[.)-]\s*(?=\S)")
YES = {"yes", "y", "true", "1", "offline", "shutdown"}
MAX_STEPS = 60  # above this a plan lists one checklist line per task; full procedures go to the job plan description


def parse_frequency(v: Any) -> tuple[FrequencyUnit, int, str, str] | None:
    s = (_s(v) or "").lower()
    if not s:
        return None
    s = ALIASES.get(s, s)
    if s in NAMED_FREQ:
        return NAMED_FREQ[s]
    try:
        days = int(float(s))
    except ValueError:
        return None
    if days < 1:
        return None
    named = DAYS_TO_NAMED.get(days)
    return NAMED_FREQ[named] if named else (FrequencyUnit.DAY, days, f"D{days}", f"Every {days} days")


def split_steps(text: str) -> list[str]:
    """'1. Clean ... 2. Inspect ...' -> ['Clean ...', 'Inspect ...']; text without numbering stays one step."""
    text = " ".join(text.split())
    parts = [p.strip(" ;,") for p in STEP_SPLIT.split(text)]
    head, steps = parts[0], [p for p in parts[1:] if p]
    if len(steps) < 2:
        steps = [text]
    elif head:
        steps[0] = f"{head} {steps[0]}"  # keep a preamble such as "Secure work permit:" with the first step
    return [st if len(st) <= 400 else st[:399] + "…" for st in steps]


def spread_start(code: str, unit: FrequencyUnit, n: int, today: date) -> date:
    """First due date for a plan imported without start_date: a stable offset inside its first cycle, so a bulk import
    spreads the workload instead of making every plan due on the import day."""
    cycle = {FrequencyUnit.DAY: 1, FrequencyUnit.WEEK: 7, FrequencyUnit.MONTH: 30, FrequencyUnit.YEAR: 365}[unit] * n
    return today + timedelta(days=zlib.crc32(code.upper().encode()) % cycle)


def _trade_code(trade: str) -> str:
    return TRADE_CODES.get(trade.lower()) or (re.sub(r"[^A-Z0-9]", "", trade.upper())[:4] or "GEN")


def _plan_code(asset_code: str, freq: str, trade: str) -> str:
    code = f"{asset_code}-{freq}-{_trade_code(trade)}"
    if len(code) > 40:
        code = f"{asset_code[:24]}~{zlib.crc32(code.encode()) & 0xFFFF:04X}-{freq}-{_trade_code(trade)}"[:40]
    return code


def validate_pm_plans(db: Session, plant: Plant, rows: list[dict]) -> dict:
    assets = {a.code.upper(): a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    plan_codes = {c.upper() for c in db.execute(select(PMPlan.code).where(PMPlan.plant_id == plant.id)).scalars()}
    jp_codes = {c.upper() for c in db.execute(select(JobPlan.code).where(JobPlan.plant_id == plant.id)).scalars()}
    out: list[dict] = []
    groups: OrderedDict[str, dict] = OrderedDict()
    for i, r in enumerate(rows, start=2):
        errs: list[str] = []
        asset_code, task = _s(r.get("asset_code")), _s(r.get("task"))
        asset = assets.get((asset_code or "").upper())
        if not asset_code:
            errs.append("asset_code is required")
        elif asset is None:
            errs.append(f"asset {asset_code} not found")
        if not task:
            errs.append("task is required")
        freq = parse_frequency(r.get("frequency"))
        if freq is None:
            errs.append("frequency must be weekly/monthly/quarterly/semiannual/yearly or a number of days")
        trade = (_s(r.get("trade")) or "General").strip().title()
        minutes = _num(r.get("duration_min"), "duration_min", errs) or 0
        crew = _num(r.get("crew"), "crew", errs, integer=True) or 1
        start = _date(r.get("start_date"), errs, "start_date")
        prio_s = (_s(r.get("priority")) or "P3").upper()
        try:
            prio = Priority(prio_s)
        except ValueError:
            errs.append("priority must be P1, P2, P3 or P4")
            prio = Priority.P3_MEDIUM
        permit_s = (_s(r.get("permit")) or "").lower().replace(" ", "_")
        permits: list[str] = []
        if permit_s in YES:
            permits = ["cold_work"]
        elif permit_s and permit_s not in ("no", "n", "false", "0", "none"):
            permits = [p.strip("_") for p in re.split(r"[,;/]+", permit_s) if p.strip("_")]
            unknown = [p for p in permits if p not in PERMIT_TYPES]
            if unknown:
                errs.append(f"unknown permit type: {', '.join(unknown)}")
        loto = (_s(r.get("loto")) or "").lower() in YES
        rec = {"row": i, "code": None, "errors": errs}
        out.append(rec)
        if errs or asset is None or freq is None or not task:
            continue
        code = _plan_code(asset.code, freq[2], trade)
        rec["code"] = code
        g = groups.setdefault(
            code.upper(),
            {
                "code": code,
                "asset": asset,
                "freq": freq,
                "trade": trade,
                "rows": [],
                "texts": [],
                "permits": [],
                "loto": False,
                "tasks": [],
                "minutes": 0.0,
                "crew": 1,
                "shutdown": False,
                "start": None,
                "priority": prio,
            },
        )
        g["rows"].append(rec)
        g["texts"].append(" ".join(task.split()))
        g["tasks"].extend(split_steps(task))
        g["minutes"] += float(minutes)
        g["crew"] = max(g["crew"], int(crew))
        g["permits"].extend(p for p in permits if p not in g["permits"])
        g["loto"] = g["loto"] or loto
        g["shutdown"] = g["shutdown"] or (_s(r.get("shutdown_required")) or "").lower() in YES
        if start:  # earliest date given in the group; blank rows do not pull it back to today
            g["start"] = min(g["start"] or start, start)
        g["priority"] = min(g["priority"], prio, key=lambda p: p.value)  # most urgent task wins
    for g in groups.values():
        if g["code"].upper() in plan_codes or g["code"].upper() in jp_codes:
            for rec in g["rows"]:
                rec["errors"].append(f"PM plan {g['code']} already exists (imported before?)")
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


def commit_pm_plans(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID) -> int:
    v = validate_pm_plans(db, plant, rows)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    today = plant_today(plant)
    for g in v["groups"]:
        unit, n, _, label = g["freq"]
        asset: Asset = g["asset"]
        name = f"{label} {g['trade']} PM – {asset.name}"[:200]
        jp = JobPlan(
            plant_id=plant.id,
            code=g["code"],
            name=name,
            trade=g["trade"],
            created_by_id=user_id,
            estimated_hours=max(round(g["minutes"] / 60, 2), 0.25),
            crew_size=g["crew"],
            safety_precautions="Machine shutdown required (offline task)." if g["shutdown"] else None,
            requires_permit=bool(g["permits"]),
            permit_types=",".join(g["permits"]) or None,
            requires_loto=g["loto"],
        )
        items = g["tasks"]
        if len(items) > MAX_STEPS:
            items = [t if len(t) <= 400 else t[:399] + "…" for t in g["texts"]]
            jp.description = "\n\n".join(f"{i}. {t}" for i, t in enumerate(dict.fromkeys(g["texts"]), start=1))
        db.add(jp)
        db.flush()
        for seq, step in enumerate(items, start=1):
            db.add(JobPlanTask(job_plan_id=jp.id, seq=seq, description=step))
        interval_days = {FrequencyUnit.DAY: 1, FrequencyUnit.WEEK: 7, FrequencyUnit.MONTH: 30, FrequencyUnit.YEAR: 365}[unit] * n
        plan = PMPlan(
            plant_id=plant.id,
            code=g["code"],
            name=name,
            asset_id=asset.id,
            job_plan_id=jp.id,
            trigger=PMTrigger.CALENDAR,
            priority=g["priority"],
            frequency_unit=unit,
            frequency_interval=n,
            schedule_basis=ScheduleBasis.FIXED,
            start_date=g["start"] or spread_start(g["code"], unit, n, today),
            lead_days=min(7, max(interval_days - 1, 0)),
            created_by_id=user_id,
        )
        db.add(plan)
        db.flush()
        pmsvc.plan_occurrences(db, plant, plan, today)
    audit(db, "pm.import", user_id=user_id, plant_id=plant.id, data={"plans": len(v["groups"]), "tasks": v["total"]})
    return len(v["groups"])


def preview_dict(v: dict) -> dict:
    return {k: v[k] for k in ("total", "valid", "invalid", "errors", "plans")}
