"""Work order status machine. Allowed transitions + required permission are stored per plant
(wo_status_transitions) and editable by administrators; business guards below are not configurable
because they protect safety-critical rules."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.enums import WOStatus as S
from app.models.workorders import WOStatusTransition

DEFAULT_TRANSITIONS: list[tuple[S, S, str]] = [
    (S.TRIAGE, S.AWAITING_APPROVAL, "wo.edit"),
    (S.TRIAGE, S.APPROVED, "wo.approve"),
    (S.TRIAGE, S.IN_PROGRESS, "wo.execute"),  # emergency fast-track only (guarded)
    (S.TRIAGE, S.CANCELLED, "wo.cancel"),
    (S.AWAITING_APPROVAL, S.APPROVED, "wo.approve"),
    (S.AWAITING_APPROVAL, S.TRIAGE, "wo.approve"),  # returned for more information
    (S.AWAITING_APPROVAL, S.CANCELLED, "wo.cancel"),
    (S.APPROVED, S.PLANNED, "wo.plan"),
    (S.APPROVED, S.SCHEDULED, "wo.plan"),
    (S.APPROVED, S.IN_PROGRESS, "wo.execute"),
    (S.APPROVED, S.CANCELLED, "wo.cancel"),
    (S.PLANNED, S.SCHEDULED, "wo.plan"),
    (S.PLANNED, S.CANCELLED, "wo.cancel"),
    (S.SCHEDULED, S.IN_PROGRESS, "wo.execute"),
    (S.SCHEDULED, S.PLANNED, "wo.plan"),
    (S.SCHEDULED, S.CANCELLED, "wo.cancel"),
    (S.IN_PROGRESS, S.ON_HOLD, "wo.execute"),
    (S.IN_PROGRESS, S.AWAITING_REVIEW, "wo.execute"),
    (S.ON_HOLD, S.IN_PROGRESS, "wo.execute"),
    (S.ON_HOLD, S.CANCELLED, "wo.cancel"),
    (S.AWAITING_REVIEW, S.IN_PROGRESS, "wo.review"),  # rework
    (S.AWAITING_REVIEW, S.COMPLETED, "wo.review"),
    (S.COMPLETED, S.CLOSED, "wo.close"),
]


def ensure_default_transitions(db: Session, plant_id: uuid.UUID) -> None:
    for f, t, perm in DEFAULT_TRANSITIONS:
        db.execute(
            pg_insert(WOStatusTransition)
            .values(id=uuid.uuid4(), plant_id=plant_id, from_status=f.value, to_status=t.value, permission=perm)
            .on_conflict_do_nothing(index_elements=["plant_id", "from_status", "to_status"])
        )


def get_transition(db: Session, plant_id: uuid.UUID, from_s: S, to_s: S) -> WOStatusTransition | None:
    q = select(WOStatusTransition).where(
        WOStatusTransition.plant_id == plant_id,
        WOStatusTransition.from_status == from_s.value,
        WOStatusTransition.to_status == to_s.value,
        WOStatusTransition.is_active.is_(True),
    )
    t = db.execute(q).scalar_one_or_none()
    if t is None:
        exists = db.execute(select(WOStatusTransition.id).where(WOStatusTransition.plant_id == plant_id).limit(1)).first()
        if not exists:
            ensure_default_transitions(db, plant_id)
            t = db.execute(q).scalar_one_or_none()
    return t


def allowed_next(db: Session, plant_id: uuid.UUID, from_s: S, permissions: set[str]) -> list[str]:
    get_transition(db, plant_id, from_s, from_s)  # ensures defaults exist
    rows = db.execute(
        select(WOStatusTransition).where(
            WOStatusTransition.plant_id == plant_id, WOStatusTransition.from_status == from_s.value, WOStatusTransition.is_active.is_(True)
        )
    ).scalars()
    return [r.to_status for r in rows if r.permission in permissions]
