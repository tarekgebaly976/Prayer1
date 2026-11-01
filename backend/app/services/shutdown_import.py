"""Shutdown plan import: the planning team / engineers upload the shutdown's work packages from Excel.

One row per package. The shutdown is found by `shutdown_code`; a new code creates the shutdown from
`shutdown_name`, `shutdown_start` and `shutdown_end`. Existing package codes are updated, new ones added, and the
predecessors listed on a row replace that package's dependencies; the critical path is recalculated. With
`create_wo` = yes, a shutdown work order is created for the package's equipment (once). Preview validates; commit is
all-or-nothing, like the other imports."""

import uuid
from collections import defaultdict, deque
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.enums import ReadinessStatus, ShutdownStatus, WOType
from app.models.identity import Membership, User
from app.models.shutdowns import PackageDependency, Shutdown, ShutdownPackage
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services.common import audit
from app.services.imports import _num, _s

YES = {"yes", "y", "true", "1", "x"}
READY_ALIASES = {"no": "not_ready", "not ready": "not_ready", "n/a": "not_required", "na": "not_required", "not required": "not_required"}


def _dt(v: object, tz: ZoneInfo, field: str, errs: list[str]) -> datetime | None:
    if v is None or _s(v) is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=tz)
    if isinstance(v, date):
        return datetime.combine(v, time(0, 0), tz)
    txt = str(v).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    errs.append(f"{field} must be YYYY-MM-DD HH:MM")
    return None


def _ready(v: object, field: str, errs: list[str]) -> ReadinessStatus | None:
    raw = (_s(v) or "").lower()
    if not raw:
        return None
    try:
        return ReadinessStatus(READY_ALIASES.get(raw, raw.replace(" ", "_")))
    except ValueError:
        errs.append(f"{field} must be one of: " + ", ".join(r.value for r in ReadinessStatus))
        return None


