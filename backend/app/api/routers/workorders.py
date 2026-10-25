import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.api.pagination import PageQ, paginate
from app.core.db import get_db
from app.core.errors import DomainError
from app.models.assets import Asset, FailureCode
from app.models.enums import OPEN_WO_STATUSES, FailureCodeKind, Priority, RequestStatus, WOStatus, WOType
from app.models.identity import User
from app.models.inventory import InventoryTransaction, Part, Reservation, Supplier, Warehouse
from app.models.lubrication import LubeTask, LubricationPoint
from app.models.workorders import (
    WOChecklistItem,
    WOComment,
    WOLabor,
    WorkOrder,
    WorkRequest,
    WOService,
    WOStatusHistory,
)
from app.schemas.common import ORM, In
from app.services import inventory as inv
from app.services import workorders as svc
from app.services.common import audit, next_number, plant_today, utcnow
from app.services.notifications import notify_permission
from app.services.workflow import allowed_next

router = APIRouter(tags=["work orders"])


# ---------------- work requests ----------------
class RequestIn(In):
    asset_id: uuid.UUID
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    symptoms: str | None = None
    suggested_priority: Priority = Priority.P3_MEDIUM
    is_breakdown: bool = False


class RequestOut(ORM):
    id: uuid.UUID
    number: str
    asset_id: uuid.UUID
    title: str
    description: str | None
    symptoms: str | None
    suggested_priority: Priority
    is_breakdown: bool
    status: RequestStatus
    triage_note: str | None
    work_order_id: uuid.UUID | None
    created_at: datetime
    created_by_id: uuid.UUID | None


class TriageIn(In):
    accept: bool
    note: str | None = None
    type: WOType = WOType.CORRECTIVE
    priority: Priority | None = None


def _asset(db: Session, ctx: Ctx, asset_id: uuid.UUID) -> Asset:
    a = db.get(Asset, asset_id)
    if a is None or a.plant_id != ctx.plant_id:
        raise HTTPException(422, "Asset not found in this plant")
    return a


