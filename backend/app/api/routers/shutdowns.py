import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.core.db import get_db
from app.core.errors import DomainError
from app.models.enums import PackageStatus, ReadinessStatus, ShutdownStatus
from app.models.shutdowns import (
    PackageDependency,
    Shutdown,
    ShutdownCheck,
    ShutdownPackage,
    ShutdownProgressLog,
)
from app.models.workorders import WorkOrder
from app.schemas.common import ORM, In
from app.services import shutdowns as svc
from app.services.common import audit, plant_today, utcnow
from app.services.notifications import notify_permission

router = APIRouter(prefix="/shutdowns", tags=["shutdowns"])


class ShutdownIn(In):
    code: str
    name: str
    scope: str | None = None
    department_id: uuid.UUID | None = None
    planned_start: datetime
    planned_end: datetime
    budget: float | None = Field(None, ge=0)


class ShutdownUpdate(In):
    name: str | None = None
    scope: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    status: ShutdownStatus | None = None
    completion_report: str | None = None
    lessons_learned: str | None = None


class ShutdownOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    scope: str | None
    department_id: uuid.UUID | None
    planned_start: datetime
    planned_end: datetime
    actual_start: datetime | None
    actual_end: datetime | None
    status: ShutdownStatus
    budget: float | None
    completion_report: str | None
    lessons_learned: str | None


def _sd(db: Session, ctx: Ctx, sid: uuid.UUID) -> Shutdown:
    s = db.get(Shutdown, sid)
    if s is None or s.plant_id != ctx.plant_id:
        raise HTTPException(404, "Shutdown not found")
    return s


def _pkg(db: Session, sd: Shutdown, pid: uuid.UUID) -> ShutdownPackage:
    p = db.get(ShutdownPackage, pid)
    if p is None or p.shutdown_id != sd.id:
        raise HTTPException(404, "Package not found")
    return p


@router.get("", response_model=list[ShutdownOut])
def list_sd(ctx: Ctx = Depends(require("shutdown.view")), db: Session = Depends(get_db)) -> list[Shutdown]:
    return list(db.execute(select(Shutdown).where(Shutdown.plant_id == ctx.plant_id).order_by(Shutdown.planned_start.desc())).scalars())


@router.post("", response_model=ShutdownOut, status_code=201)
def create_sd(body: ShutdownIn, ctx: Ctx = Depends(require("shutdown.manage")), db: Session = Depends(get_db)) -> Shutdown:
    if body.planned_end <= body.planned_start:
        raise HTTPException(422, "planned_end must be after planned_start")
    s = Shutdown(plant_id=ctx.plant_id, **body.model_dump())
    db.add(s)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Shutdown code exists") from e
    return s


@router.patch("/{sid}", response_model=ShutdownOut)
def update_sd(
    sid: uuid.UUID, body: ShutdownUpdate, ctx: Ctx = Depends(require("shutdown.manage")), db: Session = Depends(get_db)
) -> Shutdown:
    s = _sd(db, ctx, sid)
    data = body.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    for k, v in data.items():
        setattr(s, k, v)
    if new_status and new_status != s.status:
        if new_status == ShutdownStatus.IN_PROGRESS:
            s.actual_start = s.actual_start or utcnow()
        if new_status == ShutdownStatus.COMPLETED:
            r = svc.readiness(db, s)
            if r["pre_startup_checks_total"] and r["pre_startup_checks_done"] < r["pre_startup_checks_total"]:
                raise DomainError("All pre-startup inspections must be completed before closing the shutdown", "checks_pending", 409)
            s.actual_end = utcnow()
        s.status = new_status
        notify_permission(
            db,
            ctx.plant_id,
            "shutdown.view",
            kind="shutdown",
            title=f"Shutdown {s.code}: {new_status.value}",
            link=f"/shutdowns/{s.id}",
            dedupe_key=f"sd:{s.id}:{new_status.value}",
        )
    if s.planned_end <= s.planned_start:
        raise HTTPException(422, "planned_end must be after planned_start")
    svc.compute_cpm(db, s)
    audit(
        db,
        "shutdown.update",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="shutdown",
        entity_id=s.id,
        data=body.model_dump(exclude_unset=True),
    )
    return s


