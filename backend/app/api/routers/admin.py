import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, get_ctx, require
from app.api.pagination import PageQ, paginate
from app.core.db import get_db
from app.core.security import hash_password, hash_token, new_token, validate_password_strength
from app.models.enums import DepartmentType, FailureCodeKind
from app.models.identity import Membership, Role, User, UserSession
from app.models.system import AuditLog
from app.models.tenancy import Department, IntegrationToken, NumberSequence, Plant
from app.models.workorders import WOStatusTransition
from app.schemas.common import ORM, In
from app.services.common import audit, utcnow
from app.services.workflow import ensure_default_transitions

router = APIRouter(tags=["admin"])


class PlantOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    timezone: str
    currency: str
    default_locale: str
    allow_negative_stock: bool
    working_days: list[int]
    working_hours_per_day: float
    settings: dict


class PlantUpdate(In):
    name: str | None = None
    timezone: str | None = None
    currency: str | None = Field(None, min_length=3, max_length=3)
    default_locale: str | None = None
    allow_negative_stock: bool | None = None
    working_days: list[int] | None = None
    working_hours_per_day: float | None = Field(None, gt=0, le=24)
    settings: dict | None = None


@router.get("/plant", response_model=PlantOut)
def get_plant(ctx: Ctx = Depends(get_ctx)) -> Plant:
    return ctx.plant


@router.patch("/plant", response_model=PlantOut)
def update_plant(body: PlantUpdate, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)) -> Plant:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    data = body.model_dump(exclude_unset=True)
    if "timezone" in data:
        try:
            ZoneInfo(data["timezone"])
        except ZoneInfoNotFoundError as e:
            raise HTTPException(422, "Unknown timezone") from e
    for k, v in data.items():
        setattr(ctx.plant, k, v)
    audit(db, "plant.update", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="plant", entity_id=ctx.plant_id, data=data)
    return ctx.plant


class DepartmentIn(In):
    code: str = Field(min_length=1, max_length=32)
    name: str
    name_ar: str | None = None
    type: DepartmentType


class DepartmentOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    name_ar: str | None
    type: DepartmentType
    is_active: bool


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)) -> list[Department]:
    return list(db.execute(select(Department).where(Department.plant_id == ctx.plant_id).order_by(Department.code)).scalars())


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(body: DepartmentIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)) -> Department:
    d = Department(plant_id=ctx.plant_id, **body.model_dump())
    db.add(d)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Department code already exists") from e
    audit(db, "department.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="department", entity_id=d.id)
    return d


# ---------- users & memberships ----------
class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    employee_no: str | None
    is_active: bool
    trade: str | None
    hourly_rate: float | None
    locale: str


class MemberOut(ORM):
    user: UserOut
    role_code: str
    department_id: uuid.UUID | None
    is_active: bool


class UserCreate(In):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str
    role: str
    department_id: uuid.UUID | None = None
    employee_no: str | None = None
    trade: str | None = None
    hourly_rate: float | None = Field(None, ge=0)
    locale: str = "en"


class MembershipUpdate(In):
    role: str | None = None
    department_id: uuid.UUID | None = None
    is_active: bool | None = None
    trade: str | None = None
    hourly_rate: float | None = Field(None, ge=0)


def _role(db: Session, code: str) -> Role:
    role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
    if role is None:
        raise HTTPException(422, f"Unknown role {code}")
    return role


@router.get("/users", response_model=list[MemberOut])
def list_users(ctx: Ctx = Depends(require("wo.view")), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.plant_id == ctx.plant_id)
        .order_by(User.full_name)
    ).all()
    return [
        {"user": u, "role_code": m.role.code, "department_id": m.department_id, "is_active": m.is_active and u.is_active} for m, u in rows
    ]


