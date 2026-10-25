import io
import uuid
from datetime import date, datetime

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.api.pagination import PageQ, paginate
from app.core.db import get_db
from app.models.assets import Asset, AssetBOM, AssetStatusHistory, DowntimeEvent, Meter, MeterReading
from app.models.enums import AssetLevel, AssetStatus, Criticality
from app.models.inventory import Part
from app.models.workorders import WorkOrder
from app.schemas.common import ORM, In
from app.services import assets as svc
from app.services.common import audit, utcnow

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetIn(In):
    code: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9._\-/]+$")
    name: str = Field(min_length=1, max_length=200)
    name_ar: str | None = None
    department_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    level: AssetLevel
    description: str | None = None
    oem: str | None = None
    model: str | None = None
    serial_number: str | None = None
    install_date: date | None = None
    criticality: Criticality = Criticality.C
    location: str | None = None
    specifications: dict = Field(default_factory=dict)
    operating_limits: dict = Field(default_factory=dict)


class AssetUpdate(In):
    name: str | None = None
    name_ar: str | None = None
    parent_id: uuid.UUID | None = None
    description: str | None = None
    oem: str | None = None
    model: str | None = None
    serial_number: str | None = None
    install_date: date | None = None
    criticality: Criticality | None = None
    location: str | None = None
    specifications: dict | None = None
    operating_limits: dict | None = None
    status: AssetStatus | None = None
    status_note: str | None = None


class AssetOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    name_ar: str | None
    department_id: uuid.UUID
    parent_id: uuid.UUID | None
    level: AssetLevel
    path: str
    description: str | None
    oem: str | None
    model: str | None
    serial_number: str | None
    install_date: date | None
    criticality: Criticality
    status: AssetStatus
    location: str | None
    specifications: dict
    operating_limits: dict
    operating_hours: float
    qr_token: str
    is_active: bool
    created_at: datetime


class AssetNode(ORM):
    id: uuid.UUID
    code: str
    name: str
    level: AssetLevel
    parent_id: uuid.UUID | None
    department_id: uuid.UUID
    criticality: Criticality
    status: AssetStatus
    child_count: int = 0


def _get(db: Session, ctx: Ctx, asset_id: uuid.UUID) -> Asset:
    a = db.get(Asset, asset_id)
    if a is None or a.plant_id != ctx.plant_id:
        raise HTTPException(404, "Asset not found")
    return a


def _dept_filter(ctx: Ctx, q):  # type: ignore[no-untyped-def]
    return q.where(Asset.department_id == ctx.department_id) if ctx.department_id else q


@router.get("", response_model=dict)
def list_assets(
    ctx: Ctx = Depends(require("asset.view")),
    db: Session = Depends(get_db),
    page: PageQ = Depends(),
    q: str | None = None,
    department_id: uuid.UUID | None = None,
    level: AssetLevel | None = None,
    criticality: Criticality | None = None,
    status: AssetStatus | None = None,
    under: uuid.UUID | None = None,
) -> dict:
    stmt = _dept_filter(ctx, select(Asset).where(Asset.plant_id == ctx.plant_id))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Asset.code.ilike(like), Asset.name.ilike(like), Asset.serial_number.ilike(like)))
    if department_id:
        stmt = stmt.where(Asset.department_id == department_id)
    if level:
        stmt = stmt.where(Asset.level == level)
    if criticality:
        stmt = stmt.where(Asset.criticality == criticality)
    if status:
        stmt = stmt.where(Asset.status == status)
    if under:
        root = _get(db, ctx, under)
        stmt = stmt.where(Asset.path.startswith(root.path), Asset.id != root.id)
    return paginate(db, stmt.order_by(Asset.code), page, AssetOut)