class PackageIn(In):
    code: str
    name: str
    asset_id: uuid.UUID | None = None
    contractor_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    duration_hours: float = Field(gt=0)
    planned_manpower: int = Field(1, ge=0)
    contractor_manpower: int = Field(0, ge=0)
    material_status: ReadinessStatus = ReadinessStatus.NOT_READY
    permit_status: ReadinessStatus = ReadinessStatus.NOT_READY
    loto_status: ReadinessStatus = ReadinessStatus.NOT_READY
    predecessor_ids: list[uuid.UUID] = Field(default_factory=list)


class PackageUpdate(In):
    name: str | None = None
    duration_hours: float | None = Field(None, gt=0)
    planned_manpower: int | None = Field(None, ge=0)
    contractor_manpower: int | None = Field(None, ge=0)
    material_status: ReadinessStatus | None = None
    permit_status: ReadinessStatus | None = None
    loto_status: ReadinessStatus | None = None
    procurement_note: str | None = None
    status: PackageStatus | None = None
    delay_reason: str | None = None


@router.get("/{sid}")
def detail(sid: uuid.UUID, ctx: Ctx = Depends(require("shutdown.view")), db: Session = Depends(get_db)) -> dict:
    s = _sd(db, ctx, sid)
    cpm = svc.compute_cpm(db, s)
    pkgs = (
        db.execute(
            select(ShutdownPackage).where(ShutdownPackage.shutdown_id == s.id).order_by(ShutdownPackage.planned_start, ShutdownPackage.code)
        )
        .scalars()
        .all()
    )
    deps = (
        db.execute(select(PackageDependency).where(PackageDependency.package_id.in_([p.id for p in pkgs]))).scalars().all() if pkgs else []
    )
    wos = db.execute(select(WorkOrder).where(WorkOrder.shutdown_package_id.in_([p.id for p in pkgs]))).scalars().all() if pkgs else []
    checks = db.execute(select(ShutdownCheck).where(ShutdownCheck.shutdown_id == s.id)).scalars().all()
    return {
        "shutdown": ShutdownOut.model_validate(s).model_dump(mode="json"),
        "cpm": cpm,
        "readiness": svc.readiness(db, s),
        "packages": [
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "duration_hours": float(p.duration_hours),
                "planned_start": p.planned_start,
                "planned_finish": p.planned_finish,
                "actual_start": p.actual_start,
                "actual_finish": p.actual_finish,
                "progress_pct": float(p.progress_pct),
                "status": p.status,
                "is_critical": p.is_critical,
                "total_float_hours": float(p.total_float_hours or 0),
                "material_status": p.material_status,
                "permit_status": p.permit_status,
                "loto_status": p.loto_status,
                "planned_manpower": p.planned_manpower,
                "contractor_manpower": p.contractor_manpower,
                "delay_reason": p.delay_reason,
                "asset_id": p.asset_id,
                "predecessors": [d.predecessor_id for d in deps if d.package_id == p.id],
                "work_orders": [{"id": w.id, "number": w.number, "status": w.status} for w in wos if w.shutdown_package_id == p.id],
            }
            for p in pkgs
        ],
        "checks": [
            {
                "id": c.id,
                "category": c.category,
                "description": c.description,
                "is_done": c.is_done,
                "result": c.result,
                "done_at": c.done_at,
            }
            for c in checks
        ],
    }


@router.post("/{sid}/packages", status_code=201)
def add_package(sid: uuid.UUID, body: PackageIn, ctx: Ctx = Depends(require("shutdown.manage")), db: Session = Depends(get_db)) -> dict:
    s = _sd(db, ctx, sid)
    p = ShutdownPackage(plant_id=ctx.plant_id, shutdown_id=s.id, **body.model_dump(exclude={"predecessor_ids"}))
    db.add(p)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Package code exists in this shutdown") from e
    for pred in body.predecessor_ids:
        svc.add_dependency(db, s, p, _pkg(db, s, pred), 0)
    svc.compute_cpm(db, s)
    return {"id": p.id}


class DepIn(In):
    predecessor_id: uuid.UUID
    lag_hours: float = Field(0, ge=0)


@router.post("/{sid}/packages/{pid}/dependencies", status_code=201)
def add_dep(
    sid: uuid.UUID, pid: uuid.UUID, body: DepIn, ctx: Ctx = Depends(require("shutdown.manage")), db: Session = Depends(get_db)
) -> dict:
    s = _sd(db, ctx, sid)
    try:
        svc.add_dependency(db, s, _pkg(db, s, pid), _pkg(db, s, body.predecessor_id), body.lag_hours)
    except IntegrityError as e:
        raise HTTPException(409, "Dependency exists") from e
    return svc.compute_cpm(db, s)


