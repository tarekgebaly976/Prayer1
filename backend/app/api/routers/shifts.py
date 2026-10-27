import uuid
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.core.db import get_db
from app.core.errors import DomainError
from app.models.enums import HandoverStatus, RosterKind, ShiftKind
from app.models.identity import Membership, User
from app.models.shifts import RosterEntry, ShiftDefinition, ShiftHandover, ShiftPattern, Team, TeamMember
from app.models.tenancy import Department
from app.models.workorders import WorkOrder
from app.schemas.common import ORM, In
from app.services import shifts as svc
from app.services.common import audit

router = APIRouter(prefix="/shifts", tags=["shifts"])


class ShiftIn(In):
    code: str = Field(min_length=1, max_length=8)
    name: str
    kind: ShiftKind
    start_time: time
    end_time: time
    paid_hours: float = Field(8, gt=0, le=16)


class ShiftOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    kind: ShiftKind
    start_time: time
    end_time: time
    paid_hours: float


@router.get("/definitions", response_model=list[ShiftOut])
def list_shifts(ctx: Ctx = Depends(require("shift.view")), db: Session = Depends(get_db, scope="function")) -> list[ShiftDefinition]:
    return list(
        db.execute(select(ShiftDefinition).where(ShiftDefinition.plant_id == ctx.plant_id).order_by(ShiftDefinition.start_time)).scalars()
    )


@router.post("/definitions", response_model=ShiftOut, status_code=201)
def create_shift(
    body: ShiftIn, ctx: Ctx = Depends(require("shift.manage")), db: Session = Depends(get_db, scope="function")
) -> ShiftDefinition:
    s = ShiftDefinition(plant_id=ctx.plant_id, **body.model_dump())
    db.add(s)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Shift code exists") from e
    return s


class PatternIn(In):
    code: str
    name: str
    cycle: list[str] = Field(min_length=1, max_length=56)


