"""CSV/XLSX import with preview (dry-run), validation, duplicate detection and error report.
Commit is all-or-nothing: any error aborts the whole import (safe recovery = nothing partially written)."""

import csv
import io
import uuid
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.enums import ASSET_LEVEL_ORDER, AssetLevel, Criticality
from app.models.inventory import Part, Warehouse
from app.models.tenancy import Department, Plant
from app.services import inventory as inv
from app.services.assets import compute_path, new_qr_token
from app.services.common import audit

MAX_ROWS = 20000

TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "assets": [
        ("code", "Unique equipment code, e.g. PM1-WIRE-UTW-DR1"),
        ("name", "Description"),
        ("department_code", "PM | SP | FH | WWTP | EAI | UTIL (department code in this plant)"),
        ("parent_code", "Code of the parent asset (blank for production lines)"),
        ("level", "production_line | unit | assembly | sub_assembly | component"),
        ("criticality", "A | B | C"),
        ("oem", "Manufacturer"),
        ("model", "Model"),
        ("serial_number", "Serial"),
        ("install_date", "YYYY-MM-DD"),
        ("location", "Location"),
        ("description", "Long description"),
        ("name_ar", "Arabic name (optional)"),
        ("equipment_type", "Pumps | Electric Motors | Gearboxes ... (optional; picks the failure modes offered on work orders)"),
    ],
    "parts": [
        ("code", "Unique item code"),
        ("description", "Description"),
        ("oem_part_number", "OEM P/N"),
        ("manufacturer", "Manufacturer"),
        ("uom", "Unit of measure, e.g. EA, KG, L"),
        ("criticality", "A | B | C"),
        ("is_critical_spare", "yes | no"),
        ("min_qty", "number"),
        ("max_qty", "number"),
        ("reorder_point", "number"),
        ("safety_stock", "number"),
        ("lead_time_days", "integer"),
        ("unit_price", "number"),
        ("category", "text"),
        ("warehouse", "Store / warehouse code for the opening stock (created if new; blank = the only store)"),
        ("qty_on_hand", "Opening stock quantity now on the shelf (optional; booked as an opening-stock receipt at unit_price)"),
        ("bin", "Shelf / bin location (optional)"),
    ],
    "pm_plans": [
        ("asset_code", "Code of an existing asset; tasks of the same asset + frequency + trade become one PM plan"),
        ("frequency", "weekly | biweekly | monthly | bimonthly | quarterly | semiannual | yearly, or a number of days (7, 30, 90, 365)"),
        ("task", "Activity; numbered steps (1. ... 2. ...) become separate checklist items"),
        ("trade", "Mechanical | Electrical | Instrumentation | Operations ... (who does it)"),
        ("duration_min", "Minutes for this task (summed per plan)"),
        ("crew", "Number of people"),
        ("shutdown_required", "yes / offline if the machine must be stopped, otherwise no / online"),
        ("start_date", "YYYY-MM-DD of the first due date (blank = spread evenly over the first cycle)"),
        ("priority", "P1 | P2 | P3 | P4 (blank = P3)"),
        (
            "permit",
            "blank/no, yes (= cold_work) or types: cold_work, hot_work, electrical, confined_space, work_at_height, excavation, lifting, chemical",
        ),
        ("loto", "yes if energy isolation (lock-out / tag-out) is required, otherwise no"),
    ],
    "wo_history": [
        ("external_ref", "Work order / service order number in the previous system (unique)"),
        ("asset_code", "Code of an existing asset"),
        ("type", "breakdown | corrective | preventive | inspection | improvement | shutdown | workshop | lubrication | predictive"),
        ("title", "Short description of the job"),
        ("description", "Details / remarks (optional)"),
        ("trade", "Mechanical | Electrical | Instrumentation | Workshop ... (optional)"),
        ("failure_mode", "e.g. WEAR AND TEAR (optional)"),
        ("technician", "Name(s) as text (optional)"),
        ("priority", "P1-P4 or High / Medium / Low (blank = P3)"),
        ("original_status", "Status in the old system, kept for reference (optional)"),
        ("breakdown", "yes if the machine stopped (counts in MTBF / MTTR / availability)"),
        ("reported_at", "YYYY-MM-DD HH:MM when the job was raised"),
        ("started_at", "YYYY-MM-DD HH:MM (optional)"),
        ("completed_at", "YYYY-MM-DD HH:MM (optional)"),
        ("closed_at", "YYYY-MM-DD HH:MM (optional; blank = completed_at or reported_at)"),
        ("downtime_hours", "number (optional; used when completed_at is blank)"),
        ("repair_minutes", "Labour minutes (optional)"),
        ("findings", "Technician remark / work done (optional)"),
    ],
    "parts_history": [
        ("wo_external_ref", "external_ref of an imported history work order"),
        ("part_code", "Spare part code (blank if the item is not in the spare-parts list)"),
        ("description", "Item description (required when part_code is blank or unknown)"),
        ("quantity", "number > 0"),
        ("uom", "Unit (optional)"),
        ("unit_cost", "Unit cost (blank = book cost of the part)"),
        ("used_on", "YYYY-MM-DD"),
    ],
    "lube_plans": [
        ("asset_code", "Code of an existing asset"),
        ("component", "Lubricated part, e.g. Drive-side bearing"),
        ("lubricant_code", "Lubricant code; a new code is created from the next three columns"),
        ("lubricant_name", "Product, e.g. Mobilux EP 2 (needed only for a new lubricant code)"),
        ("lubricant_type", "grease | oil"),
        ("viscosity_grade", "e.g. NLGI 2 or ISO VG 220"),
        ("quantity", "Amount per service"),
        ("unit", "g | kg | ml | L (blank = g)"),
        ("method", "Grease gun / top-up / oil change ..."),
        ("frequency", "weekly | monthly | quarterly | yearly ... or a number of days"),
        ("route_code", "Optional route; blank = one route per department and frequency, e.g. LR-PM-W"),
        ("start_date", "YYYY-MM-DD first due date (blank = today)"),
        ("point_code", "Optional; blank = generated from the asset code"),
    ],
    "work_orders": [
        ("asset_code", "Code of an existing asset in your departments (blank if pm_plan_code is given)"),
        ("title", "Short description of the job (blank = PM plan name)"),
        (
            "type",
            "preventive | predictive | corrective | inspection | improvement | shutdown | lubrication (blank = corrective, or the PM plan's type)",
        ),
        ("priority", "P1 | P2 | P3 | P4 (blank = P3)"),
        ("due_date", "YYYY-MM-DD"),
        ("planned_start", "YYYY-MM-DD (optional)"),
        ("estimated_hours", "number (optional)"),
        ("assign_to", "E-mail or employee number of technicians, several separated by commas (optional)"),
        ("pm_plan_code", "Optional: release the next waiting occurrence of this PM / PdM plan instead of a new job"),
        ("description", "Details (optional)"),
    ],
    "shutdown_plan": [
        ("shutdown_code", "Code of the shutdown; a new code creates it from the next three columns"),
        ("shutdown_name", "Name of a new shutdown (first row of that shutdown is enough)"),
        ("shutdown_start", "YYYY-MM-DD HH:MM start of a new shutdown"),
        ("shutdown_end", "YYYY-MM-DD HH:MM end of a new shutdown"),
        ("package_code", "Work package code, unique within the shutdown (existing codes are updated)"),
        ("package_name", "What is done"),
        ("asset_code", "Equipment code (optional)"),
        ("duration_hours", "Hours > 0"),
        ("planned_manpower", "Own people (optional)"),
        ("contractor_manpower", "Contractor people (optional)"),
        ("owner", "E-mail of the responsible person (optional)"),
        ("predecessors", "Package codes that must finish first, separated by commas (optional)"),
        ("material_status", "not_ready | partial | ready | not_required (optional)"),
        ("permit_status", "not_ready | partial | ready | not_required (optional)"),
        ("loto_status", "not_ready | partial | ready | not_required (optional)"),
        ("create_wo", "yes = create a shutdown work order for the equipment (optional)"),
    ],
    "pdm_plans": [
        ("asset_code", "Code of an existing asset"),
        ("point_name", "What is measured, e.g. Motor DE bearing vibration"),
        ("technique", "vibration | temperature | thermography | ultrasound | oil_analysis | motor_current | pressure | flow | other"),
        ("unit", "e.g. mm/s, °C, A, bar"),
        ("frequency", "How often readings are taken: weekly | monthly | quarterly ... or days"),
        ("warning_high", "number (optional)"),
        ("alarm_high", "number (optional)"),
        ("warning_low", "number (optional)"),
        ("alarm_low", "number (optional)"),
        ("baseline", "number (optional)"),
        ("trade", "Who takes the readings, e.g. Reliability (blank = Reliability)"),
        ("start_date", "YYYY-MM-DD first round (blank = spread evenly over the first cycle)"),
        ("point_code", "Optional; blank = generated from the asset code"),
        ("priority", "critical | high | normal (blank = normal): critical points are listed first for technicians"),
    ],
}