@router.patch("/{sid}/packages/{pid}")
def update_package(
    sid: uuid.UUID, pid: uuid.UUID, body: PackageUpdate, ctx: Ctx = Depends(require("shutdown.manage")), db: Session = Depends(get_db)
) -> dict:
    s = _sd(db, ctx, sid)
    p = _pkg(db, s, pid)
    data = body.model_dump(exclude_unset=True)
    if data.get("status") == PackageStatus.DELAYED and not (data.get("delay_reason") or p.delay_reason):
        raise HTTPException(422, "A delay reason is required")
    for k, v in data.items():
        setattr(p, k, v)
    if p.status == PackageStatus.IN_PROGRESS and p.actual_start is None:
        p.actual_start = utcnow()
    if p.status == PackageStatus.COMPLETED:
        p.progress_pct, p.actual_finish = 100, p.actual_finish or utcnow()
    svc.compute_cpm(db, s)
    return {"ok": True}


class ProgressIn(In):
    progress_pct: float = Field(ge=0, le=100)
    note: str | None = None
    delay_reason: str | None = None
    log_date: date | None = None


@router.post("/{sid}/packages/{pid}/progress", status_code=201)
def progress(
    sid: uuid.UUID, pid: uuid.UUID, body: ProgressIn, ctx: Ctx = Depends(require("shutdown.manage")), db: Session = Depends(get_db)
) -> dict:
    s = _sd(db, ctx, sid)
    p = _pkg(db, s, pid)
    db.add(
        ShutdownProgressLog(
            package_id=p.id,
            log_date=body.log_date or plant_today(ctx.plant),
            progress_pct=body.progress_pct,
            note=body.note,
            delay_reason=body.delay_reason,
            recorded_by_id=ctx.user.id,
            created_at=utcnow(),
        )
    )
    p.progress_pct = body.progress_pct
    if body.delay_reason:
        p.status, p.delay_reason = PackageStatus.DELAYED, body.delay_reason
    elif body.progress_pct >= 100:
        p.status, p.actual_finish = PackageStatus.COMPLETED, p.actual_finish or utcnow()
    elif body.progress_pct > 0:
        p.status = PackageStatus.IN_PROGRESS
        p.actual_start = p.actual_start or utcnow()
    return {"status": p.status}


@router.get("/{sid}/packages/{pid}/progress")
def progress_log(sid: uuid.UUID, pid: uuid.UUID, ctx: Ctx = Depends(require("shutdown.view")), db: Session = Depends(get_db)) -> list[dict]:
    s = _sd(db, ctx, sid)
    p = _pkg(db, s, pid)
    return [
        {"date": r.log_date, "progress_pct": float(r.progress_pct), "note": r.note, "delay_reason": r.delay_reason}
        for r in db.execute(
            select(ShutdownProgressLog).where(ShutdownProgressLog.package_id == p.id).order_by(ShutdownProgressLog.log_date)
        ).scalars()
    ]


class CheckIn(In):
    category: str = Field(pattern="^(pre_startup|commissioning)$")
    description: str


@router.post("/{sid}/checks", status_code=201)
def add_check(sid: uuid.UUID, body: CheckIn, ctx: Ctx = Depends(require("shutdown.manage")), db: Session = Depends(get_db)) -> dict:
    s = _sd(db, ctx, sid)
    c = ShutdownCheck(shutdown_id=s.id, **body.model_dump())
    db.add(c)
    db.flush()
    return {"id": c.id}


class CheckDone(In):
    result: str = Field(min_length=2)


@router.post("/{sid}/checks/{cid}/complete")
def complete_check(
    sid: uuid.UUID, cid: uuid.UUID, body: CheckDone, ctx: Ctx = Depends(require("shutdown.manage")), db: Session = Depends(get_db)
) -> dict:
    s = _sd(db, ctx, sid)
    c = db.get(ShutdownCheck, cid)
    if c is None or c.shutdown_id != s.id:
        raise HTTPException(404, "Check not found")
    c.is_done, c.result, c.done_by_id, c.done_at = True, body.result, ctx.user.id, utcnow()
    audit(db, "shutdown.check", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="shutdown_check", entity_id=c.id)
    return {"ok": True}
