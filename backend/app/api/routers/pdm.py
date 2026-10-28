import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import case, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.api.pagination import PageQ, paginate
from app.core.db import get_db
from app.core.security import hash_token
from app.models.assets import Asset
from app.models.enums import AlertStatus, ConditionStatus, Priority, Technique
from app.models.pdm import ConditionAlert, ConditionReading, MeasurementPoint
from app.models.tenancy import IntegrationToken, Plant
from app.schemas.common import ORM, In
from app.services import pdm as svc
from app.services import pdm_history, pdm_priority
from app.services.common import audit, utcnow

router = APIRouter(prefix="/pdm", tags=["condition monitoring"])


class PointIn(In):
    code: str = ""  # blank: <asset code>-CM01, -CM02 ...
    name: str = ""  # blank: <asset name> – <technique>
    asset_id: uuid.UUID
    technique: Technique
    unit: str
    baseline: float | None = None
    warning_low: float | None = None
    warning_high: float | None = None
    alarm_low: float | None = None
    alarm_high: float | None = None
    stale_after_hours: int | None = Field(None, ge=1)
    auto_create_wo: bool = False
    wo_priority_on_critical: Priority = Priority.P2_HIGH
    recommended_action: str | None = None
    external_tag: str | None = None
    priority: int = Field(3, ge=1, le=3)


class PointUpdate(In):
    name: str | None = None
    baseline: float | None = None
    warning_low: float | None = None
    warning_high: float | None = None
    alarm_low: float | None = None
    alarm_high: float | None = None
    stale_after_hours: int | None = None
    auto_create_wo: bool | None = None
    recommended_action: str | None = None
    external_tag: str | None = None
    is_active: bool | None = None


class PointOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    asset_id: uuid.UUID
    technique: Technique
    unit: str
    baseline: float | None
    warning_low: float | None
    warning_high: float | None
    alarm_low: float | None
    alarm_high: float | None
    stale_after_hours: int | None
    auto_create_wo: bool
    recommended_action: str | None
    external_tag: str | None
    last_status: ConditionStatus
    last_value: float | None
    last_reading_at: datetime | None
    is_active: bool
    priority: int


def _point(db: Session, ctx: Ctx, pid: uuid.UUID) -> MeasurementPoint:
    p = db.get(MeasurementPoint, pid)
    if p is None or p.plant_id != ctx.plant_id:
        raise HTTPException(404, "Measurement point not found")
    ctx.check_asset(db, p.asset_id, "Measurement point not found")
    return p


