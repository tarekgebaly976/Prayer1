"""Import of work-order history and spare-part consumption from a previous system.

History work orders are written as CLOSED, marked source="migrated" with the old system's reference, and are never
pushed through the live workflow (no approvals, notifications or PM side effects). Breakdowns become downtime
events so MTBF, MTTR and availability include them. Same contract as the other imports: preview validates, commit is
all-or-nothing."""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import Asset, DowntimeEvent
from app.models.enums import Priority, WOStatus, WOType
from app.models.inventory import Part, PartUsage
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder, WOStatusHistory
from app.services.common import audit, utcnow
from app.services.imports import _date, _num, _s

TYPES = {
    "breakdown": WOType.EMERGENCY,
    "emergency": WOType.EMERGENCY,
    "corrective": WOType.CORRECTIVE,
    "workshop": WOType.CORRECTIVE,
    "preventive": WOType.PREVENTIVE,
    "pm": WOType.PREVENTIVE,
    "inspection": WOType.INSPECTION,
    "improvement": WOType.IMPROVEMENT,
    "project": WOType.IMPROVEMENT,
    "shutdown": WOType.SHUTDOWN,
    "lubrication": WOType.LUBRICATION,
    "predictive": WOType.PREDICTIVE,
}
PRIORITIES = {
    "high": Priority.P2_HIGH,
    "medium": Priority.P3_MEDIUM,
    "low": Priority.P4_LOW,
    "urgent": Priority.P1_EMERGENCY,
    "p1": Priority.P1_EMERGENCY,
    "p2": Priority.P2_HIGH,
    "p3": Priority.P3_MEDIUM,
    "p4": Priority.P4_LOW,
}
YES = {"yes", "y", "true", "1"}
CENT = Decimal("0.01")


