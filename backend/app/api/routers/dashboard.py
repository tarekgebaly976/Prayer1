from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Ctx, get_ctx
from app.core.db import get_db
from app.models.enums import (
    OPEN_WO_STATUSES,
    AlertStatus,
    ConditionStatus,
    LubeTaskStatus,
    OccurrenceStatus,
    RequestStatus,
    WOStatus,
    WOType,
)
from app.models.lubrication import LubeTask
from app.models.pdm import ConditionAlert
from app.models.pm import PMOccurrence
from app.models.workorders import WOAssignment, WorkOrder, WorkRequest
from app.services.common import plant_today

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function")) -> dict:
    """Operational counters for the landing page (only what the caller may see)."""
    today = plant_today(ctx.plant)
    out: dict = {"today": today.isoformat(), "timezone": ctx.plant.timezone}

    def wo_count(*conds) -> int:
        q = select(func.count()).select_from(WorkOrder).where(WorkOrder.plant_id == ctx.plant_id, *conds)
        q = q.where(ctx.dept_where(WorkOrder.department_id))
        return db.execute(q).scalar_one()

    if ctx.has("wo.view"):
        out["my_open_work"] = db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .join(WOAssignment, WOAssignment.work_order_id == WorkOrder.id)
            .where(WOAssignment.user_id == ctx.user.id, WorkOrder.status.in_(OPEN_WO_STATUSES))
        ).scalar_one()
        out["open_work_orders"] = wo_count(WorkOrder.status.in_(OPEN_WO_STATUSES))
        out["open_emergencies"] = wo_count(WorkOrder.status.in_(OPEN_WO_STATUSES), WorkOrder.type == WOType.EMERGENCY)
        out["overdue_work_orders"] = wo_count(WorkOrder.status.in_(OPEN_WO_STATUSES), WorkOrder.due_date < today)
        out["awaiting_approval"] = wo_count(WorkOrder.status == WOStatus.AWAITING_APPROVAL)
        out["awaiting_review"] = wo_count(WorkOrder.status == WOStatus.AWAITING_REVIEW)
        out["new_requests"] = db.execute(
            select(func.count())
            .select_from(WorkRequest)
            .where(WorkRequest.plant_id == ctx.plant_id, WorkRequest.status == RequestStatus.SUBMITTED)
        ).scalar_one()
    if ctx.has("pm.view"):
        out["pm_pending_approvals"] = db.execute(
            select(func.count())
            .select_from(PMOccurrence)
            .where(
                PMOccurrence.plant_id == ctx.plant_id,
                PMOccurrence.status.in_([OccurrenceStatus.DEFERRAL_REQUESTED, OccurrenceStatus.CANCELLATION_REQUESTED]),
            )
        ).scalar_one()
    if ctx.has("lube.view"):
        out["lube_overdue"] = db.execute(
            select(func.count())
            .select_from(LubeTask)
            .where(LubeTask.plant_id == ctx.plant_id, LubeTask.status == LubeTaskStatus.PENDING, LubeTask.due_date < today)
        ).scalar_one()
    if ctx.has("pdm.view"):
        rows = db.execute(
            select(ConditionAlert.severity, func.count())
            .where(ConditionAlert.plant_id == ctx.plant_id, ConditionAlert.status != AlertStatus.RESOLVED)
            .group_by(ConditionAlert.severity)
        ).all()
        d = {s.value: n for s, n in rows}
        out["open_alerts"] = {"critical": d.get(ConditionStatus.CRITICAL.value, 0), "warning": d.get(ConditionStatus.WARNING.value, 0)}
    return out