@router.get("/points", response_model=list[PointOut])
def list_points(
    ctx: Ctx = Depends(require("pdm.view")),
    db: Session = Depends(get_db, scope="function"),
    asset_id: uuid.UUID | None = None,
    status: ConditionStatus | None = None,
    q: str | None = None,
    under: uuid.UUID | None = None,
) -> list[MeasurementPoint]:
    """`q` searches point code/name and the asset's code/name; `under` keeps the points on an asset and everything below it."""
    stmt = select(MeasurementPoint).where(MeasurementPoint.plant_id == ctx.plant_id, ctx.in_department(MeasurementPoint.asset_id))
    if asset_id:
        stmt = stmt.where(MeasurementPoint.asset_id == asset_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.join(Asset, Asset.id == MeasurementPoint.asset_id).where(
            or_(MeasurementPoint.code.ilike(like), MeasurementPoint.name.ilike(like), Asset.code.ilike(like), Asset.name.ilike(like))
        )
    if under:
        root = db.get(Asset, under)
        if root is None or root.plant_id != ctx.plant_id:
            raise HTTPException(422, "Asset not found")
        stmt = stmt.where(MeasurementPoint.asset_id.in_(select(Asset.id).where(Asset.path.startswith(root.path))))
    if status:
        stmt = stmt.where(MeasurementPoint.last_status == status)
    # Critical items first, so a technician does not have to search: set priority, then the worst reading status.
    status_rank = case(
        (MeasurementPoint.last_status == ConditionStatus.CRITICAL, 0),
        (MeasurementPoint.last_status == ConditionStatus.WARNING, 1),
        (MeasurementPoint.last_status == ConditionStatus.UNKNOWN, 2),
        else_=3,
    )
    return list(db.execute(stmt.order_by(MeasurementPoint.priority, status_rank, MeasurementPoint.code).limit(2000)).scalars())


@router.post("/points", response_model=PointOut, status_code=201)
def create_point(
    body: PointIn, ctx: Ctx = Depends(require("pdm.manage")), db: Session = Depends(get_db, scope="function")
) -> MeasurementPoint:
    a = db.get(Asset, body.asset_id)
    if a is None or a.plant_id != ctx.plant_id:
        raise HTTPException(422, "Asset not found")
    ctx.check_asset(db, a.id, code=403)
    data = body.model_dump()
    data["code"] = data["code"].strip() or svc.next_point_code(db, ctx.plant_id, a.code)
    data["name"] = data["name"].strip() or f"{a.name} – {body.technique.value.replace('_', ' ')}"[:200]
    p = MeasurementPoint(plant_id=ctx.plant_id, **data)
    svc.validate_limits(p)
    db.add(p)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Point code exists") from e
    return p


@router.patch("/points/{pid}", response_model=PointOut)
def update_point(
    pid: uuid.UUID, body: PointUpdate, ctx: Ctx = Depends(require("pdm.manage")), db: Session = Depends(get_db, scope="function")
) -> MeasurementPoint:
    p = _point(db, ctx, pid)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    svc.validate_limits(p)
    audit(db, "pdm.point_update", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="measurement_point", entity_id=p.id, data=data)
    return p


@router.get("/points/priority.xlsx")
def priority_export(ctx: Ctx = Depends(require("pdm.prioritize")), db: Session = Depends(get_db, scope="function")) -> Response:
    """Every point with its priority; set the priority column and upload the file back."""
    pts = list_points(ctx, db)
    return Response(
        pdm_priority.export_xlsx(db, ctx.plant, pts),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="measurement_point_priorities.xlsx"'},
    )


@router.post("/points/priority/import")
def priority_import(
    apply: bool = False,
    file: UploadFile = File(...),
    ctx: Ctx = Depends(require("pdm.prioritize")),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    """apply=false: preview only. apply=true: save all changes, or nothing if any row has an error."""
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5 MB)")
    try:
        checked = pdm_priority.check(db, ctx.plant, file.filename or "", content, ctx.in_department(MeasurementPoint.asset_id))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if not apply:
        return checked["preview"]
    try:
        return {**checked["preview"], **pdm_priority.apply(db, ctx.plant, checked, ctx.user.id)}
    except ValueError as e:
        raise HTTPException(422, {"message": str(e), **checked["preview"]}) from e


@router.get("/readings/template.xlsx")
def history_template(ctx: Ctx = Depends(require("pdm.manage")), db: Session = Depends(get_db, scope="function")) -> Response:
    """Layout for importing past readings, with every point code listed in a second sheet."""
    return Response(
        pdm_history.template_xlsx(db, ctx.plant, list_points(ctx, db)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="condition_readings_import.xlsx"'},
    )


@router.post("/readings/import")
def history_import(
    apply: bool = False,
    file: UploadFile = File(...),
    ctx: Ctx = Depends(require("pdm.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    """Past readings (point_code, date, time, value, note). apply=false: preview; apply=true: import, or nothing if any row is wrong."""
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB)")
    try:
        checked = pdm_history.check(db, ctx.plant, file.filename or "", content, ctx.in_department(MeasurementPoint.asset_id))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if not apply:
        return checked["preview"]
    try:
        return {**checked["preview"], **pdm_history.commit(db, ctx.plant, checked, ctx.user.id)}
    except ValueError as e:
        raise HTTPException(422, {"message": str(e), **checked["preview"]}) from e


class PriorityIn(In):
    priority: int = Field(ge=1, le=3)  # 1 critical, 2 high, 3 normal


@router.put("/points/{pid}/priority", response_model=PointOut)
def set_priority(
    pid: uuid.UUID, body: PriorityIn, ctx: Ctx = Depends(require("pdm.prioritize")), db: Session = Depends(get_db, scope="function")
) -> MeasurementPoint:
    p = _point(db, ctx, pid)
    old, p.priority = p.priority, body.priority
    audit(
        db,
        "pdm.point_priority",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="measurement_point",
        entity_id=p.id,
        data={"from": old, "to": body.priority},
    )
    return p


class ReadingIn(In):
    value: float
    measured_at: datetime | None = None
    note: str | None = None


@router.post("/points/{pid}/readings", status_code=201)
def add_reading(
    pid: uuid.UUID, body: ReadingIn, ctx: Ctx = Depends(require("pdm.record")), db: Session = Depends(get_db, scope="function")
) -> dict:
    p = _point(db, ctx, pid)
    return svc.record_reading(db, ctx.plant, p, body.value, body.measured_at or utcnow(), ctx.user.id, "manual", body.note)


@router.get("/points/{pid}/readings")
def readings(
    pid: uuid.UUID,
    ctx: Ctx = Depends(require("pdm.view")),
    db: Session = Depends(get_db, scope="function"),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
) -> dict:
    p = _point(db, ctx, pid)
    q = select(ConditionReading).where(ConditionReading.point_id == p.id)
    if start:
        q = q.where(ConditionReading.measured_at >= start)
    if end:
        q = q.where(ConditionReading.measured_at <= end)
    rows = db.execute(q.order_by(ConditionReading.measured_at.desc()).limit(min(limit, 10000))).scalars().all()
    return {
        "point": PointOut.model_validate(p).model_dump(mode="json"),
        "readings": [
            {"value": float(r.value), "measured_at": r.measured_at, "status": r.status, "source": r.source} for r in reversed(rows)
        ],
    }


class AlertOut(ORM):
    id: uuid.UUID
    point_id: uuid.UUID
    asset_id: uuid.UUID
    severity: ConditionStatus
    status: AlertStatus
    message: str
    defect_description: str | None
    recommended_action: str | None
    resolution: str | None
    work_order_id: uuid.UUID | None
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


@router.get("/alerts")
def alerts(
    ctx: Ctx = Depends(require("pdm.view")),
    db: Session = Depends(get_db, scope="function"),
    page: PageQ = Depends(),
    status: AlertStatus | None = None,
    severity: ConditionStatus | None = None,
    open_only: bool = False,
) -> dict:
    q = select(ConditionAlert).where(ConditionAlert.plant_id == ctx.plant_id, ctx.in_department(ConditionAlert.asset_id))
    if status:
        q = q.where(ConditionAlert.status == status)
    if severity:
        q = q.where(ConditionAlert.severity == severity)
    if open_only:
        q = q.where(ConditionAlert.status != AlertStatus.RESOLVED)
    return paginate(db, q.order_by(ConditionAlert.created_at.desc()), page, AlertOut)


def _alert(db: Session, ctx: Ctx, aid: uuid.UUID) -> ConditionAlert:
    a = db.execute(
        select(ConditionAlert).where(ConditionAlert.id == aid, ConditionAlert.plant_id == ctx.plant_id).with_for_update(key_share=True)
    ).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Alert not found")
    ctx.check_asset(db, a.asset_id, "Alert not found")
    return a


@router.get("/alerts/{aid}", response_model=AlertOut)
def get_alert(aid: uuid.UUID, ctx: Ctx = Depends(require("pdm.view")), db: Session = Depends(get_db, scope="function")) -> ConditionAlert:
    a = db.get(ConditionAlert, aid)
    if a is None or a.plant_id != ctx.plant_id:
        raise HTTPException(404, "Alert not found")
    ctx.check_asset(db, a.asset_id, "Alert not found")
    return a


class AckIn(In):
    defect_description: str | None = None
    recommended_action: str | None = None


@router.post("/alerts/{aid}/acknowledge", response_model=AlertOut)
def acknowledge(
    aid: uuid.UUID, body: AckIn, ctx: Ctx = Depends(require("pdm.alert_manage")), db: Session = Depends(get_db, scope="function")
) -> ConditionAlert:
    a = _alert(db, ctx, aid)
    if a.status == AlertStatus.RESOLVED:
        raise HTTPException(409, "Alert already resolved")
    if a.status == AlertStatus.OPEN:
        a.status = AlertStatus.ACKNOWLEDGED
    a.acknowledged_by_id, a.acknowledged_at = ctx.user.id, utcnow()
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    return a


@router.post("/alerts/{aid}/work-order")
def alert_wo(aid: uuid.UUID, ctx: Ctx = Depends(require("wo.create")), db: Session = Depends(get_db, scope="function")) -> dict:
    a = _alert(db, ctx, aid)
    wo = svc.create_wo_from_alert(db, ctx.plant, a, ctx.user.id)
    return {"work_order_id": wo.id, "number": wo.number}


class ResolveIn(In):
    resolution: str = Field(min_length=5)


@router.post("/alerts/{aid}/resolve", response_model=AlertOut)
def resolve(
    aid: uuid.UUID, body: ResolveIn, ctx: Ctx = Depends(require("pdm.alert_manage")), db: Session = Depends(get_db, scope="function")
) -> ConditionAlert:
    a = _alert(db, ctx, aid)
    a.status, a.resolution, a.resolved_by_id, a.resolved_at = AlertStatus.RESOLVED, body.resolution, ctx.user.id, utcnow()
    audit(db, "pdm.alert_resolved", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="condition_alert", entity_id=a.id)
    return a


# ---------------- read-only industrial gateway ingestion ----------------
gateway = APIRouter(prefix="/integrations", tags=["integrations"])


class GatewayReading(In):
    tag: str = Field(description="external_tag of the measurement point (OPC UA node id, MQTT topic, ...)")
    value: float
    measured_at: datetime


class GatewayBatch(In):
    readings: list[GatewayReading] = Field(min_length=1, max_length=1000)


@gateway.post("/readings")
def ingest(
    body: GatewayBatch, request: Request, db: Session = Depends(get_db, scope="function"), authorization: str | None = Header(default=None)
) -> dict:
    """Write-only ingestion for the industrial gateway (separate credential; no user session, no CSRF).
    The gateway pushes data in; the CMMS never sends commands to PLC/SCADA/DCS."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    tok = db.execute(select(IntegrationToken).where(IntegrationToken.token_hash == hash_token(authorization[7:]))).scalar_one_or_none()
    if tok is None or tok.revoked_at is not None or "readings:write" not in tok.scopes:
        raise HTTPException(401, "Invalid token")
    plant = db.get(Plant, tok.plant_id)
    assert plant is not None
    tok.last_used_at = utcnow()
    tags = {r.tag for r in body.readings}
    points = {
        p.external_tag: p
        for p in db.execute(
            select(MeasurementPoint).where(
                MeasurementPoint.plant_id == plant.id, MeasurementPoint.external_tag.in_(tags), MeasurementPoint.is_active.is_(True)
            )
        ).scalars()
    }
    accepted = dup = 0
    unknown: list[str] = []
    for r in body.readings:
        p = points.get(r.tag)
        if p is None:
            unknown.append(r.tag)
            continue
        res = svc.record_reading(db, plant, p, r.value, r.measured_at, None, "gateway")
        dup += res["duplicate"]
        accepted += not res["duplicate"]
    return {"accepted": accepted, "duplicates": dup, "unknown_tags": sorted(set(unknown))}