def _has_cycle(edges: dict[str, set[str]]) -> bool:
    nodes = set(edges) | {p for ps in edges.values() for p in ps}
    indeg = dict.fromkeys(nodes, 0)
    succ: dict[str, list[str]] = defaultdict(list)
    for n, ps in edges.items():
        for p in ps:
            succ[p].append(n)
            indeg[n] += 1
    q = deque(n for n, d in indeg.items() if d == 0)
    seen = 0
    while q:
        n = q.popleft()
        seen += 1
        for s in succ[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                q.append(s)
    return seen != len(nodes)


def validate_shutdown_plan(db: Session, plant: Plant, rows: list[dict]) -> dict:
    tz = ZoneInfo(plant.timezone)
    shutdowns = {s.code.upper(): s for s in db.execute(select(Shutdown).where(Shutdown.plant_id == plant.id)).scalars()}
    assets = {a.code.upper(): a for a in db.execute(select(Asset).where(Asset.plant_id == plant.id)).scalars()}
    people = {
        u.email.lower(): u.id
        for u in db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.plant_id == plant.id, Membership.is_active.is_(True))
        ).scalars()
    }
    new_sd: dict[str, dict] = {}
    seen: dict[tuple[str, str], int] = {}
    out: list[dict] = []
    for i, r in enumerate(rows, start=2):
        errs: list[str] = []
        sdc = (_s(r.get("shutdown_code")) or "").upper()
        pkc = (_s(r.get("package_code")) or "").upper()
        if not sdc:
            errs.append("shutdown_code is required")
        if not pkc:
            errs.append("package_code is required")
        sd = shutdowns.get(sdc)
        if sdc and sd is None:
            info = new_sd.setdefault(sdc, {"name": None, "start": None, "end": None})
            info["name"] = info["name"] or _s(r.get("shutdown_name"))
            info["start"] = info["start"] or _dt(r.get("shutdown_start"), tz, "shutdown_start", errs)
            info["end"] = info["end"] or _dt(r.get("shutdown_end"), tz, "shutdown_end", errs)
        elif sd is not None and sd.status in (ShutdownStatus.COMPLETED, ShutdownStatus.CANCELLED):
            errs.append(f"shutdown {sd.code} is {sd.status.value}")
        if sdc and pkc:
            if (sdc, pkc) in seen:
                errs.append(f"duplicate package_code in file (also row {seen[(sdc, pkc)]})")
            seen[(sdc, pkc)] = i
        name = _s(r.get("package_name"))
        if not name:
            errs.append("package_name is required")
        hours = _num(r.get("duration_hours"), "duration_hours", errs)
        if hours is None or hours <= 0:
            errs.append("duration_hours must be a number > 0")
        acode = (_s(r.get("asset_code")) or "").upper()
        asset = assets.get(acode) if acode else None
        if acode and asset is None:
            errs.append(f"asset {acode} not found")
        owner = (_s(r.get("owner")) or "").lower()
        if owner and owner not in people:
            errs.append(f"owner {owner} is not an active member of this plant")
        create_wo = (_s(r.get("create_wo")) or "").lower() in YES
        if create_wo and asset is None:
            errs.append("create_wo needs an asset_code")
        out.append(
            {
                "row": i,
                "code": f"{sdc}/{pkc}" if sdc and pkc else (pkc or sdc or None),
                "errors": errs,
                "shutdown_code": sdc,
                "package_code": pkc,
                "name": name,
                "hours": hours,
                "asset": asset,
                "owner_id": people.get(owner) if owner else None,
                "manpower": _num(r.get("planned_manpower"), "planned_manpower", errs, integer=True),
                "contractor_manpower": _num(r.get("contractor_manpower"), "contractor_manpower", errs, integer=True),
                "material_status": _ready(r.get("material_status"), "material_status", errs),
                "permit_status": _ready(r.get("permit_status"), "permit_status", errs),
                "loto_status": _ready(r.get("loto_status"), "loto_status", errs),
                "predecessors": [p.strip().upper() for p in (_s(r.get("predecessors")) or "").replace(";", ",").split(",") if p.strip()],
                "create_wo": create_wo,
            }
        )
    # New shutdowns need a name and a window.
    for sdc, info in new_sd.items():
        problem = None
        if not (info["name"] and info["start"] and info["end"]):
            problem = f"shutdown {sdc} does not exist: give shutdown_name, shutdown_start and shutdown_end to create it"
        elif info["end"] <= info["start"]:
            problem = f"shutdown {sdc}: shutdown_end must be after shutdown_start"
        if problem:
            for rec in out:
                if rec["shutdown_code"] == sdc:
                    rec["errors"].append(problem)
    # Predecessors must be packages of the same shutdown (in the file or already there), without cycles.
    existing: dict[str, set[str]] = defaultdict(set)
    existing_deps: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for sdc, sd in shutdowns.items():
        pk = {p.id: p.code.upper() for p in db.execute(select(ShutdownPackage).where(ShutdownPackage.shutdown_id == sd.id)).scalars()}
        existing[sdc] = set(pk.values())
        if pk:
            for d in db.execute(select(PackageDependency).where(PackageDependency.package_id.in_(pk))).scalars():
                existing_deps[sdc][pk[d.package_id]].add(pk[d.predecessor_id])
    by_sd: dict[str, list[dict]] = defaultdict(list)
    for rec in out:
        by_sd[rec["shutdown_code"]].append(rec)
    for sdc, recs in by_sd.items():
        known = existing[sdc] | {r["package_code"] for r in recs}
        edges = {k: set(v) for k, v in existing_deps[sdc].items()}
        for rec in recs:
            for p in rec["predecessors"]:
                if p == rec["package_code"]:
                    rec["errors"].append("a package cannot be its own predecessor")
                elif p not in known:
                    rec["errors"].append(f"predecessor {p} is not a package of shutdown {sdc}")
            edges[rec["package_code"]] = set(rec["predecessors"]) & known - {rec["package_code"]}
        if sdc and _has_cycle(edges):
            for rec in recs:
                if rec["predecessors"]:
                    rec["errors"].append("the predecessors form a loop (A after B after A)")
    errors = [{"row": r["row"], "code": r["code"], "errors": r["errors"]} for r in out if r["errors"]]
    return {
        "rows": out,
        "new_shutdowns": new_sd,
        "total": len(out),
        "valid": len(out) - len(errors),
        "invalid": len(errors),
        "errors": errors,
        "plans": len(by_sd),  # shown as "shutdowns"
    }


