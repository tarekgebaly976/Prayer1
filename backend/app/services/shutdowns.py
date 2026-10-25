"""Shutdown planning with critical-path (CPM) scheduling over package dependencies."""

import uuid
from collections import defaultdict, deque
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.enums import PackageStatus, ReadinessStatus
from app.models.shutdowns import PackageDependency, Shutdown, ShutdownCheck, ShutdownPackage


def _topo(pkgs: dict[uuid.UUID, ShutdownPackage], deps: list[PackageDependency]) -> list[uuid.UUID]:
    indeg = {k: 0 for k in pkgs}
    succ: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for d in deps:
        succ[d.predecessor_id].append(d.package_id)
        indeg[d.package_id] += 1
    q = deque(sorted((k for k, v in indeg.items() if v == 0), key=lambda k: pkgs[k].code))
    order = []
    while q:
        n = q.popleft()
        order.append(n)
        for s in succ[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                q.append(s)
    if len(order) != len(pkgs):
        raise DomainError("Dependency cycle detected between packages", "dependency_cycle", 422)
    return order


def compute_cpm(db: Session, sd: Shutdown) -> dict:
    pkgs = {p.id: p for p in db.execute(select(ShutdownPackage).where(ShutdownPackage.shutdown_id == sd.id)).scalars()}
    if not pkgs:
        return {"duration_hours": 0, "critical_path": []}
    deps = list(db.execute(select(PackageDependency).where(PackageDependency.package_id.in_(pkgs))).scalars())
    order = _topo(pkgs, deps)
    preds: dict[uuid.UUID, list[PackageDependency]] = defaultdict(list)
    succs: dict[uuid.UUID, list[PackageDependency]] = defaultdict(list)
    for d in deps:
        preds[d.package_id].append(d)
        succs[d.predecessor_id].append(d)
    es: dict[uuid.UUID, float] = {}
    ef: dict[uuid.UUID, float] = {}
    for n in order:
        es[n] = max((ef[d.predecessor_id] + float(d.lag_hours) for d in preds[n]), default=0.0)
        ef[n] = es[n] + float(pkgs[n].duration_hours)
    project = max(ef.values())
    lf: dict[uuid.UUID, float] = {}
    ls: dict[uuid.UUID, float] = {}
    for n in reversed(order):
        lf[n] = min((ls[d.package_id] - float(d.lag_hours) for d in succs[n]), default=project)
        ls[n] = lf[n] - float(pkgs[n].duration_hours)
    critical = []
    for n in order:
        p = pkgs[n]
        tf = round(ls[n] - es[n], 4)
        p.total_float_hours = Decimal(str(tf))
        p.is_critical = abs(tf) < 1e-6
        p.planned_start = sd.planned_start + timedelta(hours=es[n])
        p.planned_finish = sd.planned_start + timedelta(hours=ef[n])
        if p.is_critical:
            critical.append(p.code)
    planned_window = (sd.planned_end - sd.planned_start).total_seconds() / 3600
    return {
        "duration_hours": project,
        "critical_path": critical,
        "planned_window_hours": planned_window,
        "fits_window": project <= planned_window,
    }


def add_dependency(db: Session, sd: Shutdown, pkg: ShutdownPackage, pred: ShutdownPackage, lag: float) -> None:
    if pkg.shutdown_id != sd.id or pred.shutdown_id != sd.id:
        raise DomainError("Packages must belong to the same shutdown", "invalid_dependency", 422)
    d = PackageDependency(package_id=pkg.id, predecessor_id=pred.id, lag_hours=lag)
    db.add(d)
    db.flush()
    try:
        compute_cpm(db, sd)
    except DomainError:
        db.delete(d)
        db.flush()
        raise


def readiness(db: Session, sd: Shutdown) -> dict:
    pkgs = list(db.execute(select(ShutdownPackage).where(ShutdownPackage.shutdown_id == sd.id)).scalars())
    checks = list(db.execute(select(ShutdownCheck).where(ShutdownCheck.shutdown_id == sd.id)).scalars())

    def pct(attr: str) -> float | None:
        if not pkgs:
            return None
        ok = sum(1 for p in pkgs if getattr(p, attr) in (ReadinessStatus.READY, ReadinessStatus.NOT_REQUIRED))
        return round(100 * ok / len(pkgs), 1)

    total_h = sum(float(p.duration_hours) for p in pkgs)
    progress = round(sum(float(p.duration_hours) * float(p.progress_pct) for p in pkgs) / total_h, 1) if total_h else None
    return {
        "packages": len(pkgs),
        "materials_ready_pct": pct("material_status"),
        "permits_ready_pct": pct("permit_status"),
        "loto_ready_pct": pct("loto_status"),
        "weighted_progress_pct": progress,
        "completed": sum(1 for p in pkgs if p.status == PackageStatus.COMPLETED),
        "delayed": [{"code": p.code, "reason": p.delay_reason} for p in pkgs if p.status == PackageStatus.DELAYED],
        "manpower_internal": sum(p.planned_manpower for p in pkgs),
        "manpower_contractor": sum(p.contractor_manpower for p in pkgs),
        "pre_startup_checks_done": sum(1 for c in checks if c.is_done and c.category == "pre_startup"),
        "pre_startup_checks_total": sum(1 for c in checks if c.category == "pre_startup"),
        "commissioning_checks_done": sum(1 for c in checks if c.is_done and c.category == "commissioning"),
        "commissioning_checks_total": sum(1 for c in checks if c.category == "commissioning"),
    }
