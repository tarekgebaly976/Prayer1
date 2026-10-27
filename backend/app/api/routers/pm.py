import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.api.pagination import PageQ, paginate
from app.core.db import get_db
from app.models.assets import Asset, Meter
from app.models.enums import (
    ChecklistKind,
    FrequencyUnit,
    OccurrenceStatus,
    PMTrigger,
    Priority,
    ScheduleBasis,
    WOType,
)
from app.models.inventory import Part
from app.models.pm import JobPlan, JobPlanMaterial, JobPlanTask, PMOccurrence, PMPlan
from app.schemas.common import ORM, In
from app.services import pm as svc
from app.services.common import audit, plant_today
from app.services.system import record_job

router = APIRouter(prefix="/pm", tags=["preventive maintenance"])


class TaskIn(In):
    seq: int = Field(ge=1)
    description: str = Field(min_length=2, max_length=400)
    kind: ChecklistKind = ChecklistKind.CHECK
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    is_required: bool = True


class MaterialIn(In):
    part_id: uuid.UUID
    quantity: float = Field(gt=0)


class JobPlanIn(In):
    code: str = Field(min_length=1, max_length=40)
    name: str
    description: str | None = None
    trade: str | None = None
    estimated_hours: float = Field(1, gt=0)
    crew_size: int = Field(1, ge=1)
    tools: str | None = None
    safety_precautions: str | None = None
    requires_loto: bool = False
    requires_permit: bool = False
    requires_testing: bool = False
    permit_types: str | None = None
    tasks: list[TaskIn] = Field(default_factory=list)
    materials: list[MaterialIn] = Field(default_factory=list)


class JobPlanOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    trade: str | None
    estimated_hours: float
    crew_size: int
    tools: str | None
    safety_precautions: str | None
    requires_loto: bool
    requires_permit: bool
    requires_testing: bool
    permit_types: str | None


@router.get("/job-plans", response_model=list[JobPlanOut])
def list_job_plans(ctx: Ctx = Depends(require("pm.view")), db: Session = Depends(get_db, scope="function")) -> list[JobPlan]:
    return list(db.execute(select(JobPlan).where(JobPlan.plant_id == ctx.plant_id).order_by(JobPlan.code)).scalars())


@router.get("/job-plans/{jp_id}")
def get_job_plan(jp_id: uuid.UUID, ctx: Ctx = Depends(require("pm.view")), db: Session = Depends(get_db, scope="function")) -> dict:
    jp = db.get(JobPlan, jp_id)
    if jp is None or jp.plant_id != ctx.plant_id:
        raise HTTPException(404, "Job plan not found")
    tasks = db.execute(select(JobPlanTask).where(JobPlanTask.job_plan_id == jp.id).order_by(JobPlanTask.seq)).scalars()
    mats = db.execute(
        select(JobPlanMaterial, Part).join(Part, Part.id == JobPlanMaterial.part_id).where(JobPlanMaterial.job_plan_id == jp.id)
    ).all()
    return {
        **JobPlanOut.model_validate(jp).model_dump(),
        "tasks": [
            {
                "seq": t.seq,
                "description": t.description,
                "kind": t.kind,
                "unit": t.unit,
                "min_value": t.min_value,
                "max_value": t.max_value,
                "is_required": t.is_required,
            }
            for t in tasks
        ],
        "materials": [{"part_id": p.id, "part_code": p.code, "description": p.description, "quantity": m.quantity} for m, p in mats],
    }