def preview_dict(v: dict) -> dict:
    return {k: v[k] for k in ("total", "valid", "invalid", "errors", "plans")}


def commit_shutdown_plan(db: Session, plant: Plant, rows: list[dict], user_id: uuid.UUID) -> int:
    from app.services import shutdowns as sdsvc
    from app.services import workorders as wosvc

    v = validate_shutdown_plan(db, plant, rows)
    if v["invalid"]:
        raise ValueError("Import has validation errors; nothing was imported")
    sds = {s.code.upper(): s for s in db.execute(select(Shutdown).where(Shutdown.plant_id == plant.id)).scalars()}
    for sdc, info in v["new_shutdowns"].items():
        sd = Shutdown(plant_id=plant.id, code=sdc, name=info["name"], planned_start=info["start"], planned_end=info["end"])
        db.add(sd)
        sds[sdc] = sd
    db.flush()
    pkgs: dict[tuple[str, str], ShutdownPackage] = {}
    for sdc, sd in sds.items():
        for p in db.execute(select(ShutdownPackage).where(ShutdownPackage.shutdown_id == sd.id)).scalars():
            pkgs[(sdc, p.code.upper())] = p
    for rec in v["rows"]:
        key = (rec["shutdown_code"], rec["package_code"])
        p = pkgs.get(key)
        if p is None:
            p = ShutdownPackage(plant_id=plant.id, shutdown_id=sds[key[0]].id, code=key[1], name=rec["name"], duration_hours=rec["hours"])
            db.add(p)
            pkgs[key] = p
        p.name, p.duration_hours = rec["name"], rec["hours"]
        if rec["asset"] is not None:
            p.asset_id = rec["asset"].id
        if rec["owner_id"]:
            p.owner_id = rec["owner_id"]
        for f in ("manpower", "contractor_manpower"):
            if rec[f] is not None:
                setattr(p, "planned_manpower" if f == "manpower" else f, rec[f])
        for f in ("material_status", "permit_status", "loto_status"):
            if rec[f] is not None:
                setattr(p, f, rec[f])
    db.flush()
    touched: set[str] = set()
    for rec in v["rows"]:
        p = pkgs[(rec["shutdown_code"], rec["package_code"])]
        touched.add(rec["shutdown_code"])
        for d in db.execute(select(PackageDependency).where(PackageDependency.package_id == p.id)).scalars():
            db.delete(d)
        db.flush()
        for pc in rec["predecessors"]:
            db.add(PackageDependency(package_id=p.id, predecessor_id=pkgs[(rec["shutdown_code"], pc)].id, lag_hours=0))
        if rec["create_wo"]:
            sd = sds[rec["shutdown_code"]]
            already = db.execute(select(WorkOrder.id).where(WorkOrder.shutdown_package_id == p.id).limit(1)).first()
            if not already:
                wo = wosvc.create_work_order(
                    db,
                    plant,
                    asset=rec["asset"],
                    type=WOType.SHUTDOWN,
                    title=f"{sd.code} {p.code} {p.name}"[:200],
                    user_id=user_id,
                    due_date=sd.planned_end.astimezone(ZoneInfo(plant.timezone)).date(),
                    shutdown_package_id=p.id,
                )
                wo.planned_start, wo.planned_end = sd.planned_start, sd.planned_end
                wo.estimated_hours = rec["hours"]
    db.flush()
    for sdc in touched:
        sdsvc.compute_cpm(db, sds[sdc])
    audit(db, "shutdown.import", user_id=user_id, plant_id=plant.id, data={"packages": len(v["rows"]), "shutdowns": sorted(touched)})
    return len(v["rows"])