@router.post("/work-requests", response_model=RequestOut, status_code=201)
def create_request(body: RequestIn, ctx: Ctx = Depends(require("request.create")), db: Session = Depends(get_db)) -> WorkRequest:
    a = _asset(db, ctx, body.asset_id)
    r = WorkRequest(plant_id=ctx.plant_id, number=next_number(db, ctx.plant, "WR"), created_by_id=ctx.user.id, **body.model_dump())
    db.add(r)
    db.flush()
    notify_permission(
        db,
        ctx.plant_id,
        "request.triage",
        kind="work_request",
        severity="critical" if body.is_breakdown else "info",
        title=f"{'BREAKDOWN ' if body.is_breakdown else ''}Work request {r.number}",
        body=f"{a.code}: {r.title}",
        link=f"/requests/{r.id}",
        dedupe_key=f"wr:{r.id}",
        email=body.is_breakdown,
    )
    audit(db, "request.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="work_request", entity_id=r.id)
    return r


@router.get("/work-requests")
def list_requests(
    ctx: Ctx = Depends(require("wo.view")),
    db: Session = Depends(get_db),
    page: PageQ = Depends(),
    status: RequestStatus | None = None,
    mine: bool = False,
) -> dict:
    q = select(WorkRequest).where(WorkRequest.plant_id == ctx.plant_id)
    if status:
        q = q.where(WorkRequest.status == status)
    if mine:
        q = q.where(WorkRequest.created_by_id == ctx.user.id)
    return paginate(db, q.order_by(WorkRequest.created_at.desc()), page, RequestOut)


@router.post("/work-requests/{rid}/triage", response_model=RequestOut)
def triage(rid: uuid.UUID, body: TriageIn, ctx: Ctx = Depends(require("request.triage")), db: Session = Depends(get_db)) -> WorkRequest:
    r = db.execute(
        select(WorkRequest).where(WorkRequest.id == rid, WorkRequest.plant_id == ctx.plant_id).with_for_update(key_share=True)
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Request not found")
    if r.status != RequestStatus.SUBMITTED:
        raise DomainError("Request already triaged", "invalid_state", 409)
    r.triaged_by_id, r.triaged_at, r.triage_note = ctx.user.id, utcnow(), body.note
    if body.accept:
        a = _asset(db, ctx, r.asset_id)
        wtype = WOType.EMERGENCY if r.is_breakdown and body.type == WOType.CORRECTIVE else body.type
        wo = svc.create_work_order(
            db,
            ctx.plant,
            asset=a,
            type=wtype,
            title=r.title,
            user_id=ctx.user.id,
            priority=body.priority or r.suggested_priority,
            description=r.description,
            symptoms=r.symptoms,
            work_request_id=r.id,
        )
        r.status, r.work_order_id = RequestStatus.ACCEPTED, wo.id
    else:
        if not body.note:
            raise DomainError("A reason is required to reject a request", "reason_required", 422)
        r.status = RequestStatus.REJECTED
    audit(
        db,
        "request.triage",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="work_request",
        entity_id=r.id,
        data={"accept": body.accept},
    )
    return r


# ---------------- work orders ----------------
class WOCreate(In):
    asset_id: uuid.UUID
    type: WOType
    title: str = Field(min_length=3, max_length=200)
    priority: Priority = Priority.P3_MEDIUM
    description: str | None = None
    symptoms: str | None = None
    due_date: date | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    estimated_hours: float | None = Field(None, ge=0)
    estimated_cost: float | None = Field(None, ge=0)
    requires_loto: bool = False
    requires_permit: bool = False
    requires_testing: bool = False
    safety_requirements: str | None = None
    supervisor_id: uuid.UUID | None = None
    shutdown_package_id: uuid.UUID | None = None


class WOUpdate(In):
    title: str | None = None
    priority: Priority | None = None
    description: str | None = None
    symptoms: str | None = None
    due_date: date | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    estimated_hours: float | None = Field(None, ge=0)
    estimated_cost: float | None = Field(None, ge=0)
    requires_loto: bool | None = None
    requires_permit: bool | None = None
    requires_testing: bool | None = None
    permit_reference: str | None = None
    safety_requirements: str | None = None
    supervisor_id: uuid.UUID | None = None
    problem_code_id: uuid.UUID | None = None
    cause_code_id: uuid.UUID | None = None
    remedy_code_id: uuid.UUID | None = None
    downtime_hours: float | None = Field(None, ge=0)
    production_impact: str | None = None
    production_loss_tons: float | None = Field(None, ge=0)
    findings: str | None = None
    recommendations: str | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    shutdown_package_id: uuid.UUID | None = None
    version: int | None = None  # optimistic concurrency: send the version you edited


EXECUTION_FIELDS = {
    "findings",
    "recommendations",
    "root_cause",
    "corrective_action",
    "problem_code_id",
    "cause_code_id",
    "remedy_code_id",
    "downtime_hours",
    "production_impact",
    "production_loss_tons",
    "version",
}


class AssignmentOut(ORM):
    user_id: uuid.UUID
    is_lead: bool


class WOOut(ORM):
    id: uuid.UUID
    number: str
    type: WOType
    status: WOStatus
    priority: Priority
    asset_id: uuid.UUID
    department_id: uuid.UUID
    title: str
    description: str | None
    symptoms: str | None
    problem_code_id: uuid.UUID | None
    cause_code_id: uuid.UUID | None
    remedy_code_id: uuid.UUID | None
    supervisor_id: uuid.UUID | None
    due_date: date | None
    planned_start: datetime | None
    planned_end: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    estimated_hours: float | None
    estimated_cost: float | None
    actual_labor_hours: float
    actual_labor_cost: float
    actual_material_cost: float
    actual_service_cost: float
    actual_cost: float
    currency: str
    downtime_hours: float | None
    production_impact: str | None
    production_loss_tons: float | None
    requires_loto: bool
    requires_permit: bool
    permit_reference: str | None
    safety_requirements: str | None
    safety_signed_by_id: uuid.UUID | None
    safety_signed_at: datetime | None
    requires_testing: bool
    test_result: str | None
    test_passed: bool | None
    tested_by_id: uuid.UUID | None
    tested_at: datetime | None
    findings: str | None
    recommendations: str | None
    root_cause: str | None
    corrective_action: str | None
    is_repeat_failure: bool
    pm_occurrence_id: uuid.UUID | None
    condition_alert_id: uuid.UUID | None
    shutdown_package_id: uuid.UUID | None
    work_request_id: uuid.UUID | None
    version: int
    created_at: datetime
    assignments: list[AssignmentOut]


def get_wo(db: Session, ctx: Ctx, wo_id: uuid.UUID, lock: bool = False) -> WorkOrder:
    q = select(WorkOrder).where(WorkOrder.id == wo_id, WorkOrder.plant_id == ctx.plant_id)
    if lock:
        q = q.with_for_update(key_share=True)
    wo = db.execute(q).scalar_one_or_none()
    if wo is None or (ctx.department_id and wo.department_id != ctx.department_id):
        raise HTTPException(404, "Work order not found")
    return wo


def _is_assignee(ctx: Ctx, wo: WorkOrder) -> bool:
    return any(a.user_id == ctx.user.id for a in wo.assignments)


@router.get("/work-orders")
def list_work_orders(
    ctx: Ctx = Depends(require("wo.view")),
    db: Session = Depends(get_db),
    page: PageQ = Depends(),
    q: str | None = None,
    status: list[WOStatus] | None = None,
    type: list[WOType] | None = None,
    priority: Priority | None = None,
    asset_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    assigned_to_me: bool = False,
    open_only: bool = False,
    overdue: bool = False,
    due_from: date | None = None,
    due_to: date | None = None,
    ids: str | None = None,
    sort: str = "-created_at",
) -> dict:
    from fastapi import Query  # noqa: F401

    stmt = select(WorkOrder).where(WorkOrder.plant_id == ctx.plant_id)
    if ctx.department_id:
        stmt = stmt.where(WorkOrder.department_id == ctx.department_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(WorkOrder.number.ilike(like), WorkOrder.title.ilike(like)))
    if status:
        stmt = stmt.where(WorkOrder.status.in_(status))
    if open_only:
        stmt = stmt.where(WorkOrder.status.in_(OPEN_WO_STATUSES))
    if type:
        stmt = stmt.where(WorkOrder.type.in_(type))
    if priority:
        stmt = stmt.where(WorkOrder.priority == priority)
    if asset_id:
        stmt = stmt.where(WorkOrder.asset_id == asset_id)
    if department_id:
        stmt = stmt.where(WorkOrder.department_id == department_id)
    if due_from:
        stmt = stmt.where(WorkOrder.due_date >= due_from)
    if due_to:
        stmt = stmt.where(WorkOrder.due_date <= due_to)
    if overdue:
        stmt = stmt.where(WorkOrder.status.in_(OPEN_WO_STATUSES), WorkOrder.due_date < plant_today(ctx.plant))
    if ids:
        try:
            stmt = stmt.where(WorkOrder.id.in_([uuid.UUID(x) for x in ids.split(",") if x]))
        except ValueError as e:
            raise HTTPException(422, "Invalid ids") from e
    if assigned_to_me:
        from app.models.workorders import WOAssignment

        stmt = stmt.where(WorkOrder.id.in_(select(WOAssignment.work_order_id).where(WOAssignment.user_id == ctx.user.id)))
    sort_cols = {
        "created_at": WorkOrder.created_at,
        "due_date": WorkOrder.due_date,
        "priority": WorkOrder.priority,
        "number": WorkOrder.number,
        "planned_start": WorkOrder.planned_start,
    }
    col = sort_cols.get(sort.lstrip("-"), WorkOrder.created_at)
    stmt = stmt.order_by(col.desc().nulls_last() if sort.startswith("-") else col.asc().nulls_last(), WorkOrder.number)
    return paginate(db, stmt, page, WOOut)


@router.post("/work-orders", response_model=WOOut, status_code=201)
def create_wo(body: WOCreate, ctx: Ctx = Depends(require("wo.create")), db: Session = Depends(get_db)) -> WorkOrder:
    a = _asset(db, ctx, body.asset_id)
    if ctx.department_id and a.department_id != ctx.department_id:
        raise HTTPException(403, "Your access is limited to your department")
    data = body.model_dump()
    for k in ("asset_id", "type", "title", "priority", "description", "symptoms", "due_date"):
        data.pop(k)
    if body.planned_start and body.planned_end and body.planned_end < body.planned_start:
        raise HTTPException(422, "planned_end must be after planned_start")
    _check_refs(db, ctx, data)
    return svc.create_work_order(
        db,
        ctx.plant,
        asset=a,
        type=body.type,
        title=body.title,
        user_id=ctx.user.id,
        priority=body.priority,
        description=body.description,
        symptoms=body.symptoms,
        due_date=body.due_date,
        **data,
    )


def _check_refs(db: Session, ctx: Ctx, data: dict) -> None:
    from app.models.shutdowns import ShutdownPackage

    if data.get("supervisor_id"):
        from app.models.identity import Membership

        if not db.execute(
            select(Membership).where(Membership.user_id == data["supervisor_id"], Membership.plant_id == ctx.plant_id)
        ).first():
            raise HTTPException(422, "Supervisor is not a member of this plant")
    if data.get("shutdown_package_id"):
        p = db.get(ShutdownPackage, data["shutdown_package_id"])
        if p is None or p.plant_id != ctx.plant_id:
            raise HTTPException(422, "Shutdown package not found")
    for key, kind in (
        ("problem_code_id", FailureCodeKind.PROBLEM),
        ("cause_code_id", FailureCodeKind.CAUSE),
        ("remedy_code_id", FailureCodeKind.REMEDY),
    ):
        if data.get(key):
            fc = db.get(FailureCode, data[key])
            if fc is None or fc.plant_id != ctx.plant_id or fc.kind != kind:
                raise HTTPException(422, f"Invalid {kind.value} code")


@router.get("/work-orders/{wo_id}", response_model=WOOut)
def get_work_order(wo_id: uuid.UUID, ctx: Ctx = Depends(require("wo.view")), db: Session = Depends(get_db)) -> WorkOrder:
    return get_wo(db, ctx, wo_id)


@router.get("/work-orders/{wo_id}/detail")
def wo_detail(wo_id: uuid.UUID, ctx: Ctx = Depends(require("wo.view")), db: Session = Depends(get_db)) -> dict:
    """Everything a technician needs on one screen."""
    wo = get_wo(db, ctx, wo_id)
    asset = db.get(Asset, wo.asset_id)
    users = {u.id: u.full_name for u in db.execute(select(User).where(User.organization_id == ctx.plant.organization_id)).scalars()}
    checklist = (
        db.execute(select(WOChecklistItem).where(WOChecklistItem.work_order_id == wo.id).order_by(WOChecklistItem.seq)).scalars().all()
    )
    labor = db.execute(select(WOLabor).where(WOLabor.work_order_id == wo.id).order_by(WOLabor.work_date)).scalars().all()
    services = db.execute(select(WOService).where(WOService.work_order_id == wo.id)).scalars().all()
    hist = (
        db.execute(select(WOStatusHistory).where(WOStatusHistory.work_order_id == wo.id).order_by(WOStatusHistory.changed_at))
        .scalars()
        .all()
    )
    res = db.execute(
        select(Reservation, Part, Warehouse)
        .join(Part, Part.id == Reservation.part_id)
        .join(Warehouse, Warehouse.id == Reservation.warehouse_id)
        .where(Reservation.work_order_id == wo.id)
    ).all()
    txns = db.execute(
        select(InventoryTransaction, Part)
        .join(Part, Part.id == InventoryTransaction.part_id)
        .where(InventoryTransaction.work_order_id == wo.id)
        .order_by(InventoryTransaction.created_at)
    ).all()
    comments = db.execute(select(WOComment).where(WOComment.work_order_id == wo.id).order_by(WOComment.created_at)).scalars().all()
    lube = db.execute(
        select(LubeTask, LubricationPoint)
        .join(LubricationPoint, LubricationPoint.id == LubeTask.point_id)
        .where(LubeTask.work_order_id == wo.id)
        .order_by(LubricationPoint.route_seq)
    ).all()
    from app.models.lubrication import Lubricant

    lubs = {lb.id: lb for lb in db.execute(select(Lubricant).where(Lubricant.plant_id == ctx.plant_id)).scalars()}
    return {
        "work_order": WOOut.model_validate(wo).model_dump(mode="json"),
        "asset": {"id": asset.id, "code": asset.code, "name": asset.name, "location": asset.location, "criticality": asset.criticality}
        if asset
        else None,
        "allowed_transitions": allowed_next(db, ctx.plant_id, wo.status, ctx.permissions),
        "assignees": [{"user_id": a.user_id, "name": users.get(a.user_id), "is_lead": a.is_lead} for a in wo.assignments],
        "checklist": [
            {
                "id": c.id,
                "seq": c.seq,
                "description": c.description,
                "kind": c.kind,
                "is_required": c.is_required,
                "unit": c.unit,
                "min_value": c.min_value,
                "max_value": c.max_value,
                "is_done": c.is_done,
                "is_ok": c.is_ok,
                "reading_value": c.reading_value,
                "remark": c.remark,
                "done_by": users.get(c.done_by_id) if c.done_by_id else None,
                "done_at": c.done_at,
            }
            for c in checklist
        ],
        "labor": [
            {
                "id": lab.id,
                "user_id": lab.user_id,
                "name": users.get(lab.user_id),
                "work_date": lab.work_date,
                "hours": lab.hours,
                "is_overtime": lab.is_overtime,
                "cost": lab.cost,
                "notes": lab.notes,
            }
            for lab in labor
        ],
        "services": [{"id": s.id, "description": s.description, "cost": s.cost, "po_reference": s.po_reference} for s in services],
        "reservations": [
            {
                "id": r.id,
                "part_id": p.id,
                "part_code": p.code,
                "description": p.description,
                "warehouse": w.code,
                "warehouse_id": w.id,
                "quantity": r.quantity,
                "qty_issued": r.qty_issued,
                "status": r.status,
                "uom": p.uom,
            }
            for r, p, w in res
        ],
        "transactions": [
            {
                "id": t.id,
                "part_code": p.code,
                "type": t.type,
                "quantity": t.quantity,
                "unit_cost": t.unit_cost,
                "total_cost": t.total_cost,
                "at": t.created_at,
            }
            for t, p in txns
        ],
        "history": [
            {
                "from": h.from_status,
                "to": h.to_status,
                "by": users.get(h.changed_by_id) if h.changed_by_id else "system",
                "at": h.changed_at,
                "comment": h.comment,
            }
            for h in hist
        ],
        "comments": [{"id": c.id, "user": users.get(c.user_id), "body": c.body, "at": c.created_at} for c in comments],
        "lube_tasks": [
            {
                "id": t.id,
                "point_code": p.code,
                "component": p.component,
                "location": p.location,
                "lubricant": f"{lubs[p.lubricant_id].manufacturer} {lubs[p.lubricant_id].product}" if p.lubricant_id in lubs else None,
                "lubricant_id": p.lubricant_id,
                "quantity": p.quantity,
                "unit": p.unit,
                "method": p.method,
                "status": t.status,
                "quantity_actual": t.quantity_actual,
                "due_date": t.due_date,
            }
            for t, p in lube
        ],
        "safety_signed_by": users.get(wo.safety_signed_by_id) if wo.safety_signed_by_id else None,
        "tested_by": users.get(wo.tested_by_id) if wo.tested_by_id else None,
    }


@router.patch("/work-orders/{wo_id}", response_model=WOOut)
def update_wo(wo_id: uuid.UUID, body: WOUpdate, ctx: Ctx = Depends(require("wo.view")), db: Session = Depends(get_db)) -> WorkOrder:
    wo = get_wo(db, ctx, wo_id, lock=True)
    data = body.model_dump(exclude_unset=True)
    version = data.pop("version", None)
    if version is not None and version != wo.version:
        raise DomainError("This work order was changed by someone else. Reload and retry.", "stale_version", 409)
    if wo.status in (WOStatus.CLOSED, WOStatus.CANCELLED):
        raise DomainError("Closed or cancelled work orders are read-only", "read_only", 409)
    # Field-level authorization: assignees with wo.execute may update execution fields only.
    planning_fields = set(data) - EXECUTION_FIELDS
    if planning_fields:
        ctx.require("wo.edit")
    elif not (ctx.has("wo.edit") or (ctx.has("wo.execute") and _is_assignee(ctx, wo))):
        raise HTTPException(403, "Only assigned technicians or editors may update this work order")
    if wo.status == WOStatus.COMPLETED and planning_fields:
        raise DomainError("Completed work orders accept execution details only", "read_only", 409)
    ps, pe = data.get("planned_start", wo.planned_start), data.get("planned_end", wo.planned_end)
    if ps and pe and pe < ps:
        raise HTTPException(422, "planned_end must be after planned_start")
    _check_refs(db, ctx, data)
    for k, v in data.items():
        setattr(wo, k, v)
    audit(db, "wo.update", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="work_order", entity_id=wo.id, data=data)
    db.flush()
    return wo


class StatusIn(In):
    to: WOStatus
    comment: str | None = None


@router.post("/work-orders/{wo_id}/status", response_model=WOOut)
def set_status(wo_id: uuid.UUID, body: StatusIn, ctx: Ctx = Depends(require("wo.view")), db: Session = Depends(get_db)) -> WorkOrder:
    wo = get_wo(db, ctx, wo_id, lock=True)
    # Technicians may only move work they are assigned to.
    if (
        body.to in (WOStatus.IN_PROGRESS, WOStatus.ON_HOLD, WOStatus.AWAITING_REVIEW)
        and not ctx.has("wo.assign")
        and not _is_assignee(ctx, wo)
    ):
        raise HTTPException(403, "You are not assigned to this work order")
    svc.change_status(db, ctx, wo, body.to, body.comment)
    db.flush()
    return wo


class AssignIn(In):
    user_ids: list[uuid.UUID] = Field(min_length=1)
    lead_id: uuid.UUID | None = None
    force: bool = False


@router.post("/work-orders/{wo_id}/assign")
def assign(wo_id: uuid.UUID, body: AssignIn, ctx: Ctx = Depends(require("wo.assign")), db: Session = Depends(get_db)) -> dict:
    wo = get_wo(db, ctx, wo_id, lock=True)
    warnings = svc.assign(db, ctx, wo, body.user_ids, body.lead_id, body.force)
    return {"warnings": warnings, "assignees": [a.user_id for a in wo.assignments]}


@router.delete("/work-orders/{wo_id}/assign/{user_id}", status_code=204)
def unassign(wo_id: uuid.UUID, user_id: uuid.UUID, ctx: Ctx = Depends(require("wo.assign")), db: Session = Depends(get_db)) -> None:
    wo = get_wo(db, ctx, wo_id, lock=True)
    wo.assignments = [a for a in wo.assignments if a.user_id != user_id]
    audit(db, "wo.unassign", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="work_order", entity_id=wo.id, data={"user": user_id})


class BulkAssignIn(In):
    work_order_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    user_ids: list[uuid.UUID] = Field(min_length=1)
    lead_id: uuid.UUID | None = None
    force: bool = False


@router.post("/work-orders/bulk-assign")
def bulk_assign(body: BulkAssignIn, ctx: Ctx = Depends(require("wo.assign")), db: Session = Depends(get_db)) -> dict:
    results = {}
    for wid in body.work_order_ids:
        wo = get_wo(db, ctx, wid, lock=True)
        results[wo.number] = svc.assign(db, ctx, wo, body.user_ids, body.lead_id, body.force)
    return {"assigned": len(results), "warnings": results}


class SafetyIn(In):
    permit_reference: str | None = None
    note: str | None = None


@router.post("/work-orders/{wo_id}/safety-signoff", response_model=WOOut)
def safety_signoff(
    wo_id: uuid.UUID, body: SafetyIn, ctx: Ctx = Depends(require("wo.safety_signoff")), db: Session = Depends(get_db)
) -> WorkOrder:
    wo = get_wo(db, ctx, wo_id, lock=True)
    if body.permit_reference:
        wo.permit_reference = body.permit_reference
    if wo.requires_permit and not wo.permit_reference:
        raise DomainError("Permit reference is required for sign-off", "permit_required", 422)
    wo.safety_signed_by_id, wo.safety_signed_at = ctx.user.id, utcnow()
    audit(
        db,
        "wo.safety_signoff",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="work_order",
        entity_id=wo.id,
        data=body.model_dump(),
        ip=ctx.ip,
    )
    db.flush()
    return wo


class TestIn(In):
    test_result: str = Field(min_length=3)
    test_passed: bool


@router.post("/work-orders/{wo_id}/test-result", response_model=WOOut)
def test_result(wo_id: uuid.UUID, body: TestIn, ctx: Ctx = Depends(require("wo.review")), db: Session = Depends(get_db)) -> WorkOrder:
    wo = get_wo(db, ctx, wo_id, lock=True)
    if wo.status not in (WOStatus.IN_PROGRESS, WOStatus.AWAITING_REVIEW):
        raise DomainError("Test results are recorded during execution or review", "invalid_state", 409)
    wo.test_result, wo.test_passed, wo.tested_by_id, wo.tested_at = body.test_result, body.test_passed, ctx.user.id, utcnow()
    audit(
        db, "wo.test_result", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="work_order", entity_id=wo.id, data=body.model_dump()
    )
    db.flush()
    return wo


class ChecklistUpdate(In):
    is_done: bool = True
    is_ok: bool | None = None
    reading_value: float | None = None
    remark: str | None = None


def _require_execute(ctx: Ctx, wo: WorkOrder) -> None:
    if not (ctx.has("wo.execute") and (_is_assignee(ctx, wo) or ctx.has("wo.assign"))):
        raise HTTPException(403, "Only assigned technicians or supervisors may record execution")
    if wo.status not in (WOStatus.IN_PROGRESS, WOStatus.ON_HOLD):
        raise DomainError("Work must be in progress to record execution", "wo_not_in_progress", 409)


@router.patch("/work-orders/{wo_id}/checklist/{item_id}")
def update_checklist(
    wo_id: uuid.UUID, item_id: uuid.UUID, body: ChecklistUpdate, ctx: Ctx = Depends(require("wo.execute")), db: Session = Depends(get_db)
) -> dict:
    wo = get_wo(db, ctx, wo_id)
    _require_execute(ctx, wo)
    item = db.get(WOChecklistItem, item_id)
    if item is None or item.work_order_id != wo.id:
        raise HTTPException(404, "Checklist item not found")
    if item.kind.value == "reading" and body.is_done and body.reading_value is None:
        raise HTTPException(422, "A reading value is required")
    item.is_done, item.remark = body.is_done, body.remark
    item.reading_value = body.reading_value
    if body.reading_value is not None and (item.min_value is not None or item.max_value is not None):
        lo = float(item.min_value) if item.min_value is not None else float("-inf")
        hi = float(item.max_value) if item.max_value is not None else float("inf")
        item.is_ok = lo <= body.reading_value <= hi
    else:
        item.is_ok = body.is_ok if body.is_ok is not None else (True if body.is_done else None)
    item.done_by_id, item.done_at = (ctx.user.id, utcnow()) if body.is_done else (None, None)
    return {
        "id": item.id,
        "is_done": item.is_done,
        "is_ok": item.is_ok,
        "out_of_range": item.is_ok is False and body.reading_value is not None,
    }


class ChecklistAdd(In):
    description: str
    kind: str = Field("check", pattern="^(check|reading)$")
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    is_required: bool = True


@router.post("/work-orders/{wo_id}/checklist", status_code=201)
def add_checklist(wo_id: uuid.UUID, body: ChecklistAdd, ctx: Ctx = Depends(require("wo.edit")), db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import func

    wo = get_wo(db, ctx, wo_id)
    seq = (db.execute(select(func.max(WOChecklistItem.seq)).where(WOChecklistItem.work_order_id == wo.id)).scalar() or 0) + 10
    it = WOChecklistItem(work_order_id=wo.id, seq=seq, **body.model_dump())
    db.add(it)
    db.flush()
    return {"id": it.id}


class LaborIn(In):
    user_id: uuid.UUID | None = None
    work_date: date
    hours: float = Field(gt=0, le=24)
    is_overtime: bool = False
    notes: str | None = None


@router.post("/work-orders/{wo_id}/labor", status_code=201)
def add_labor(wo_id: uuid.UUID, body: LaborIn, ctx: Ctx = Depends(require("wo.execute")), db: Session = Depends(get_db)) -> dict:
    wo = get_wo(db, ctx, wo_id, lock=True)
    if not (_is_assignee(ctx, wo) or ctx.has("wo.assign")):
        raise HTTPException(403, "You are not assigned to this work order")
    if body.work_date > plant_today(ctx.plant):
        raise HTTPException(422, "Labor cannot be booked in the future")
    lab = svc.add_labor(db, ctx, wo, body.user_id or ctx.user.id, body.work_date, body.hours, body.is_overtime, body.notes)
    return {"id": lab.id, "cost": float(lab.cost), "wo_labor_hours": float(wo.actual_labor_hours)}


class ServiceIn(In):
    description: str
    cost: float = Field(ge=0)
    supplier_id: uuid.UUID | None = None
    po_reference: str | None = None


@router.post("/work-orders/{wo_id}/services", status_code=201)
def add_service(wo_id: uuid.UUID, body: ServiceIn, ctx: Ctx = Depends(require("wo.edit")), db: Session = Depends(get_db)) -> dict:
    from decimal import Decimal

    wo = get_wo(db, ctx, wo_id, lock=True)
    if body.supplier_id:
        sp = db.get(Supplier, body.supplier_id)
        if sp is None or sp.plant_id != ctx.plant_id:
            raise HTTPException(422, "Supplier not found")
    s = WOService(work_order_id=wo.id, created_at=utcnow(), created_by_id=ctx.user.id, **body.model_dump())
    db.add(s)
    wo.actual_service_cost = Decimal(str(wo.actual_service_cost or 0)) + Decimal(str(body.cost))
    db.flush()
    return {"id": s.id}


class CommentIn(In):
    body: str = Field(min_length=1, max_length=5000)


@router.post("/work-orders/{wo_id}/comments", status_code=201)
def add_comment(wo_id: uuid.UUID, body: CommentIn, ctx: Ctx = Depends(require("wo.view")), db: Session = Depends(get_db)) -> dict:
    wo = get_wo(db, ctx, wo_id)
    c = WOComment(work_order_id=wo.id, user_id=ctx.user.id, body=body.body, created_at=utcnow())
    db.add(c)
    db.flush()
    return {"id": c.id}


# ---------------- materials on a work order ----------------
class ReserveIn(In):
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: float = Field(gt=0)


def _part_wh(db: Session, ctx: Ctx, part_id: uuid.UUID, wh_id: uuid.UUID) -> tuple[Part, Warehouse]:
    p, w = db.get(Part, part_id), db.get(Warehouse, wh_id)
    if p is None or w is None or p.plant_id != ctx.plant_id or w.plant_id != ctx.plant_id:
        raise HTTPException(422, "Part or warehouse not found")
    return p, w


@router.post("/work-orders/{wo_id}/reservations", status_code=201)
def reserve(wo_id: uuid.UUID, body: ReserveIn, ctx: Ctx = Depends(require("inventory.reserve")), db: Session = Depends(get_db)) -> dict:
    wo = get_wo(db, ctx, wo_id)
    p, w = _part_wh(db, ctx, body.part_id, body.warehouse_id)
    r = inv.reserve(db, ctx.plant, wo, p, w, body.quantity, ctx.user.id)
    audit(
        db,
        "inventory.reserve",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="reservation",
        entity_id=r.id,
        data={"wo": wo.number, "part": p.code, "qty": body.quantity},
    )
    return {"id": r.id}


@router.delete("/work-orders/{wo_id}/reservations/{res_id}", status_code=204)
def cancel_res(
    wo_id: uuid.UUID, res_id: uuid.UUID, ctx: Ctx = Depends(require("inventory.reserve")), db: Session = Depends(get_db)
) -> None:
    wo = get_wo(db, ctx, wo_id)
    r = db.get(Reservation, res_id)
    if r is None or r.work_order_id != wo.id:
        raise HTTPException(404, "Reservation not found")
    inv.cancel_reservation(db, r)


class IssueIn(In):
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: float = Field(gt=0)
    reservation_id: uuid.UUID | None = None


@router.post("/work-orders/{wo_id}/issues", status_code=201)
def issue(wo_id: uuid.UUID, body: IssueIn, ctx: Ctx = Depends(require("inventory.transact")), db: Session = Depends(get_db)) -> dict:
    wo = get_wo(db, ctx, wo_id, lock=True)
    p, w = _part_wh(db, ctx, body.part_id, body.warehouse_id)
    r = None
    if body.reservation_id:
        r = db.execute(select(Reservation).where(Reservation.id == body.reservation_id).with_for_update(key_share=True)).scalar_one_or_none()
        if r is None or r.work_order_id != wo.id:
            raise HTTPException(404, "Reservation not found")
    tx = inv.issue(db, ctx.plant, p, w, body.quantity, ctx.user.id, wo=wo, reservation=r, reference=wo.number)
    audit(
        db,
        "inventory.issue",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="inventory_txn",
        entity_id=tx.id,
        data={"wo": wo.number, "part": p.code, "qty": body.quantity, "cost": tx.total_cost},
    )
    return {
        "transaction_id": tx.id,
        "unit_cost": float(tx.unit_cost),
        "total_cost": -float(tx.total_cost),
        "balance_after": float(tx.balance_after),
        "wo_material_cost": float(wo.actual_material_cost),
    }


class ReturnIn(In):
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: float = Field(gt=0)
    reason: str | None = None


@router.post("/work-orders/{wo_id}/returns", status_code=201)
def return_stock(
    wo_id: uuid.UUID, body: ReturnIn, ctx: Ctx = Depends(require("inventory.transact")), db: Session = Depends(get_db)
) -> dict:
    wo = get_wo(db, ctx, wo_id, lock=True)
    p, w = _part_wh(db, ctx, body.part_id, body.warehouse_id)
    tx = inv.return_to_stock(db, ctx.plant, p, w, body.quantity, ctx.user.id, wo, body.reason)
    audit(db, "inventory.return", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="inventory_txn", entity_id=tx.id)
    return {"transaction_id": tx.id, "wo_material_cost": float(wo.actual_material_cost)}