@router.post("/job-plans", response_model=JobPlanOut, status_code=201)
def create_job_plan(body: JobPlanIn, ctx: Ctx = Depends(require("pm.manage")), db: Session = Depends(get_db, scope="function")) -> JobPlan:
    data = body.model_dump(exclude={"tasks", "materials"})
    jp = JobPlan(plant_id=ctx.plant_id, created_by_id=ctx.user.id, **data)
    db.add(jp)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Job plan code exists") from e
    if len({t.seq for t in body.tasks}) != len(body.tasks):
        raise HTTPException(422, "Task sequence numbers must be unique")
    for t in body.tasks:
        db.add(JobPlanTask(job_plan_id=jp.id, **t.model_dump()))
    for m in body.materials:
        p = db.get(Part, m.part_id)
        if p is None or p.plant_id != ctx.plant_id:
            raise HTTPException(422, "Part not found")
        db.add(JobPlanMaterial(job_plan_id=jp.id, **m.model_dump()))
    audit(db, "jobplan.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="job_plan", entity_id=jp.id)
    return jp


class PlanIn(In):
    code: str = Field(min_length=1, max_length=40)
    name: str
    asset_id: uuid.UUID
    job_plan_id: uuid.UUID
    trigger: PMTrigger = PMTrigger.CALENDAR
    wo_type: WOType = WOType.PREVENTIVE
    priority: Priority = Priority.P3_MEDIUM
    frequency_unit: FrequencyUnit | None = None
    frequency_interval: int | None = Field(None, ge=1)
    schedule_basis: ScheduleBasis = ScheduleBasis.FIXED
    start_date: date | None = None
    meter_id: uuid.UUID | None = None
    meter_interval: float | None = Field(None, gt=0)
    last_meter_value: float | None = Field(None, ge=0)
    horizon_days: int = Field(30, ge=1, le=730)
    lead_days: int = Field(7, ge=0, le=365)
    tolerance_days: int = Field(0, ge=0, le=60)

    @model_validator(mode="after")
    def _check(self) -> "PlanIn":
        if self.trigger == PMTrigger.CALENDAR and not (self.frequency_unit and self.frequency_interval and self.start_date):
            raise ValueError("Calendar plans need frequency_unit, frequency_interval and start_date")
        if self.trigger == PMTrigger.METER and not (self.meter_id and self.meter_interval):
            raise ValueError("Meter plans need meter_id and meter_interval")
        if self.wo_type not in (WOType.PREVENTIVE, WOType.INSPECTION, WOType.PREDICTIVE):
            raise ValueError("PM plans generate preventive, inspection or predictive work orders")
        return self


class PlanUpdate(In):
    name: str | None = None
    priority: Priority | None = None
    horizon_days: int | None = Field(None, ge=1, le=730)
    lead_days: int | None = Field(None, ge=0, le=365)
    tolerance_days: int | None = Field(None, ge=0, le=60)
    is_active: bool | None = None


class PlanOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    asset_id: uuid.UUID
    job_plan_id: uuid.UUID
    trigger: PMTrigger
    wo_type: WOType
    priority: Priority
    frequency_unit: FrequencyUnit | None
    frequency_interval: int | None
    schedule_basis: ScheduleBasis
    start_date: date | None
    meter_id: uuid.UUID | None
    meter_interval: float | None
    last_meter_value: float | None
    horizon_days: int
    lead_days: int
    tolerance_days: int
    last_completed_date: date | None
    next_due_date: date | None
    is_active: bool


@router.get("/plans")
def list_plans(
    ctx: Ctx = Depends(require("pm.view")),
    db: Session = Depends(get_db, scope="function"),
    page: PageQ = Depends(),
    asset_id: uuid.UUID | None = None,
    active: bool | None = None,
) -> dict:
    q = select(PMPlan).where(PMPlan.plant_id == ctx.plant_id)
    if asset_id:
        q = q.where(PMPlan.asset_id == asset_id)
    if active is not None:
        q = q.where(PMPlan.is_active.is_(active))
    return paginate(db, q.order_by(PMPlan.next_due_date.asc().nulls_last(), PMPlan.code), page, PlanOut)


@router.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(body: PlanIn, ctx: Ctx = Depends(require("pm.manage")), db: Session = Depends(get_db, scope="function")) -> PMPlan:
    a, jp = db.get(Asset, body.asset_id), db.get(JobPlan, body.job_plan_id)
    if a is None or a.plant_id != ctx.plant_id or jp is None or jp.plant_id != ctx.plant_id:
        raise HTTPException(422, "Asset or job plan not found")
    if body.meter_id:
        m = db.get(Meter, body.meter_id)
        if m is None or m.plant_id != ctx.plant_id:
            raise HTTPException(422, "Meter not found")
    p = PMPlan(plant_id=ctx.plant_id, created_by_id=ctx.user.id, **body.model_dump())
    db.add(p)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "PM plan code exists") from e
    svc.plan_occurrences(db, ctx.plant, p, plant_today(ctx.plant))
    audit(db, "pm.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="pm_plan", entity_id=p.id)
    return p


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: uuid.UUID, body: PlanUpdate, ctx: Ctx = Depends(require("pm.manage")), db: Session = Depends(get_db, scope="function")
) -> PMPlan:
    p = db.get(PMPlan, plan_id)
    if p is None or p.plant_id != ctx.plant_id:
        raise HTTPException(404, "PM plan not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    audit(
        db,
        "pm.update",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="pm_plan",
        entity_id=p.id,
        data=body.model_dump(exclude_unset=True),
    )
    return p