@router.post("/users", response_model=MemberOut, status_code=201)
def create_user(body: UserCreate, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db)) -> dict:
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    role = _role(db, body.role)
    if role.code == "system_admin" and not ctx.user.is_system_admin:
        raise HTTPException(403, "Only system administrators can grant the system administrator role")
    _check_dept(db, ctx, body.department_id)
    email = body.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            organization_id=ctx.plant.organization_id,
            email=email,
            full_name=body.full_name,
            password_hash=hash_password(body.password),
            employee_no=body.employee_no,
            trade=body.trade,
            hourly_rate=body.hourly_rate,
            locale=body.locale,
            password_changed_at=utcnow(),
        )
        db.add(user)
        db.flush()
    elif user.organization_id != ctx.plant.organization_id:
        raise HTTPException(409, "Email belongs to another organization")
    m = Membership(user_id=user.id, plant_id=ctx.plant_id, role_id=role.id, department_id=body.department_id)
    db.add(m)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "User is already a member of this plant") from e
    audit(db, "user.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="user", entity_id=user.id, data={"role": role.code})
    return {"user": user, "role_code": role.code, "department_id": m.department_id, "is_active": True}


def _check_dept(db: Session, ctx: Ctx, dept_id: uuid.UUID | None) -> None:
    if dept_id is not None:
        d = db.get(Department, dept_id)
        if d is None or d.plant_id != ctx.plant_id:
            raise HTTPException(422, "Department not in this plant")


@router.patch("/users/{user_id}", response_model=MemberOut)
def update_membership(
    user_id: uuid.UUID, body: MembershipUpdate, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db)
) -> dict:
    m = db.execute(select(Membership).where(Membership.user_id == user_id, Membership.plant_id == ctx.plant_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Member not found")
    data = body.model_dump(exclude_unset=True)
    if "role" in data:
        role = _role(db, data["role"])
        if role.code == "system_admin" and not ctx.user.is_system_admin:
            raise HTTPException(403, "Only system administrators can grant the system administrator role")
        m.role_id = role.id
    if "department_id" in data:
        _check_dept(db, ctx, data["department_id"])
        m.department_id = data["department_id"]
    user = db.get(User, user_id)
    assert user is not None
    if "trade" in data:
        user.trade = data["trade"]
    if "hourly_rate" in data:
        user.hourly_rate = data["hourly_rate"]
    if data.get("is_active") is False:
        m.is_active = False
        # Revocation: kill live sessions immediately.
        for s in db.execute(select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))).scalars():
            s.revoked_at = utcnow()
    elif data.get("is_active") is True:
        m.is_active = True
    db.flush()
    db.refresh(m)
    audit(db, "user.update", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="user", entity_id=user_id, data=data)
    return {"user": user, "role_code": m.role.code, "department_id": m.department_id, "is_active": m.is_active and user.is_active}


@router.get("/roles")
def list_roles(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)) -> list[dict]:
    return [{"code": r.code, "name": r.name} for r in db.execute(select(Role).order_by(Role.name)).scalars()]


# ---------- failure codes ----------
class FailureCodeIn(In):
    kind: FailureCodeKind
    code: str = Field(min_length=1, max_length=32)
    description: str
    description_ar: str | None = None


class FailureCodeOut(ORM):
    id: uuid.UUID
    kind: FailureCodeKind
    code: str
    description: str
    description_ar: str | None


@router.get("/failure-codes", response_model=list[FailureCodeOut])
def list_failure_codes(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)) -> list:
    from app.models.assets import FailureCode

    return list(
        db.execute(
            select(FailureCode)
            .where(FailureCode.plant_id == ctx.plant_id, FailureCode.is_active.is_(True))
            .order_by(FailureCode.kind, FailureCode.code)
        ).scalars()
    )


@router.post("/failure-codes", response_model=FailureCodeOut, status_code=201)
def create_failure_code(body: FailureCodeIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)):  # type: ignore[no-untyped-def]
    from app.models.assets import FailureCode

    fc = FailureCode(plant_id=ctx.plant_id, **body.model_dump())
    db.add(fc)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Code exists") from e
    return fc


# ---------- workflow transitions ----------
class TransitionOut(ORM):
    id: uuid.UUID
    from_status: str
    to_status: str
    permission: str
    is_active: bool


class TransitionUpdate(In):
    permission: str | None = None
    is_active: bool | None = None


