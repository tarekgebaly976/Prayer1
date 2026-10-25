import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import Ctx, get_ctx, require
from app.api.pagination import PageQ, paginate
from app.core.db import get_db
from app.models.system import EmailOutbox, JobRun, Notification
from app.schemas.common import ORM
from app.services.common import utcnow

router = APIRouter(tags=["notifications"])


class NotificationOut(ORM):
    id: uuid.UUID
    kind: str
    severity: str
    title: str
    body: str | None
    link: str | None
    created_at: datetime
    read_at: datetime | None


@router.get("/notifications")
def list_notifications(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db), page: PageQ = Depends(), unread: bool = False) -> dict:
    q = select(Notification).where(Notification.user_id == ctx.user.id, Notification.plant_id == ctx.plant_id)
    if unread:
        q = q.where(Notification.read_at.is_(None))
    res = paginate(db, q.order_by(Notification.created_at.desc()), page, NotificationOut)
    res["unread"] = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == ctx.user.id, Notification.plant_id == ctx.plant_id, Notification.read_at.is_(None))
    ).scalar_one()
    return res


@router.post("/notifications/{nid}/read", status_code=204)
def mark_read(nid: uuid.UUID, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)) -> None:
    n = db.get(Notification, nid)
    if n is None or n.user_id != ctx.user.id:
        raise HTTPException(404, "Notification not found")
    n.read_at = n.read_at or utcnow()


@router.post("/notifications/read-all", status_code=204)
def read_all(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == ctx.user.id, Notification.plant_id == ctx.plant_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )


@router.get("/system/jobs")
def job_runs(ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db), limit: int = 100) -> list[dict]:
    return [
        {
            "id": j.id,
            "job": j.job,
            "status": j.status,
            "started_at": j.started_at,
            "finished_at": j.finished_at,
            "details": j.details,
            "error": j.error,
        }
        for j in db.execute(select(JobRun).order_by(JobRun.started_at.desc()).limit(min(limit, 500))).scalars()
    ]


@router.get("/system/email-outbox")
def outbox(ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(EmailOutbox.status, func.count()).group_by(EmailOutbox.status)).all()
    return {s.value: n for s, n in rows}