class OccOut(ORM):
    id: uuid.UUID
    pm_plan_id: uuid.UUID
    occurrence_key: str
    due_date: date
    original_due_date: date
    due_meter: float | None
    status: OccurrenceStatus
    work_order_id: uuid.UUID | None
    completed_date: date | None
    request_reason: str | None
    requested_new_date: date | None
    requested_by_id: uuid.UUID | None


@router.get("/occurrences")
def list_occurrences(
    ctx: Ctx = Depends(require("pm.view")),
    db: Session = Depends(get_db, scope="function"),
    page: PageQ = Depends(),
    plan_id: uuid.UUID | None = None,
    status: list[OccurrenceStatus] | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
) -> dict:
    from fastapi import Query  # noqa: F401

    q = select(PMOccurrence).where(PMOccurrence.plant_id == ctx.plant_id)
    if plan_id:
        q = q.where(PMOccurrence.pm_plan_id == plan_id)
    if status:
        q = q.where(PMOccurrence.status.in_(status))
    if due_from:
        q = q.where(PMOccurrence.due_date >= due_from)
    if due_to:
        q = q.where(PMOccurrence.due_date <= due_to)
    return paginate(db, q.order_by(PMOccurrence.due_date), page, OccOut)


class ChangeRequestIn(In):
    kind: str = Field(pattern="^(defer|cancel)$")
    reason: str = Field(min_length=5)
    new_date: date | None = None


def _occ(db: Session, ctx: Ctx, occ_id: uuid.UUID) -> PMOccurrence:
    o = db.execute(
        select(PMOccurrence).where(PMOccurrence.id == occ_id, PMOccurrence.plant_id == ctx.plant_id).with_for_update(key_share=True)
    ).scalar_one_or_none()
    if o is None:
        raise HTTPException(404, "Occurrence not found")
    return o


@router.post("/occurrences/{occ_id}/request", response_model=OccOut)
def request_change(
    occ_id: uuid.UUID, body: ChangeRequestIn, ctx: Ctx = Depends(require("pm.view")), db: Session = Depends(get_db, scope="function")
) -> PMOccurrence:
    if not (ctx.has("wo.plan") or ctx.has("wo.execute")):
        raise HTTPException(403, "Not permitted")
    return svc.request_change(db, ctx.plant, _occ(db, ctx, occ_id), ctx.user.id, body.kind, body.reason, body.new_date)


class DecisionIn(In):
    approve: bool


@router.post("/occurrences/{occ_id}/decide", response_model=OccOut)
def decide(
    occ_id: uuid.UUID, body: DecisionIn, ctx: Ctx = Depends(require("pm.approve_deferral")), db: Session = Depends(get_db, scope="function")
) -> PMOccurrence:
    return svc.decide_change(db, ctx.plant, _occ(db, ctx, occ_id), ctx.user.id, body.approve)


class RunIn(In):
    as_of: date | None = None  # testing / back-office: run as if today were this date (planners only)


@router.post("/scheduler/run")
def run_scheduler(body: RunIn, ctx: Ctx = Depends(require("pm.run_scheduler")), db: Session = Depends(get_db, scope="function")) -> dict:
    with record_job(db, "pm_scheduler_manual") as details:
        res = svc.run_scheduler(db, ctx.plant, body.as_of)
        details.update(res)
    audit(db, "pm.scheduler_run", user_id=ctx.user.id, plant_id=ctx.plant_id, data=res)
    return res
