"""Bulk import of lubrication points (one row per point) into routes.

Points without a route_code are grouped into one route per department and frequency, so a weekly
grease round of an area becomes one lubrication work order. Preview validates; commit is all-or-nothing."""

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.enums import FrequencyUnit
from app.models.lubrication import LubeRoute, Lubricant, LubricationPoint
from app.models.tenancy import Department, Plant
from app.services.assets import new_qr_token
from app.services.common import audit, plant_today
from app.services.imports import _date, _num, _s
from app.services.pm_import import parse_frequency, spread_start

UNIT_DAYS = {FrequencyUnit.DAY: 1, FrequencyUnit.WEEK: 7, FrequencyUnit.MONTH: 30, FrequencyUnit.YEAR: 365}


def freq_days(v: Any) -> tuple[int, str, str] | None:
    f = parse_frequency(v)
    return (UNIT_DAYS[f[0]] * f[1], f[2], f[3]) if f else None


def validate_lube_plans(db: Session, plant: Plant, rows: list[dict]) -> dict:
    assets = {a.code.upper(): a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    lubes = {lb.code.upper(): lb for lb in db.execute(select(Lubricant).where(Lubricant.plant_id == plant.id)).scalars()}
    routes = {r.code.upper(): r for r in db.execute(select(LubeRoute).where(LubeRoute.plant_id == plant.id)).scalars()}
    depts = {d.id: d for d in db.execute(select(Department).where(Department.plant_id == plant.id)).scalars()}
    point_codes = {c.upper() for c in db.execute(select(LubricationPoint.code).where(LubricationPoint.plant_id == plant.id)).scalars()}
    per_asset = Counter(a for a in db.execute(select(LubricationPoint.asset_id).where(LubricationPoint.plant_id == plant.id)).scalars())
    new_lubes: dict[str, dict] = {}
    new_routes: dict[str, dict] = {}
    seen: dict[str, int] = {}
    out = []
    for i, r in enumerate(rows, start=2):
        errs: list[str] = []
        asset = assets.get((_s(r.get("asset_code")) or "").upper())
        if asset is None:
            errs.append(f"asset {_s(r.get('asset_code')) or '(blank)'} not found")
        lcode = (_s(r.get("lubricant_code")) or "").upper()
        if not lcode:
            errs.append("lubricant_code is required")
        elif lcode not in lubes and lcode not in new_lubes:
            kind = (_s(r.get("lubricant_type")) or "grease").lower()
            if not _s(r.get("lubricant_name")):
                errs.append(f"lubricant {lcode} is new: lubricant_name is required")
            elif kind not in ("grease", "oil"):
                errs.append("lubricant_type must be grease or oil")
            else:
                new_lubes[lcode] = {
                    "code": _s(r.get("lubricant_code")),
                    "product": _s(r.get("lubricant_name")),
                    "kind": kind,
                    "viscosity_grade": _s(r.get("viscosity_grade")),
                }
        qty = _num(r.get("quantity"), "quantity", errs)
        if not qty:
            errs.append("quantity must be > 0")
        fd = freq_days(r.get("frequency"))
        if fd is None:
            errs.append("frequency must be weekly/monthly/quarterly/semiannual/yearly or a number of days")
        start = _date(r.get("start_date"), errs, "start_date")
        rcode = (_s(r.get("route_code")) or "").upper()
        if asset is not None and fd is not None and not rcode:
            dept = depts[asset.department_id]
            rcode = f"LR-{dept.code}-{fd[1]}".upper()
            if rcode not in routes:
                new_routes.setdefault(rcode, {"code": rcode, "name": f"{fd[2]} lubrication – {dept.name}", "department_id": dept.id})
        elif rcode and rcode not in routes and rcode not in new_routes and asset is not None:
            new_routes[rcode] = {
                "code": _s(r.get("route_code")),
                "name": f"Lubrication route {_s(r.get('route_code'))}",
                "department_id": asset.department_id,
            }
        pcode = _s(r.get("point_code"))
        if not pcode and asset is not None:
            per_asset[asset.id] += 1
            pcode = f"{asset.code}-L{per_asset[asset.id]:02d}"
            while pcode.upper() in point_codes or pcode.upper() in seen:
                per_asset[asset.id] += 1
                pcode = f"{asset.code}-L{per_asset[asset.id]:02d}"
        if pcode:
            if len(pcode) > 40:
                errs.append("point_code longer than 40 characters")
            if pcode.upper() in point_codes:
                errs.append(f"lubrication point {pcode} already exists (imported before?)")
            if pcode.upper() in seen:
                errs.append(f"duplicate point_code in file (also row {seen[pcode.upper()]})")
            seen.setdefault(pcode.upper(), i)
        out.append(
            {
                "row": i,
                "code": pcode,
                "errors": errs,
                "asset": asset,
                "lubricant": lcode,
                "quantity": qty,
                "unit": _s(r.get("unit")) or "g",
                "component": _s(r.get("component")),
                "method": _s(r.get("method")),
                "days": fd[0] if fd else None,
                "route": rcode,
                "start": start,
            }
        )
    errors = [{"row": r["row"], "code": r["code"], "errors": r["errors"]} for r in out if r["errors"]]
    return {
        "rows": out,
        "new_lubricants": new_lubes,
        "new_routes": new_routes,
        "total": len(out),
        "valid": len(out) - len(errors),
        "invalid": len(errors),
        "errors": errors,
    }


def preview_dict(v: dict) -> dict:
    return {
        **{k: v[k] for k in ("total", "valid", "invalid", "errors")},
        "plans": len(v["new_routes"]),
        "new_lubricants": len(v["new_lubricants"]),
    }


def commit_lube_plans(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID) -> int:
    v = validate_lube_plans(db, plant, rows)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    lubes = {lb.code.upper(): lb for lb in db.execute(select(Lubricant).where(Lubricant.plant_id == plant.id)).scalars()}
    routes = {r.code.upper(): r for r in db.execute(select(LubeRoute).where(LubeRoute.plant_id == plant.id)).scalars()}
    for code, d in v["new_lubricants"].items():
        lubes[code] = Lubricant(
            plant_id=plant.id, code=d["code"], manufacturer="-", product=d["product"], kind=d["kind"], viscosity_grade=d["viscosity_grade"]
        )
        db.add(lubes[code])
    for code, d in v["new_routes"].items():
        routes[code] = LubeRoute(plant_id=plant.id, code=d["code"], name=d["name"][:200], department_id=d["department_id"])
        db.add(routes[code])
    db.flush()
    today = plant_today(plant)
    seq = Counter[str]()
    for r in v["rows"]:
        seq[r["route"]] += 10
        db.add(
            LubricationPoint(
                plant_id=plant.id,
                code=r["code"],
                asset_id=r["asset"].id,
                component=r["component"],
                lubricant_id=lubes[r["lubricant"]].id,
                quantity=r["quantity"],
                unit=r["unit"],
                method=r["method"],
                frequency_days=r["days"],
                route_id=routes[r["route"]].id,
                route_seq=seq[r["route"]],
                # Without a start date, points of one machine and frequency share a day inside the first cycle,
                # so routes are spread over the cycle instead of all falling due on the import day.
                next_due_date=r["start"] or spread_start(f"{r['asset'].code}-{r['days']}", FrequencyUnit.DAY, r["days"], today),
                qr_token=new_qr_token(),
            )
        )
    db.flush()
    audit(
        db,
        "lube.import",
        user_id=user_id,
        plant_id=plant.id,
        data={"points": len(v["rows"]), "routes": len(v["new_routes"]), "lubricants": len(v["new_lubricants"])},
    )
    return len(v["rows"])