def read_rows(filename: str, content: bytes) -> list[dict[str, Any]]:
    name = filename.lower()
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    elif name.endswith(".xlsx"):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(it, [])]
        rows = []
        for r in it:
            if r is None or all(v is None or str(v).strip() == "" for v in r):
                continue
            rows.append({header[i]: r[i] for i in range(min(len(header), len(r))) if header[i]})
    else:
        raise ValueError("Only .csv and .xlsx files are supported")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"Too many rows (max {MAX_ROWS})")
    return [{(k or "").strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()} for r in rows]


def _s(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _num(v: Any, field: str, errs: list[str], integer: bool = False) -> float | int | None:
    if _s(v) is None:
        return None
    try:
        x = float(str(v).replace(",", ""))
        if x < 0:
            errs.append(f"{field} must be ≥ 0")
            return None
        return int(x) if integer else x
    except ValueError:
        errs.append(f"{field} is not a number")
        return None


def _date(v: Any, errs: list[str], field: str = "install_date") -> date | None:
    if v is None or _s(v) is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        errs.append(f"{field} must be YYYY-MM-DD")
        return None


def validate_assets(db: Session, plant: Plant, rows: list[dict]) -> dict:
    depts = {d.code.upper(): d for d in db.execute(select(Department).where(Department.plant_id == plant.id)).scalars()}
    existing = {a.code.upper(): a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    seen: dict[str, int] = {}
    file_rows: dict[str, dict] = {}
    results = []
    for i, r in enumerate(rows, start=2):  # row 1 = header
        errs: list[str] = []
        code = _s(r.get("code"))
        name = _s(r.get("name"))
        if not code:
            errs.append("code is required")
        if not name:
            errs.append("name is required")
        cu = (code or "").upper()
        if code and cu in seen:
            errs.append(f"duplicate code in file (also row {seen[cu]})")
        if code and cu in existing:
            errs.append("duplicate: code already exists in this plant")
        if code:
            seen.setdefault(cu, i)
        dept = depts.get((_s(r.get("department_code")) or "").upper())
        if dept is None:
            errs.append("unknown department_code")
        try:
            level = AssetLevel((_s(r.get("level")) or "").lower())
        except ValueError:
            errs.append("invalid level")
            level = None
        try:
            crit = Criticality((_s(r.get("criticality")) or "C").upper())
        except ValueError:
            errs.append("criticality must be A, B or C")
            crit = Criticality.C
        inst = _date(r.get("install_date"), errs)
        rec = {
            "row": i,
            "code": code,
            "name": name,
            "department": dept,
            "parent_code": _s(r.get("parent_code")),
            "level": level,
            "criticality": crit,
            "install_date": inst,
            "errors": errs,
            "raw": r,
        }
        results.append(rec)
        if code and cu not in file_rows:
            file_rows[cu] = rec
    # Hierarchy checks after all rows are known (parents may appear later in the file or already exist).
    for rec in results:
        if rec["level"] is None or rec["department"] is None:
            continue
        pc = (rec["parent_code"] or "").upper()
        if not pc:
            if rec["level"] != AssetLevel.PRODUCTION_LINE:
                rec["errors"].append("parent_code required for levels below production_line")
            continue
        parent_level, parent_dept = None, None
        if pc in existing:
            parent_level, parent_dept = existing[pc].level, existing[pc].department_id
        elif pc in file_rows and file_rows[pc] is not rec:
            parent_level = file_rows[pc]["level"]
            parent_dept = file_rows[pc]["department"].id if file_rows[pc]["department"] else None
        else:
            rec["errors"].append(f"parent_code {rec['parent_code']} not found")
            continue
        if parent_level is not None and ASSET_LEVEL_ORDER.index(rec["level"]) <= ASSET_LEVEL_ORDER.index(parent_level):
            rec["errors"].append(f"{rec['level'].value} cannot be under {parent_level.value}")
        if parent_dept is not None and parent_dept != rec["department"].id:
            rec["errors"].append("parent belongs to a different department")
    # Cycle detection among in-file parents.
    for rec in results:
        seen_chain = set()
        cur = rec
        while cur and cur["parent_code"]:
            key = cur["parent_code"].upper()
            if key in seen_chain:
                rec["errors"].append("circular parent reference")
                break
            seen_chain.add(key)
            cur = file_rows.get(key)
    errors = [{"row": r["row"], "code": r["code"], "errors": r["errors"]} for r in results if r["errors"]]
    return {"rows": results, "total": len(results), "valid": len(results) - len(errors), "invalid": len(errors), "errors": errors}


def commit_assets(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID) -> int:
    v = validate_assets(db, plant, rows)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    existing = {a.code.upper(): a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    pending = list(v["rows"])
    created: dict[str, Asset] = {}
    while pending:
        progressed = False
        for rec in list(pending):
            pc = (rec["parent_code"] or "").upper()
            parent = existing.get(pc) or created.get(pc) if pc else None
            if pc and parent is None:
                continue
            a = Asset(
                id=uuid.uuid4(),
                plant_id=plant.id,
                department_id=rec["department"].id,
                parent_id=parent.id if parent else None,
                level=rec["level"],
                code=rec["code"],
                name=rec["name"],
                name_ar=_s(rec["raw"].get("name_ar")),
                criticality=rec["criticality"],
                oem=_s(rec["raw"].get("oem")),
                model=_s(rec["raw"].get("model")),
                serial_number=_s(rec["raw"].get("serial_number")),
                install_date=rec["install_date"],
                location=_s(rec["raw"].get("location")),
                description=_s(rec["raw"].get("description")),
                equipment_type=(_s(rec["raw"].get("equipment_type")) or "")[:60] or None,
                qr_token=new_qr_token(),
                created_by_id=user_id,
            )
            a.path = compute_path(parent, a.id)
            db.add(a)
            created[rec["code"].upper()] = a
            pending.remove(rec)
            progressed = True
        if not progressed:
            raise ValueError("Unresolvable parent references")
    db.flush()
    audit(db, "asset.import", user_id=user_id, plant_id=plant.id, data={"created": len(created)})
    return len(created)


def validate_parts(db: Session, plant: Plant, rows: list[dict]) -> dict:
    existing = {c.upper() for c in db.execute(select(Part.code).where(Part.plant_id == plant.id)).scalars()}
    existing_pn = {
        (p.manufacturer or "").upper() + "|" + (p.oem_part_number or "").upper(): p.code
        for p in db.execute(select(Part).where(Part.plant_id == plant.id, Part.oem_part_number.is_not(None))).scalars()
    }
    warehouses = {w.code.upper(): w for w in db.execute(select(Warehouse).where(Warehouse.plant_id == plant.id)).scalars()}
    file_stores = {w for r in rows if (w := _s(r.get("warehouse")))}
    seen: dict[str, int] = {}
    out = []
    for i, r in enumerate(rows, start=2):
        errs: list[str] = []
        warns: list[str] = []
        code, desc = _s(r.get("code")), _s(r.get("description"))
        if not code:
            errs.append("code is required")
        if not desc:
            errs.append("description is required")
        cu = (code or "").upper()
        if code and cu in seen:
            errs.append(f"duplicate code in file (also row {seen[cu]})")
        if code and cu in existing:
            errs.append("duplicate: code already exists")
        seen.setdefault(cu, i)
        pn_key = (_s(r.get("manufacturer")) or "").upper() + "|" + (_s(r.get("oem_part_number")) or "").upper()
        if _s(r.get("oem_part_number")) and pn_key in existing_pn:
            warns.append(f"possible duplicate of {existing_pn[pn_key]} (same manufacturer + OEM P/N)")
        try:
            crit = Criticality((_s(r.get("criticality")) or "C").upper())
        except ValueError:
            errs.append("criticality must be A, B or C")
            crit = Criticality.C
        vals = {f: _num(r.get(f), f, errs) for f in ("min_qty", "max_qty", "reorder_point", "safety_stock", "unit_price")}
        lt = _num(r.get("lead_time_days"), "lead_time_days", errs, integer=True)
        if vals["min_qty"] and vals["max_qty"] and vals["min_qty"] > vals["max_qty"]:
            errs.append("min_qty exceeds max_qty")
        crit_spare = (_s(r.get("is_critical_spare")) or "no").lower() in {"yes", "y", "true", "1"}
        qty = _num(r.get("qty_on_hand"), "qty_on_hand", errs)
        if qty is not None and qty < 0:
            errs.append("qty_on_hand cannot be negative")
        wh_code = _s(r.get("warehouse"))
        if qty and not wh_code:
            stores = {w.code for w in warehouses.values()} | file_stores
            if len(stores) <= 1:
                wh_code = next(iter(stores), "MAIN")  # one store (or none yet: a store called MAIN is created)
            else:
                errs.append("warehouse is required for qty_on_hand (more than one store)")
        if qty and wh_code and wh_code.upper() not in warehouses:
            warns.append(f"new store '{wh_code}' will be created")
        out.append(
            {
                "row": i,
                "code": code,
                "description": desc,
                "criticality": crit,
                "values": vals,
                "lead_time_days": lt,
                "is_critical_spare": crit_spare,
                "qty_on_hand": qty or 0,
                "warehouse": wh_code,
                "raw": r,
                "errors": errs,
                "warnings": warns,
            }
        )
    errors = [{"row": r["row"], "code": r["code"], "errors": r["errors"]} for r in out if r["errors"]]
    warnings = [{"row": r["row"], "code": r["code"], "warnings": r["warnings"]} for r in out if r["warnings"]]
    return {"rows": out, "total": len(out), "valid": len(out) - len(errors), "invalid": len(errors), "errors": errors, "warnings": warnings}


def commit_parts(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID) -> int:
    v = validate_parts(db, plant, rows)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    warehouses = {w.code.upper(): w for w in db.execute(select(Warehouse).where(Warehouse.plant_id == plant.id)).scalars()}
    stocked = 0
    for rec in v["rows"]:
        vals = {k: (x or 0) for k, x in rec["values"].items()}
        part = Part(
            plant_id=plant.id,
            code=rec["code"],
            description=rec["description"],
            criticality=rec["criticality"],
            oem_part_number=_s(rec["raw"].get("oem_part_number")),
            manufacturer=_s(rec["raw"].get("manufacturer")),
            uom=_s(rec["raw"].get("uom")) or "EA",
            category=_s(rec["raw"].get("category")),
            is_critical_spare=rec["is_critical_spare"],
            lead_time_days=rec["lead_time_days"],
            currency=plant.currency,
            average_cost=vals["unit_price"],
            created_by_id=user_id,
            **vals,
        )
        db.add(part)
        db.flush()
        if rec["qty_on_hand"] > 0:
            key = rec["warehouse"].upper()
            if key not in warehouses:
                warehouses[key] = Warehouse(plant_id=plant.id, code=rec["warehouse"][:32], name=rec["warehouse"][:120])
                db.add(warehouses[key])
                db.flush()
            bin_ = _s(rec["raw"].get("bin"))
            if bin_:
                inv.lock_stock(db, plant, part, warehouses[key]).bin = bin_[:40]
                db.flush()
            inv.receive(db, plant, part, warehouses[key], rec["qty_on_hand"], vals["unit_price"], user_id, "Opening stock (import)")
            stocked += 1
    db.flush()
    audit(db, "part.import", user_id=user_id, plant_id=plant.id, data={"created": len(v["rows"]), "with_stock": stocked})
    return len(v["rows"])


def template_xlsx(kind: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = kind
    cols = TEMPLATES[kind]
    ws.append([c for c, _ in cols])
    ws.append([f"<{h}>" for _, h in cols])
    help_ws = wb.create_sheet("instructions")
    help_ws.append(["column", "meaning"])
    for c, h in cols:
        help_ws.append([c, h])
    help_ws.append([])
    help_ws.append(
        [
            "Delete the example row 2 before importing. Use Preview first; nothing is written until Commit, "
            "and Commit is rejected if any row has errors."
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def errors_csv(errors: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["row", "code", "error"])
    for e in errors:
        for msg in e["errors"]:
            w.writerow([e["row"], e["code"] or "", msg])
    return buf.getvalue()