@router.get("/workflow/transitions", response_model=list[TransitionOut])
def list_transitions(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)) -> list:
    ensure_default_transitions(db, ctx.plant_id)
    return list(
        db.execute(
            select(WOStatusTransition)
            .where(WOStatusTransition.plant_id == ctx.plant_id)
            .order_by(WOStatusTransition.from_status, WOStatusTransition.to_status)
        ).scalars()
    )


@router.patch("/workflow/transitions/{tid}", response_model=TransitionOut)
def update_transition(
    tid: uuid.UUID, body: TransitionUpdate, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)
) -> WOStatusTransition:
    from app.core.permissions import PERMISSIONS

    t = db.get(WOStatusTransition, tid)
    if t is None or t.plant_id != ctx.plant_id:
        raise HTTPException(404, "Transition not found")
    if body.permission is not None:
        if body.permission not in PERMISSIONS:
            raise HTTPException(422, "Unknown permission")
        t.permission = body.permission
    if body.is_active is not None:
        t.is_active = body.is_active
    audit(
        db,
        "workflow.update",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="transition",
        entity_id=tid,
        data=body.model_dump(exclude_unset=True),
    )
    return t


# ---------- numbering ----------
class SequenceIn(In):
    key: str = Field(pattern="^(WO|WR|PO)$")
    prefix: str = Field(min_length=1, max_length=32)
    padding: int = Field(6, ge=3, le=10)


@router.put("/numbering")
def set_numbering(body: SequenceIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)) -> dict:
    seq = db.execute(
        select(NumberSequence).where(NumberSequence.plant_id == ctx.plant_id, NumberSequence.key == body.key).with_for_update(key_share=True)
    ).scalar_one_or_none()
    if seq is None:
        seq = NumberSequence(plant_id=ctx.plant_id, key=body.key, prefix=body.prefix, padding=body.padding, next_value=1)
        db.add(seq)
    else:
        seq.prefix, seq.padding = body.prefix, body.padding
    audit(db, "numbering.update", user_id=ctx.user.id, plant_id=ctx.plant_id, data=body.model_dump())
    return {"key": seq.key, "prefix": seq.prefix, "padding": seq.padding, "next_value": seq.next_value}


# ---------- integration tokens (industrial gateway) ----------
class TokenIn(In):
    name: str
    notes: str | None = None


@router.post("/integration-tokens", status_code=201)
def create_token(body: TokenIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)) -> dict:
    token = "cmmsgw_" + new_token(32)
    t = IntegrationToken(plant_id=ctx.plant_id, name=body.name, token_hash=hash_token(token), notes=body.notes, created_by_id=ctx.user.id)
    db.add(t)
    db.flush()
    audit(db, "integration_token.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="integration_token", entity_id=t.id)
    return {"id": t.id, "token": token, "note": "Store this token now; it is not retrievable later."}


@router.get("/integration-tokens")
def list_tokens(ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)) -> list[dict]:
    return [
        {"id": t.id, "name": t.name, "scopes": t.scopes, "revoked_at": t.revoked_at, "last_used_at": t.last_used_at}
        for t in db.execute(select(IntegrationToken).where(IntegrationToken.plant_id == ctx.plant_id)).scalars()
    ]


@router.delete("/integration-tokens/{tid}", status_code=204)
def revoke_token(tid: uuid.UUID, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db)) -> None:
    t = db.get(IntegrationToken, tid)
    if t is None or t.plant_id != ctx.plant_id:
        raise HTTPException(404, "Token not found")
    t.revoked_at = utcnow()
    audit(db, "integration_token.revoke", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="integration_token", entity_id=tid)


# ---------- audit ----------
class AuditOut(ORM):
    id: int
    at: datetime
    user_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: str | None
    data: dict
    ip: str | None


@router.get("/audit-logs")
def audit_logs(
    ctx: Ctx = Depends(require("audit.view")),
    db: Session = Depends(get_db),
    page: PageQ = Depends(),
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = Query(None),
) -> dict:
    q = select(AuditLog).where(AuditLog.plant_id == ctx.plant_id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if action:
        q = q.where(AuditLog.action.startswith(action))
    return paginate(db, q.order_by(AuditLog.id.desc()), page, AuditOut)
