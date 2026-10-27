import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.core.db import get_db
from app.models.assets import Asset
from app.models.enums import LubeTaskStatus
from app.models.lubrication import LubeRoute, LubeTask, Lubricant, LubricantAlternative, LubricationPoint
from app.models.tenancy import Department
from app.schemas.common import ORM, In
from app.services import labels
from app.services import lubrication as svc
from app.services.assets import new_qr_token
from app.services.common import audit, plant_today, utcnow

router = APIRouter(prefix="/lubrication", tags=["lubrication"])


class LubricantIn(In):
    code: str
    manufacturer: str
    product: str
    kind: str = Field(pattern="^(oil|grease)$")
    viscosity_grade: str | None = None
    specification: str | None = None
    part_id: uuid.UUID | None = None


class LubricantOut(ORM):
    id: uuid.UUID
    code: str
    manufacturer: str
    product: str
    kind: str
    viscosity_grade: str | None
    specification: str | None
    part_id: uuid.UUID | None
    is_approved: bool


@router.get("/lubricants", response_model=list[LubricantOut])
def list_lubricants(ctx: Ctx = Depends(require("lube.view")), db: Session = Depends(get_db, scope="function")) -> list[Lubricant]:
    return list(db.execute(select(Lubricant).where(Lubricant.plant_id == ctx.plant_id).order_by(Lubricant.code)).scalars())


@router.post("/lubricants", response_model=LubricantOut, status_code=201)
def create_lubricant(
    body: LubricantIn, ctx: Ctx = Depends(require("lube.manage")), db: Session = Depends(get_db, scope="function")
) -> Lubricant:
    if body.part_id:
        from app.models.inventory import Part

        p = db.get(Part, body.part_id)
        if p is None or p.plant_id != ctx.plant_id:
            raise HTTPException(422, "Part not found")
    lub = Lubricant(plant_id=ctx.plant_id, **body.model_dump())
    db.add(lub)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Lubricant code exists") from e
    return lub


class AlternativeIn(In):
    alternative_id: uuid.UUID
    compatibility_note: str = Field(min_length=10, description="Evidence of verified compatibility")