@router.get("/tree", response_model=list[AssetNode])
def tree_children(
    ctx: Ctx = Depends(require("asset.view")),
    db: Session = Depends(get_db),
    department_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
) -> list[dict]:
    """Lazy-loaded tree: children of a parent (or top-level lines of a department)."""
    child = select(func.count()).where(Asset.parent_id == Asset.id).correlate(Asset).scalar_subquery()
    from sqlalchemy.orm import aliased

    c = aliased(Asset)
    cnt = select(func.count(c.id)).where(c.parent_id == Asset.id).scalar_subquery()
    del child
    stmt = _dept_filter(ctx, select(Asset, cnt.label("cc")).where(Asset.plant_id == ctx.plant_id))
    stmt = stmt.where(Asset.parent_id == parent_id) if parent_id else stmt.where(Asset.parent_id.is_(None))
    if department_id:
        stmt = stmt.where(Asset.department_id == department_id)
    out = []
    for a, cc in db.execute(stmt.order_by(Asset.code)).all():
        node = AssetNode.model_validate(a)
        node.child_count = cc
        out.append(node.model_dump())
    return out


@router.post("", response_model=AssetOut, status_code=201)
def create_asset(body: AssetIn, ctx: Ctx = Depends(require("asset.edit")), db: Session = Depends(get_db)) -> Asset:
    if ctx.department_id and body.department_id != ctx.department_id:
        raise HTTPException(403, "Your access is limited to your department")
    parent = svc.validate_parent(db, ctx.plant_id, body.level, body.parent_id, body.department_id)
    a = Asset(id=uuid.uuid4(), plant_id=ctx.plant_id, qr_token=svc.new_qr_token(), created_by_id=ctx.user.id, **body.model_dump())
    a.path = svc.compute_path(parent, a.id)
    db.add(a)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, f"Asset code {body.code} already exists in this plant") from e
    audit(
        db,
        "asset.create",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="asset",
        entity_id=a.id,
        data={"code": a.code, "level": a.level},
    )
    return a


@router.get("/by-qr/{token}", response_model=AssetOut)
def by_qr(token: str, ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db)) -> Asset:
    a = db.execute(select(Asset).where(Asset.qr_token == token, Asset.plant_id == ctx.plant_id)).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Asset not found")
    return a


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: uuid.UUID, ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db)) -> Asset:
    return _get(db, ctx, asset_id)


@router.get("/{asset_id}/ancestors", response_model=list[AssetNode])
def ancestors(asset_id: uuid.UUID, ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db)) -> list[Asset]:
    a = _get(db, ctx, asset_id)
    ids = [uuid.UUID(x) for x in a.path.strip("/").split("/") if x]
    rows = {r.id: r for r in db.execute(select(Asset).where(Asset.id.in_(ids), Asset.plant_id == ctx.plant_id)).scalars()}
    return [rows[i] for i in ids if i in rows]


@router.patch("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: uuid.UUID, body: AssetUpdate, ctx: Ctx = Depends(require("asset.edit")), db: Session = Depends(get_db)) -> Asset:
    a = _get(db, ctx, asset_id)
    data = body.model_dump(exclude_unset=True)
    if "parent_id" in data:
        svc.move_asset(db, a, data.pop("parent_id"))
    if "status" in data:
        svc.change_status(db, a, data.pop("status"), ctx.user.id, data.pop("status_note", None))
    data.pop("status_note", None)
    for k, v in data.items():
        setattr(a, k, v)
    audit(
        db,
        "asset.update",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="asset",
        entity_id=a.id,
        data=body.model_dump(exclude_unset=True),
    )
    return a


@router.get("/{asset_id}/qr.png")
def asset_qr(asset_id: uuid.UUID, ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db)) -> StreamingResponse:
    a = _get(db, ctx, asset_id)
    img = qrcode.make(f"cmms:asset:{a.qr_token}")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.get("/{asset_id}/history")