@router.get("/patterns")
def list_patterns(ctx: Ctx = Depends(require("shift.view")), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    return [
        {"id": p.id, "code": p.code, "name": p.name, "cycle": p.cycle}
        for p in db.execute(select(ShiftPattern).where(ShiftPattern.plant_id == ctx.plant_id)).scalars()
    ]


@router.post("/patterns", status_code=201)
def create_pattern(body: PatternIn, ctx: Ctx = Depends(require("shift.manage")), db: Session = Depends(get_db, scope="function")) -> dict:
    codes = {s.code for s in db.execute(select(ShiftDefinition).where(ShiftDefinition.plant_id == ctx.plant_id)).scalars()}
    bad = [c for c in body.cycle if c != "OFF" and c not in codes]
    if bad:
        raise HTTPException(422, f"Unknown shift codes in pattern: {sorted(set(bad))}")
    p = ShiftPattern(plant_id=ctx.plant_id, **body.model_dump())
    db.add(p)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Pattern code exists") from e
    return {"id": p.id}


class TeamIn(In):
    code: str
    name: str
    department_id: uuid.UUID | None = None
    supervisor_id: uuid.UUID | None = None
    pattern_id: uuid.UUID | None = None
    pattern_anchor_date: date | None = None
    member_ids: list[uuid.UUID] = Field(default_factory=list)


def _member(db: Session, ctx: Ctx, uid: uuid.UUID) -> None:
    if not db.execute(select(Membership).where(Membership.user_id == uid, Membership.plant_id == ctx.plant_id)).first():
        raise HTTPException(422, "User is not a member of this plant")


@router.get("/teams")
def list_teams(ctx: Ctx = Depends(require("shift.view")), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    out = []
    for t in db.execute(select(Team).where(Team.plant_id == ctx.plant_id).order_by(Team.code)).scalars():
        members = db.execute(
            select(User.id, User.full_name, User.trade).join(TeamMember, TeamMember.user_id == User.id).where(TeamMember.team_id == t.id)
        ).all()
        out.append(
            {
                "id": t.id,
                "code": t.code,
                "name": t.name,
                "department_id": t.department_id,
                "supervisor_id": t.supervisor_id,
                "pattern_id": t.pattern_id,
                "pattern_anchor_date": t.pattern_anchor_date,
                "members": [{"id": i, "name": n, "trade": tr} for i, n, tr in members],
            }
        )
    return out


@router.post("/teams", status_code=201)
def create_team(body: TeamIn, ctx: Ctx = Depends(require("shift.manage")), db: Session = Depends(get_db, scope="function")) -> dict:
    if body.department_id:
        d = db.get(Department, body.department_id)
        if d is None or d.plant_id != ctx.plant_id:
            raise HTTPException(422, "Department not found")
    if body.supervisor_id:
        _member(db, ctx, body.supervisor_id)
    t = Team(plant_id=ctx.plant_id, **body.model_dump(exclude={"member_ids"}))
    db.add(t)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Team code exists") from e
    for uid in body.member_ids:
        _member(db, ctx, uid)
        db.add(TeamMember(team_id=t.id, user_id=uid))
    return {"id": t.id}


class GenerateRosterIn(In):
    start: date
    end: date


@router.post("/teams/{team_id}/generate-roster")
def generate_roster(
    team_id: uuid.UUID, body: GenerateRosterIn, ctx: Ctx = Depends(require("shift.manage")), db: Session = Depends(get_db, scope="function")
) -> dict:
    t = db.get(Team, team_id)
    if t is None or t.plant_id != ctx.plant_id:
        raise HTTPException(404, "Team not found")
    if body.end < body.start:
        raise HTTPException(422, "end before start")
    n = svc.generate_roster(db, ctx.plant, t, body.start, body.end)
    audit(db, "roster.generate", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="team", entity_id=t.id, data={"created": n})
    return {"created": n}


class RosterIn(In):
    user_id: uuid.UUID
    work_date: date
    shift_id: uuid.UUID | None = None
    kind: RosterKind = RosterKind.WORK
    hours: float = Field(8, ge=0, le=24)
    overtime_hours: float = Field(0, ge=0, le=16)
    callout_hours: float = Field(0, ge=0, le=16)
    note: str | None = None
    replace: bool = False


@router.get("/roster")
def roster(
    start: date,
    end: date,
    ctx: Ctx = Depends(require("shift.view")),
    db: Session = Depends(get_db, scope="function"),
    user_id: uuid.UUID | None = None,
) -> list[dict]:
    if (end - start).days > 92:
        raise HTTPException(422, "Range too long (max 92 days)")
    q = (
        select(RosterEntry, User)
        .join(User, User.id == RosterEntry.user_id)
        .where(RosterEntry.plant_id == ctx.plant_id, RosterEntry.work_date >= start, RosterEntry.work_date <= end)
    )
    if user_id:
        q = q.where(RosterEntry.user_id == user_id)
    shifts = {s.id: s.code for s in db.execute(select(ShiftDefinition).where(ShiftDefinition.plant_id == ctx.plant_id)).scalars()}
    return [
        {
            "id": r.id,
            "user_id": u.id,
            "name": u.full_name,
            "trade": u.trade,
            "work_date": r.work_date,
            "shift": shifts.get(r.shift_id) if r.shift_id else None,
            "kind": r.kind,
            "hours": r.hours,
            "overtime_hours": r.overtime_hours,
            "callout_hours": r.callout_hours,
            "note": r.note,
        }
        for r, u in db.execute(q.order_by(RosterEntry.work_date, User.full_name)).all()
    ]


@router.put("/roster")
def set_roster(body: RosterIn, ctx: Ctx = Depends(require("shift.manage")), db: Session = Depends(get_db, scope="function")) -> dict:
    _member(db, ctx, body.user_id)
    if body.kind in (RosterKind.WORK, RosterKind.OVERTIME, RosterKind.CALLOUT) and body.shift_id is None:
        raise HTTPException(422, "A shift is required for working entries")
    if body.shift_id:
        s = db.get(ShiftDefinition, body.shift_id)
        if s is None or s.plant_id != ctx.plant_id:
            raise HTTPException(422, "Shift not found")
    existing = db.execute(
        select(RosterEntry)
        .where(RosterEntry.user_id == body.user_id, RosterEntry.work_date == body.work_date)
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    data = body.model_dump(exclude={"replace"})
    if existing is not None:
        if existing.plant_id != ctx.plant_id:
            raise DomainError("This person is already rostered at another plant on that day", "roster_conflict", 409)
        if not body.replace and (existing.kind != body.kind or existing.shift_id != body.shift_id):
            raise DomainError(
                f"Conflict: already rostered as {existing.kind.value} on {body.work_date}. Resubmit with replace=true.",
                "roster_conflict",
                409,
            )
        for k, v in data.items():
            setattr(existing, k, v)
        existing.source = "manual"
        entry = existing
    else:
        entry = RosterEntry(plant_id=ctx.plant_id, **data)
        db.add(entry)
    db.flush()
    # Leave/absence: warn about existing WO assignments on that day.
    warnings = []
    if body.kind in (RosterKind.LEAVE, RosterKind.ABSENCE):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(ctx.plant.timezone)
        day_start = datetime.combine(body.work_date, time.min, tz)
        for wo in svc.user_assignments_on(db, body.user_id, day_start, day_start + timedelta(days=1)):
            warnings.append(f"Assigned to {wo.number} on this day — reassign")
    audit(db, "roster.set", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="roster", entity_id=entry.id, data=data)
    return {"id": entry.id, "warnings": warnings}


@router.get("/manpower")
def manpower(
    start: date,
    end: date,
    ctx: Ctx = Depends(require("shift.view")),
    db: Session = Depends(get_db, scope="function"),
    department_id: uuid.UUID | None = None,
) -> list[dict]:
    if (end - start).days > 62:
        raise HTTPException(422, "Range too long (max 62 days)")
    return svc.manpower(db, ctx.plant, start, end, department_id)


# ---------------- handovers ----------------
class HandoverIn(In):
    department_id: uuid.UUID
    shift_date: date
    shift_id: uuid.UUID
    incoming_user_id: uuid.UUID | None = None
    summary: str = Field(min_length=5)
    outstanding_breakdowns: str | None = None
    pending_work: str | None = None
    safety_concerns: str | None = None
    equipment_abnormalities: str | None = None
    pending_permits: str | None = None
    critical_risks: str | None = None


class HandoverUpdate(In):
    incoming_user_id: uuid.UUID | None = None
    summary: str | None = None
    outstanding_breakdowns: str | None = None
    pending_work: str | None = None
    safety_concerns: str | None = None
    equipment_abnormalities: str | None = None
    pending_permits: str | None = None
    critical_risks: str | None = None


class HandoverOut(ORM):
    id: uuid.UUID
    department_id: uuid.UUID
    shift_date: date
    shift_id: uuid.UUID
    outgoing_user_id: uuid.UUID
    incoming_user_id: uuid.UUID | None
    summary: str
    outstanding_breakdowns: str | None
    pending_work: str | None
    safety_concerns: str | None
    equipment_abnormalities: str | None
    pending_permits: str | None
    critical_risks: str | None
    open_work_order_ids: list[str]
    status: HandoverStatus
    confirmed_by_id: uuid.UUID | None
    supervisor_comment: str | None
    is_locked: bool


def _ho(db: Session, ctx: Ctx, hid: uuid.UUID) -> ShiftHandover:
    h = db.execute(
        select(ShiftHandover).where(ShiftHandover.id == hid, ShiftHandover.plant_id == ctx.plant_id).with_for_update(key_share=True)
    ).scalar_one_or_none()
    if h is None:
        raise HTTPException(404, "Handover not found")
    return h


@router.get("/handovers", response_model=list[HandoverOut])
def list_handovers(
    ctx: Ctx = Depends(require("shift.view")),
    db: Session = Depends(get_db, scope="function"),
    department_id: uuid.UUID | None = None,
    status: HandoverStatus | None = None,
    limit: int = 50,
) -> list[ShiftHandover]:
    q = select(ShiftHandover).where(ShiftHandover.plant_id == ctx.plant_id)
    if department_id:
        q = q.where(ShiftHandover.department_id == department_id)
    if status:
        q = q.where(ShiftHandover.status == status)
    return list(db.execute(q.order_by(ShiftHandover.shift_date.desc(), ShiftHandover.created_at.desc()).limit(min(limit, 200))).scalars())


@router.get("/handovers/{hid}")
def get_handover(hid: uuid.UUID, ctx: Ctx = Depends(require("shift.view")), db: Session = Depends(get_db, scope="function")) -> dict:
    h = db.get(ShiftHandover, hid)
    if h is None or h.plant_id != ctx.plant_id:
        raise HTTPException(404, "Handover not found")
    live = svc.open_breakdowns(db, ctx.plant, h.department_id)
    snap = [uuid.UUID(x) for x in h.open_work_order_ids]
    snap_wos = db.execute(select(WorkOrder).where(WorkOrder.id.in_(snap))).scalars().all() if snap else []
    return {
        **HandoverOut.model_validate(h).model_dump(mode="json"),
        "open_breakdowns_now": [
            {"id": w.id, "number": w.number, "title": w.title, "status": w.status, "priority": w.priority} for w in live
        ],
        "open_breakdowns_at_submit": [{"id": w.id, "number": w.number, "title": w.title, "status": w.status} for w in snap_wos],
    }


@router.post("/handovers", response_model=HandoverOut, status_code=201)
def create_handover(
    body: HandoverIn, ctx: Ctx = Depends(require("handover.create")), db: Session = Depends(get_db, scope="function")
) -> ShiftHandover:
    d, s = db.get(Department, body.department_id), db.get(ShiftDefinition, body.shift_id)
    if d is None or d.plant_id != ctx.plant_id or s is None or s.plant_id != ctx.plant_id:
        raise HTTPException(422, "Department or shift not found")
    if body.incoming_user_id:
        _member(db, ctx, body.incoming_user_id)
    h = ShiftHandover(plant_id=ctx.plant_id, outgoing_user_id=ctx.user.id, **body.model_dump())
    db.add(h)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "A handover already exists for this department, date and shift") from e
    return h


@router.patch("/handovers/{hid}", response_model=HandoverOut)
def update_handover(
    hid: uuid.UUID, body: HandoverUpdate, ctx: Ctx = Depends(require("handover.create")), db: Session = Depends(get_db, scope="function")
) -> ShiftHandover:
    h = _ho(db, ctx, hid)
    if h.is_locked or h.status != HandoverStatus.DRAFT:
        raise DomainError("Submitted handovers cannot be edited", "locked", 409)
    if h.outgoing_user_id != ctx.user.id:
        raise HTTPException(403, "Only the author can edit a draft handover")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    h.revision += 1
    return h


@router.post("/handovers/{hid}/submit", response_model=HandoverOut)
def submit(
    hid: uuid.UUID, ctx: Ctx = Depends(require("handover.create")), db: Session = Depends(get_db, scope="function")
) -> ShiftHandover:
    return svc.submit_handover(db, ctx.plant, _ho(db, ctx, hid), ctx.user.id)


class ConfirmIn(In):
    comment: str | None = None


@router.post("/handovers/{hid}/confirm", response_model=HandoverOut)
def confirm(
    hid: uuid.UUID, body: ConfirmIn, ctx: Ctx = Depends(require("handover.confirm")), db: Session = Depends(get_db, scope="function")
) -> ShiftHandover:
    return svc.confirm_handover(db, ctx.plant, _ho(db, ctx, hid), ctx.user.id, body.comment)