def _when(v: Any, field: str, errs: list[str], tz: ZoneInfo) -> datetime | None:
    """Plant-local timestamp from a datetime cell or 'YYYY-MM-DD[ HH:MM]' text."""
    if v is None or _s(v) is None:
        return None
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, date):
        dt = datetime.combine(v, time())
    else:
        txt = str(v).strip().replace("T", " ")
        try:
            dt = datetime.fromisoformat(txt[:19]) if len(txt) > 10 else datetime.combine(date.fromisoformat(txt[:10]), time())
        except ValueError:
            errs.append(f"{field} must be YYYY-MM-DD HH:MM")
            return None
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def validate_wo_history(db: Session, plant: Plant, rows: list[dict]) -> dict:
    tz = ZoneInfo(plant.timezone)
    assets = {a.code.upper(): a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    taken = {
        r.upper()
        for r in db.execute(
            select(WorkOrder.external_ref).where(WorkOrder.plant_id == plant.id, WorkOrder.external_ref.is_not(None))
        ).scalars()
    }
    seen: dict[str, int] = {}
    out = []
    for i, r in enumerate(rows, start=2):
        errs: list[str] = []
        ref = _s(r.get("external_ref"))
        if not ref:
            errs.append("external_ref is required")
        elif len(ref) > 60:
            errs.append("external_ref longer than 60 characters")
        elif ref.upper() in taken:
            errs.append(f"work order {ref} was already imported")
        elif ref.upper() in seen:
            errs.append(f"duplicate external_ref in file (also row {seen[ref.upper()]})")
        if ref:
            seen.setdefault(ref.upper(), i)
        asset = assets.get((_s(r.get("asset_code")) or "").upper())
        if asset is None:
            errs.append(f"asset {_s(r.get('asset_code')) or '(blank)'} not found")
        breakdown = (_s(r.get("breakdown")) or "").lower() in YES
        t = (_s(r.get("type")) or ("breakdown" if breakdown else "corrective")).lower()
        wtype = WOType.EMERGENCY if breakdown else TYPES.get(t)
        if wtype is None:
            errs.append("unknown type")
        title = _s(r.get("title")) or _s(r.get("description"))
        if not title:
            errs.append("title is required")
        prio = PRIORITIES.get((_s(r.get("priority")) or "p3").lower())
        if prio is None:
            errs.append("priority must be P1-P4 or High/Medium/Low")
        reported = _when(r.get("reported_at"), "reported_at", errs, tz)
        if reported is None and "reported_at must be YYYY-MM-DD HH:MM" not in errs:
            errs.append("reported_at is required")
        started = _when(r.get("started_at"), "started_at", errs, tz)
        completed = _when(r.get("completed_at"), "completed_at", errs, tz)
        closed = _when(r.get("closed_at"), "closed_at", errs, tz)
        dt_hours = _num(r.get("downtime_hours"), "downtime_hours", errs)
        minutes = _num(r.get("repair_minutes"), "repair_minutes", errs)
        if reported and completed and completed < reported:
            errs.append("completed_at is before reported_at")
        out.append(
            {
                "row": i,
                "code": ref,
                "errors": errs,
                "raw": r,
                "asset": asset,
                "type": wtype,
                "title": title,
                "priority": prio,
                "breakdown": breakdown,
                "reported": reported,
                "started": started,
                "completed": completed,
                "closed": closed,
                "downtime_hours": dt_hours,
                "minutes": minutes,
            }
        )
    errors = [{"row": r["row"], "code": r["code"], "errors": r["errors"]} for r in out if r["errors"]]
    return {
        "rows": out,
        "total": len(out),
        "valid": len(out) - len(errors),
        "invalid": len(errors),
        "errors": errors,
        "plans": sum(1 for r in out if r["breakdown"]),
    }


def preview_dict(v: dict) -> dict:
    return {k: v[k] for k in ("total", "valid", "invalid", "errors", "plans")}


def _text(*parts: tuple[str, str | None]) -> str | None:
    lines = [f"{label}: {value}" for label, value in parts if value]
    return "\n".join(lines) or None


def commit_wo_history(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID) -> int:
    v = validate_wo_history(db, plant, rows)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    for rec in v["rows"]:
        r, a = rec["raw"], rec["asset"]
        start = rec["started"] or rec["reported"]
        end = rec["completed"]
        if end is None and rec["downtime_hours"]:
            end = start + timedelta(hours=float(rec["downtime_hours"]))
        if end is not None and end < start:
            end = start  # day/month mix-ups in old data: never a negative duration
        closed = rec["closed"] or end or rec["reported"]
        wo = WorkOrder(
            plant_id=plant.id,
            number=f"MIG-{rec['code']}"[:40],
            source="migrated",
            external_ref=rec["code"],
            type=rec["type"],
            status=WOStatus.CLOSED,
            priority=rec["priority"],
            asset_id=a.id,
            department_id=a.department_id,
            title=rec["title"][:200],
            description=_text(
                ("Description", _s(r.get("description"))),
                ("Trade", _s(r.get("trade"))),
                ("Technician", _s(r.get("technician"))),
                ("Status in previous system", _s(r.get("original_status"))),
            ),
            findings=_text(("Failure mode", _s(r.get("failure_mode"))), ("Work done", _s(r.get("findings")))),
            actual_start=start,
            actual_end=end,
            completed_at=end or closed,
            closed_at=closed,
            currency=plant.currency,
            downtime_hours=round((end - start).total_seconds() / 3600, 2) if (rec["breakdown"] and end) else rec["downtime_hours"],
            actual_labor_hours=round(rec["minutes"] / 60, 2) if rec["minutes"] else 0,
            created_by_id=user_id,
        )
        wo.created_at = rec["reported"]
        db.add(wo)
        db.flush()
        db.add(
            WOStatusHistory(
                work_order_id=wo.id,
                from_status=None,
                to_status=WOStatus.CLOSED.value,
                changed_by_id=user_id,
                changed_at=closed,
                comment=f"Migrated from previous system ({rec['code']})",
            )
        )
        if rec["breakdown"]:
            db.add(
                DowntimeEvent(
                    plant_id=plant.id,
                    asset_id=a.id,
                    work_order_id=wo.id,
                    started_at=start,
                    ended_at=end or start,
                    is_failure=True,
                    is_planned=False,
                    created_by_id=user_id,
                )
            )
    db.flush()
    audit(db, "history.wo_import", user_id=user_id, plant_id=plant.id, data={"work_orders": len(v["rows"])})
    return len(v["rows"])


def validate_parts_history(db: Session, plant: Plant, rows: list[dict]) -> dict:
    wos = {
        w.external_ref.upper(): w
        for w in db.execute(select(WorkOrder).where(WorkOrder.plant_id == plant.id, WorkOrder.external_ref.is_not(None))).scalars()
    }
    parts: dict[str, Part] = {}
    for p in db.execute(select(Part).where(Part.plant_id == plant.id)).scalars():
        parts[p.code.upper()] = p
        parts.setdefault(p.code.upper().lstrip("0"), p)  # 04000038 in one system, 4000038 in another
    out = []
    for i, r in enumerate(rows, start=2):
        errs: list[str] = []
        ref = _s(r.get("wo_external_ref"))
        wo = wos.get((ref or "").upper())
        if wo is None:
            errs.append(f"history work order {ref or '(blank)'} not found (import the work orders first)")
        code = _s(r.get("part_code"))
        part = parts.get((code or "").upper()) or parts.get((code or "").upper().lstrip("0")) if code else None
        desc = _s(r.get("description"))
        if part is None and not desc:
            errs.append("description is required when the part code is blank or not in the spare-parts list")
        qty = _num(r.get("quantity"), "quantity", errs)
        if not qty:
            errs.append("quantity must be > 0")
        cost = _num(r.get("unit_cost"), "unit_cost", errs)
        used = _date(r.get("used_on"), errs, "used_on")
        if used is None and "used_on must be YYYY-MM-DD" not in errs:
            errs.append("used_on is required")
        label = f"{code} - {desc}" if code and part is None and desc else desc
        out.append(
            {
                "row": i,
                "code": ref,
                "errors": errs,
                "wo": wo,
                "part": part,
                "description": label,
                "qty": qty,
                "uom": _s(r.get("uom")),
                "cost": cost,
                "used_on": used,
            }
        )
    errors = [{"row": r["row"], "code": r["code"], "errors": r["errors"]} for r in out if r["errors"]]
    return {
        "rows": out,
        "total": len(out),
        "valid": len(out) - len(errors),
        "invalid": len(errors),
        "errors": errors,
        "plans": sum(1 for r in out if r["part"] is not None),
    }


def commit_parts_history(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID) -> int:
    v = validate_parts_history(db, plant, rows)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    for rec in v["rows"]:
        p, wo = rec["part"], rec["wo"]
        q = Decimal(str(rec["qty"]))
        cost = Decimal(str(rec["cost"])) if rec["cost"] is not None else Decimal(str((p.average_cost or p.unit_price) if p else 0))
        u = PartUsage(
            plant_id=plant.id,
            work_order_id=wo.id,
            asset_id=wo.asset_id,
            part_id=p.id if p else None,
            description=None if p else (rec["description"] or "")[:300],
            quantity=q,
            uom=(rec["uom"] or (p.uom if p else "EA"))[:16],
            unit_cost=cost,
            total_cost=(q * cost).quantize(CENT),
            used_on=rec["used_on"],
            note="Migrated from previous system",
            created_by_id=user_id,
            created_at=utcnow(),
        )
        db.add(u)
        wo.actual_material_cost = Decimal(str(wo.actual_material_cost or 0)) + u.total_cost
    db.flush()
    audit(db, "history.parts_import", user_id=user_id, plant_id=plant.id, data={"lines": len(v["rows"])})
    return len(v["rows"])