def asset_history(
    asset_id: uuid.UUID, ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db), include_children: bool = True
) -> dict:
    a = _get(db, ctx, asset_id)
    ids = svc.subtree_ids(db, a) if include_children else [a.id]
    wos = (
        db.execute(
            select(WorkOrder)
            .where(WorkOrder.plant_id == ctx.plant_id, WorkOrder.asset_id.in_(ids))
            .order_by(WorkOrder.created_at.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )
    downtime = (
        db.execute(select(DowntimeEvent).where(DowntimeEvent.asset_id.in_(ids)).order_by(DowntimeEvent.started_at.desc()).limit(200))
        .scalars()
        .all()
    )
    statuses = (
        db.execute(select(AssetStatusHistory).where(AssetStatusHistory.asset_id == a.id).order_by(AssetStatusHistory.changed_at.desc()))
        .scalars()
        .all()
    )
    total_cost = sum(w.actual_cost for w in wos)
    return {
        "work_orders": [
            {
                "id": w.id,
                "number": w.number,
                "type": w.type,
                "status": w.status,
                "title": w.title,
                "created_at": w.created_at,
                "completed_at": w.completed_at,
                "actual_cost": w.actual_cost,
                "asset_id": w.asset_id,
            }
            for w in wos
        ],
        "downtime": [
            {
                "id": d.id,
                "started_at": d.started_at,
                "ended_at": d.ended_at,
                "is_failure": d.is_failure,
                "reason": d.reason,
                "work_order_id": d.work_order_id,
            }
            for d in downtime
        ],
        "status_history": [{"from": s.from_status, "to": s.to_status, "at": s.changed_at, "note": s.note} for s in statuses],
        "total_cost": round(total_cost, 2),
    }


@router.get("/{asset_id}/reliability")
def asset_reliability(
    asset_id: uuid.UUID,
    ctx: Ctx = Depends(require("asset.view")),
    db: Session = Depends(get_db),
    start: date | None = None,
    end: date | None = None,
) -> dict:
    from app.services.kpi import asset_reliability as rel

    a = _get(db, ctx, asset_id)
    return rel(db, ctx.plant, a, start, end)


# ---------- BOM ----------
class BOMIn(In):
    part_id: uuid.UUID
    quantity: float = Field(gt=0)
    position: str | None = None
    notes: str | None = None


@router.get("/{asset_id}/bom")
def get_bom(asset_id: uuid.UUID, ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db)) -> list[dict]:
    _get(db, ctx, asset_id)
    rows = db.execute(select(AssetBOM, Part).join(Part, Part.id == AssetBOM.part_id).where(AssetBOM.asset_id == asset_id)).all()
    return [
        {
            "id": b.id,
            "part_id": p.id,
            "part_code": p.code,
            "description": p.description,
            "quantity": float(b.quantity),
            "position": b.position,
            "is_critical_spare": p.is_critical_spare,
        }
        for b, p in rows
    ]


@router.post("/{asset_id}/bom", status_code=201)
def add_bom(asset_id: uuid.UUID, body: BOMIn, ctx: Ctx = Depends(require("asset.edit")), db: Session = Depends(get_db)) -> dict:
    _get(db, ctx, asset_id)
    p = db.get(Part, body.part_id)
    if p is None or p.plant_id != ctx.plant_id:
        raise HTTPException(422, "Part not found in this plant")
    b = AssetBOM(asset_id=asset_id, **body.model_dump())
    db.add(b)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Part already in BOM") from e
    return {"id": b.id}


@router.delete("/{asset_id}/bom/{bom_id}", status_code=204)
def del_bom(asset_id: uuid.UUID, bom_id: uuid.UUID, ctx: Ctx = Depends(require("asset.edit")), db: Session = Depends(get_db)) -> None:
    _get(db, ctx, asset_id)
    b = db.get(AssetBOM, bom_id)
    if b is None or b.asset_id != asset_id:
        raise HTTPException(404, "BOM line not found")
    db.delete(b)


# ---------- meters ----------
class MeterIn(In):
    name: str
    unit: str = "h"
    is_operating_hours: bool = True
    current_value: float = Field(0, ge=0)


class MeterReadingIn(In):
    value: float = Field(ge=0)
    read_at: datetime | None = None


class MeterOut(ORM):
    id: uuid.UUID
    asset_id: uuid.UUID
    name: str
    unit: str
    is_operating_hours: bool
    current_value: float
    last_read_at: datetime | None


@router.get("/{asset_id}/meters", response_model=list[MeterOut])
def list_meters(asset_id: uuid.UUID, ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db)) -> list[Meter]:
    _get(db, ctx, asset_id)
    return list(db.execute(select(Meter).where(Meter.asset_id == asset_id)).scalars())