@router.post("/lubricants/{lub_id}/alternatives", status_code=201)
def approve_alternative(
    lub_id: uuid.UUID,
    body: AlternativeIn,
    ctx: Ctx = Depends(require("lube.approve_alternative")),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    a, b = db.get(Lubricant, lub_id), db.get(Lubricant, body.alternative_id)
    if a is None or b is None or a.plant_id != ctx.plant_id or b.plant_id != ctx.plant_id:
        raise HTTPException(404, "Lubricant not found")
    if a.kind != b.kind:
        raise HTTPException(422, "An oil cannot be approved as an alternative to a grease (or vice versa)")
    alt = LubricantAlternative(
        lubricant_id=a.id, alternative_id=b.id, compatibility_note=body.compatibility_note, approved_by_id=ctx.user.id, approved_at=utcnow()
    )
    db.add(alt)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Alternative already recorded") from e
    audit(
        db,
        "lube.alternative_approved",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="lubricant",
        entity_id=a.id,
        data={"alternative": b.code, "note": body.compatibility_note},
    )
    return {"id": alt.id}


@router.get("/lubricants/{lub_id}/alternatives")
def list_alternatives(
    lub_id: uuid.UUID, ctx: Ctx = Depends(require("lube.view")), db: Session = Depends(get_db, scope="function")
) -> list[dict]:
    rows = db.execute(
        select(LubricantAlternative, Lubricant)
        .join(Lubricant, Lubricant.id == LubricantAlternative.alternative_id)
        .where(LubricantAlternative.lubricant_id == lub_id, Lubricant.plant_id == ctx.plant_id)
    ).all()
    return [
        {
            "alternative_id": lb.id,
            "code": lb.code,
            "product": f"{lb.manufacturer} {lb.product}",
            "note": a.compatibility_note,
            "approved_at": a.approved_at,
        }
        for a, lb in rows
    ]


class RouteIn(In):
    code: str
    name: str
    department_id: uuid.UUID
    lead_days: int = Field(2, ge=0, le=60)


class RouteOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    department_id: uuid.UUID
    lead_days: int
    is_active: bool


@router.get("/routes", response_model=list[RouteOut])
def list_routes(ctx: Ctx = Depends(require("lube.view")), db: Session = Depends(get_db, scope="function")) -> list[LubeRoute]:
    return list(db.execute(select(LubeRoute).where(LubeRoute.plant_id == ctx.plant_id).order_by(LubeRoute.code)).scalars())


@router.post("/routes", response_model=RouteOut, status_code=201)
def create_route(body: RouteIn, ctx: Ctx = Depends(require("lube.manage")), db: Session = Depends(get_db, scope="function")) -> LubeRoute:
    d = db.get(Department, body.department_id)
    if d is None or d.plant_id != ctx.plant_id:
        raise HTTPException(422, "Department not found")
    r = LubeRoute(plant_id=ctx.plant_id, **body.model_dump())
    db.add(r)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Route code exists") from e
    return r


class GenerateIn(In):
    as_of: date | None = None


@router.post("/routes/{route_id}/generate")
def generate(
    route_id: uuid.UUID, body: GenerateIn, ctx: Ctx = Depends(require("lube.manage")), db: Session = Depends(get_db, scope="function")
) -> dict:
    r = db.get(LubeRoute, route_id)
    if r is None or r.plant_id != ctx.plant_id:
        raise HTTPException(404, "Route not found")
    wo = svc.generate_route(db, ctx.plant, r, body.as_of, ctx.user.id)
    return {
        "work_order_id": wo.id if wo else None,
        "number": wo.number if wo else None,
        "message": None if wo else "No points due on this route",
    }


class PointIn(In):
    code: str
    asset_id: uuid.UUID
    component: str | None = None
    location: str | None = None
    lubricant_id: uuid.UUID
    quantity: float = Field(gt=0)
    unit: str = "g"
    method: str | None = None
    tools: str | None = None
    frequency_days: int | None = Field(None, ge=1)
    hours_interval: float | None = Field(None, gt=0)
    oem_recommendation: str | None = None
    route_id: uuid.UUID | None = None
    route_seq: int = 0
    responsible_user_id: uuid.UUID | None = None
    next_due_date: date | None = None


class PointOut(ORM):
    id: uuid.UUID
    code: str
    asset_id: uuid.UUID
    component: str | None
    location: str | None
    lubricant_id: uuid.UUID
    quantity: float
    unit: str
    method: str | None
    tools: str | None
    frequency_days: int | None
    hours_interval: float | None
    oem_recommendation: str | None
    route_id: uuid.UUID | None
    route_seq: int
    responsible_user_id: uuid.UUID | None
    last_done_date: date | None
    next_due_date: date | None
    qr_token: str
    is_active: bool


@router.get("/points", response_model=list[PointOut])
def list_points(
    ctx: Ctx = Depends(require("lube.view")),
    db: Session = Depends(get_db, scope="function"),
    route_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    due_before: date | None = None,
) -> list[LubricationPoint]:
    q = select(LubricationPoint).where(LubricationPoint.plant_id == ctx.plant_id)
    if route_id:
        q = q.where(LubricationPoint.route_id == route_id)
    if asset_id:
        q = q.where(LubricationPoint.asset_id == asset_id)
    if due_before:
        q = q.where(LubricationPoint.next_due_date <= due_before)
    return list(db.execute(q.order_by(LubricationPoint.route_seq, LubricationPoint.code).limit(2000)).scalars())


@router.post("/points", response_model=PointOut, status_code=201)
def create_point(
    body: PointIn, ctx: Ctx = Depends(require("lube.manage")), db: Session = Depends(get_db, scope="function")
) -> LubricationPoint:
    if not body.frequency_days and not body.hours_interval:
        raise HTTPException(422, "A frequency in days or an operating-hour interval is required")
    a, lub = db.get(Asset, body.asset_id), db.get(Lubricant, body.lubricant_id)
    if a is None or a.plant_id != ctx.plant_id or lub is None or lub.plant_id != ctx.plant_id:
        raise HTTPException(422, "Asset or lubricant not found")
    if body.route_id:
        r = db.get(LubeRoute, body.route_id)
        if r is None or r.plant_id != ctx.plant_id:
            raise HTTPException(422, "Route not found")
    p = LubricationPoint(plant_id=ctx.plant_id, qr_token=new_qr_token(), **body.model_dump())
    if p.next_due_date is None and p.frequency_days:
        p.next_due_date = plant_today(ctx.plant)
    db.add(p)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Point code exists") from e
    return p


@router.get("/points/labels.pdf")
def point_labels(
    ctx: Ctx = Depends(require("lube.view")),
    db: Session = Depends(get_db, scope="function"),
    route_id: uuid.UUID | None = None,
    under: uuid.UUID | None = None,
    skip: int = Query(0, ge=0, le=labels.PER_SHEET - 1),
) -> Response:
    """QR label sheets (A4, 24 per sheet) for lubrication points of a route and/or under an asset."""
    stmt = (
        select(LubricationPoint, Lubricant)
        .join(Lubricant, Lubricant.id == LubricationPoint.lubricant_id)
        .where(LubricationPoint.plant_id == ctx.plant_id, LubricationPoint.is_active.is_(True))
    )
    if route_id:
        stmt = stmt.where(LubricationPoint.route_id == route_id)
    if under:
        root = db.get(Asset, under)
        if root is None or root.plant_id != ctx.plant_id:
            raise HTTPException(404, "Asset not found")
        stmt = stmt.join(Asset, Asset.id == LubricationPoint.asset_id).where(Asset.path.startswith(root.path))
    rows = db.execute(stmt.order_by(LubricationPoint.code).limit(labels.MAX_LABELS + 1)).all()
    if len(rows) > labels.MAX_LABELS:
        raise HTTPException(422, f"More than {labels.MAX_LABELS} labels; choose a route or an area")
    items = [
        labels.Label(
            f"cmms:lube:{p.qr_token}",
            p.code,
            p.component or "",
            f"{lub.code} · {p.quantity:g} {p.unit}" + (f" · every {p.frequency_days} d" if p.frequency_days else ""),
        )
        for p, lub in rows
    ]
    return Response(
        labels.sheet_pdf(items, skip, "Lubrication QR labels"),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{labels.file_name("lubrication")}"'},
    )


@router.get("/points/{point_id}/qr.png")
def point_qr(point_id: uuid.UUID, ctx: Ctx = Depends(require("lube.view")), db: Session = Depends(get_db, scope="function")):  # type: ignore[no-untyped-def]
    import io

    import qrcode
    from fastapi.responses import StreamingResponse

    p = db.get(LubricationPoint, point_id)
    if p is None or p.plant_id != ctx.plant_id:
        raise HTTPException(404, "Point not found")
    buf = io.BytesIO()
    qrcode.make(f"cmms:lube:{p.qr_token}").save(buf, "PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.get("/points/by-qr/{token}", response_model=PointOut)
def point_by_qr(token: str, ctx: Ctx = Depends(require("lube.view")), db: Session = Depends(get_db, scope="function")) -> LubricationPoint:
    p = db.execute(
        select(LubricationPoint).where(LubricationPoint.qr_token == token, LubricationPoint.plant_id == ctx.plant_id)
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Point not found")
    return p


class TaskRecordIn(In):
    quantity: float = Field(gt=0)
    lubricant_used_id: uuid.UUID | None = None
    note: str | None = None
    done_date: date | None = None
    warehouse_id: uuid.UUID | None = None  # issue the lubricant from stock


@router.get("/tasks")
def list_tasks(
    ctx: Ctx = Depends(require("lube.view")),
    db: Session = Depends(get_db, scope="function"),
    status: LubeTaskStatus | None = None,
    work_order_id: uuid.UUID | None = None,
) -> list[dict]:
    q = (
        select(LubeTask, LubricationPoint)
        .join(LubricationPoint, LubricationPoint.id == LubeTask.point_id)
        .where(LubeTask.plant_id == ctx.plant_id)
    )
    if status:
        q = q.where(LubeTask.status == status)
    if work_order_id:
        q = q.where(LubeTask.work_order_id == work_order_id)
    return [
        {
            "id": t.id,
            "point_id": p.id,
            "point_code": p.code,
            "due_date": t.due_date,
            "status": t.status,
            "work_order_id": t.work_order_id,
            "done_date": t.done_date,
            "quantity_actual": t.quantity_actual,
        }
        for t, p in db.execute(q.order_by(LubeTask.due_date).limit(1000)).all()
    ]


def _task(db: Session, ctx: Ctx, task_id: uuid.UUID) -> LubeTask:
    t = db.execute(
        select(LubeTask).where(LubeTask.id == task_id, LubeTask.plant_id == ctx.plant_id).with_for_update(key_share=True)
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Task not found")
    return t


@router.post("/tasks/{task_id}/record")
def record(
    task_id: uuid.UUID, body: TaskRecordIn, ctx: Ctx = Depends(require("lube.execute")), db: Session = Depends(get_db, scope="function")
) -> dict:
    t = _task(db, ctx, task_id)
    if body.done_date and body.done_date > plant_today(ctx.plant):
        raise HTTPException(422, "Completion date cannot be in the future")
    if body.lubricant_used_id:
        lub = db.get(Lubricant, body.lubricant_used_id)
        if lub is None or lub.plant_id != ctx.plant_id:
            raise HTTPException(422, "Lubricant not found")
    res = svc.record_task(
        db, ctx.plant, t, ctx.user.id, body.quantity, body.lubricant_used_id, body.note, body.done_date, body.warehouse_id
    )
    audit(
        db,
        "lube.task_done",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="lube_task",
        entity_id=t.id,
        data={"qty": body.quantity},
    )
    return res


class SkipIn(In):
    reason: str = Field(min_length=5)


@router.post("/tasks/{task_id}/skip")
def skip(
    task_id: uuid.UUID, body: SkipIn, ctx: Ctx = Depends(require("lube.manage")), db: Session = Depends(get_db, scope="function")
) -> dict:
    t = _task(db, ctx, task_id)
    svc.skip_task(db, t, ctx.user.id, body.reason)
    audit(
        db, "lube.task_skipped", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="lube_task", entity_id=t.id, data=body.model_dump()
    )
    return {"status": t.status}


@router.get("/consumption")
def consumption(
    ctx: Ctx = Depends(require("lube.view")),
    db: Session = Depends(get_db, scope="function"),
    start: date | None = None,
    end: date | None = None,
) -> list[dict]:
    from sqlalchemy import func

    q = (
        select(Lubricant.code, Lubricant.product, LubricationPoint.unit, func.sum(LubeTask.quantity_actual), func.count())
        .join(LubricationPoint, LubricationPoint.id == LubeTask.point_id)
        .join(Lubricant, Lubricant.id == LubeTask.lubricant_used_id)
        .where(LubeTask.plant_id == ctx.plant_id, LubeTask.status == LubeTaskStatus.DONE)
        .group_by(Lubricant.code, Lubricant.product, LubricationPoint.unit)
    )
    if start:
        q = q.where(LubeTask.done_date >= start)
    if end:
        q = q.where(LubeTask.done_date <= end)
    return [{"lubricant": c, "product": p, "unit": u, "quantity": float(q_ or 0), "tasks": n} for c, p, u, q_, n in db.execute(q).all()]