@router.post("/{asset_id}/meters", response_model=MeterOut, status_code=201)
def create_meter(asset_id: uuid.UUID, body: MeterIn, ctx: Ctx = Depends(require("asset.edit")), db: Session = Depends(get_db)) -> Meter:
    _get(db, ctx, asset_id)
    m = Meter(plant_id=ctx.plant_id, asset_id=asset_id, **body.model_dump())
    db.add(m)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Meter name exists for this asset") from e
    return m


@router.post("/meters/{meter_id}/readings", response_model=MeterOut)
def add_meter_reading(
    meter_id: uuid.UUID, body: MeterReadingIn, ctx: Ctx = Depends(require("pdm.record")), db: Session = Depends(get_db)
) -> Meter:
    from app.services.pm import record_meter_reading

    m = db.get(Meter, meter_id)
    if m is None or m.plant_id != ctx.plant_id:
        raise HTTPException(404, "Meter not found")
    record_meter_reading(db, ctx.plant, m, body.value, body.read_at or utcnow(), ctx.user.id)
    return m


@router.get("/meters/{meter_id}/readings")
def meter_readings(
    meter_id: uuid.UUID, ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db), limit: int = Query(200, le=2000)
) -> list[dict]:
    m = db.get(Meter, meter_id)
    if m is None or m.plant_id != ctx.plant_id:
        raise HTTPException(404, "Meter not found")
    rows = db.execute(
        select(MeterReading).where(MeterReading.meter_id == meter_id).order_by(MeterReading.read_at.desc()).limit(limit)
    ).scalars()
    return [{"value": float(r.value), "read_at": r.read_at, "source": r.source} for r in rows]


# ---------- downtime ----------
class DowntimeIn(In):
    started_at: datetime
    ended_at: datetime | None = None
    is_failure: bool = True
    is_planned: bool = False
    production_loss_tons: float | None = Field(None, ge=0)
    reason: str | None = None
    work_order_id: uuid.UUID | None = None


@router.post("/{asset_id}/downtime", status_code=201)
def add_downtime(asset_id: uuid.UUID, body: DowntimeIn, ctx: Ctx = Depends(require("wo.execute")), db: Session = Depends(get_db)) -> dict:
    _get(db, ctx, asset_id)
    if body.ended_at and body.ended_at < body.started_at:
        raise HTTPException(422, "ended_at must be after started_at")
    if body.work_order_id:
        w = db.get(WorkOrder, body.work_order_id)
        if w is None or w.plant_id != ctx.plant_id:
            raise HTTPException(422, "Work order not found")
    d = DowntimeEvent(plant_id=ctx.plant_id, asset_id=asset_id, created_by_id=ctx.user.id, **body.model_dump())
    db.add(d)
    db.flush()
    audit(db, "downtime.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="downtime", entity_id=d.id)
    return {"id": d.id}


class DowntimeClose(In):
    ended_at: datetime


@router.post("/downtime/{downtime_id}/close")
def close_downtime(
    downtime_id: uuid.UUID, body: DowntimeClose, ctx: Ctx = Depends(require("wo.execute")), db: Session = Depends(get_db)
) -> dict:
    d = db.get(DowntimeEvent, downtime_id)
    if d is None or d.plant_id != ctx.plant_id:
        raise HTTPException(404, "Downtime event not found")
    if body.ended_at < d.started_at:
        raise HTTPException(422, "ended_at must be after started_at")
    d.ended_at = body.ended_at
    return {"id": d.id, "ended_at": d.ended_at}
