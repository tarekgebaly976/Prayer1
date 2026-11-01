import uuid
from datetime import datetime, time

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import EmailStr, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, get_ctx, require
from app.api.pagination import PageQ, paginate
from app.core.db import get_db
from app.core.security import hash_password, hash_token, new_token, validate_password_strength
from app.models.enums import DepartmentType, FailureCodeKind
from app.models.identity import Membership, Role, RolePermission, User, UserSession
from app.models.system import AuditLog
from app.models.tenancy import Department, IntegrationToken, NumberSequence, Plant
from app.models.workorders import WOStatusTransition
from app.schemas.common import ORM, In
from app.services import failure_modes as fm
from app.services import user_import
from app.services.common import audit, reset_role, role_permissions, utcnow
from app.services.plants import create_plant
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
def update_plant(body: PlantUpdate, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> Plant:
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


# ---------- daily summary e-mail (administrators only) ----------
class DailySummaryCfg(In):
    enabled: bool
    send_time: time  # plant-local, e.g. "06:30"
    # Frequency: ISO weekdays to send on (1 = Monday .. 7 = Sunday). All 7 = daily, one day = weekly. Omitted = unchanged.
    days: list[int] | None = Field(None, min_length=1, max_length=7)


@router.get("/daily-summary")
def get_daily_summary(ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> dict:
    from app.core.config import get_settings
    from app.services import daily_summary

    people = daily_summary.recipients(db, ctx.plant)
    return {
        "enabled": ctx.plant.daily_summary_enabled,
        "send_time": ctx.plant.daily_summary_time.strftime("%H:%M"),
        "days": daily_summary.send_days(ctx.plant),
        "working_days": ctx.plant.working_days,
        "timezone": ctx.plant.timezone,
        "recipients": [{"user_id": u.id, "full_name": u.full_name, "email": u.email, "department_ids": d} for u, d in people],
        "email_configured": get_settings().email_enabled,
        "suppressed": daily_summary.suppressed_reason(),
    }


@router.put("/daily-summary")
def set_daily_summary(
    body: DailySummaryCfg, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")
) -> dict:
    if body.days is not None:
        if any(d < 1 or d > 7 for d in body.days):
            raise HTTPException(422, "Days are ISO weekdays 1 (Monday) to 7 (Sunday)")
        ctx.plant.daily_summary_days = sorted(set(body.days))
    ctx.plant.daily_summary_enabled = body.enabled
    ctx.plant.daily_summary_time = body.send_time.replace(second=0, microsecond=0, tzinfo=None)
    audit(
        db,
        "daily_summary.update",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="plant",
        entity_id=ctx.plant_id,
        data={
            "enabled": body.enabled,
            "send_time": ctx.plant.daily_summary_time.strftime("%H:%M"),
            "days": ctx.plant.daily_summary_days,
        },
    )
    db.flush()
    return get_daily_summary(ctx, db)


@router.get("/daily-summary/preview")
def preview_daily_summary(
    user_id: uuid.UUID | None = None, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")
) -> dict:
    """What the chosen member (default: yourself) would receive today; nothing is sent."""
    from app.services import daily_summary
    from app.services.common import plant_today

    m, user = _member(db, ctx, user_id) if user_id else (None, ctx.user)
    dept_ids = m.department_ids if m is not None else ctx.department_ids
    stats = daily_summary.collect(db, ctx.plant, plant_today(ctx.plant))
    subject, body = daily_summary.compose(db, ctx.plant, stats, user, dept_ids)
    return {"subject": subject, "body": body}


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
def list_departments(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function")) -> list[Department]:
    return list(db.execute(select(Department).where(Department.plant_id == ctx.plant_id).order_by(Department.code)).scalars())


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(
    body: DepartmentIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")
) -> Department:
    d = Department(plant_id=ctx.plant_id, **body.model_dump())
    db.add(d)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Department code already exists") from e
    audit(db, "department.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="department", entity_id=d.id)
    return d


class DepartmentUpdate(In):
    code: str | None = Field(None, min_length=1, max_length=32)
    name: str | None = Field(None, min_length=1, max_length=200)
    name_ar: str | None = None
    type: DepartmentType | None = None
    is_active: bool | None = None


@router.patch("/departments/{dept_id}", response_model=DepartmentOut)
def update_department(
    dept_id: uuid.UUID, body: DepartmentUpdate, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")
) -> Department:
    """Rename a department (code, name) or retire it. Equipment and history keep pointing to it."""
    from app.models.assets import Asset

    d = db.get(Department, dept_id)
    if d is None or d.plant_id != ctx.plant_id:
        raise HTTPException(404, "Department not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_active") is False:
        left = db.execute(
            select(func.count()).select_from(Asset).where(Asset.department_id == d.id, Asset.is_active.is_(True))
        ).scalar_one()
        if left:
            raise HTTPException(409, f"{left} active equipment still belong to {d.code}: move them first")
    for k, v in data.items():
        setattr(d, k, v)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Department code already exists") from e
    audit(db, "department.update", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="department", entity_id=d.id, data=data)
    return d


class MoveAssetsIn(In):
    # Production lines or units; everything below them moves too.
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    to_department_id: uuid.UUID
    # For units: put them under this production line of the target department. Blank = each unit becomes a line.
    parent_id: uuid.UUID | None = None
    apply: bool = False


@router.post("/departments/move-assets")
def move_assets(body: MoveAssetsIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> dict:
    """Move production lines or units (with every level below them) to another department, together with their work
    orders, so lists, KPIs and department access follow the equipment. A unit either becomes a production line of the
    target department or goes under a chosen line there. apply=false only counts."""
    from sqlalchemy import update

    from app.models.assets import Asset
    from app.models.enums import AssetLevel
    from app.models.pm import PMPlan
    from app.models.workorders import WorkOrder
    from app.services.assets import move_asset

    target = db.get(Department, body.to_department_id)
    if target is None or target.plant_id != ctx.plant_id:
        raise HTTPException(404, "Department not found")
    parent = None
    if body.parent_id:
        parent = db.get(Asset, body.parent_id)
        if (
            parent is None
            or parent.plant_id != ctx.plant_id
            or parent.department_id != target.id
            or parent.level != AssetLevel.PRODUCTION_LINE
        ):
            raise HTTPException(422, f"The new parent must be a production line of {target.code}")
    picked = []
    for aid in dict.fromkeys(body.asset_ids):
        a = db.get(Asset, aid)
        if a is None or a.plant_id != ctx.plant_id:
            raise HTTPException(404, "Asset not found")
        if a.level not in (AssetLevel.PRODUCTION_LINE, AssetLevel.UNIT):
            raise HTTPException(422, f"{a.code} is a {a.level.value.replace('_', ' ')}: pick its unit or production line")
        if parent is not None and parent.path.startswith(a.path):
            raise HTTPException(422, f"{a.code} cannot go under its own child {parent.code}")
        picked.append(a)
    # A unit picked together with its own line moves with the line.
    picked = [a for a in picked if not any(o is not a and a.path.startswith(o.path) for o in picked)]
    ids: list[uuid.UUID] = []
    plan: list[dict] = []
    for a in picked:
        ids += svc_subtree(db, a)
        if a.level == AssetLevel.PRODUCTION_LINE:
            becomes = "line"
        else:
            becomes = f"under {parent.code}" if parent is not None else "line"
        plan.append({"code": a.code, "name": a.name, "becomes": becomes})
    wos = db.execute(select(func.count()).select_from(WorkOrder).where(WorkOrder.asset_id.in_(ids))).scalar_one() if ids else 0
    plans = db.execute(select(func.count()).select_from(PMPlan).where(PMPlan.asset_id.in_(ids))).scalar_one() if ids else 0
    out = {
        "lines": [a.code for a in picked],
        "moves": plan,
        "to": target.code,
        "assets": len(ids),
        "work_orders": wos,
        "pm_plans": plans,
        "applied": False,
    }
    if body.apply and ids:
        db.execute(update(Asset).where(Asset.id.in_(ids)).values(department_id=target.id).execution_options(synchronize_session=False))
        db.execute(
            update(WorkOrder)
            .where(WorkOrder.asset_id.in_(ids))
            .values(department_id=target.id)
            .execution_options(synchronize_session=False)
        )
        for a in picked:
            a.department_id = target.id
            if a.level == AssetLevel.UNIT:
                if parent is None:
                    a.level = AssetLevel.PRODUCTION_LINE
                    move_asset(db, a, None)
                else:
                    move_asset(db, a, parent.id)
        if not target.is_active:
            target.is_active = True
        db.flush()
        out["applied"] = True
        audit(
            db,
            "department.move_assets",
            user_id=ctx.user.id,
            plant_id=ctx.plant_id,
            entity_type="department",
            entity_id=target.id,
            data=out,
        )
    return out


def svc_subtree(db: Session, asset) -> list[uuid.UUID]:
    from app.services.assets import subtree_ids

    return subtree_ids(db, asset)


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
    department_ids: list[uuid.UUID] = []
    is_active: bool
    daily_summary: bool = False


class UserCreate(In):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str
    role: str
    department_id: uuid.UUID | None = None
    department_ids: list[uuid.UUID] | None = None  # several areas; the first is the main one (overrides department_id)
    employee_no: str | None = None
    trade: str | None = None
    hourly_rate: float | None = Field(None, ge=0)
    locale: str = "en"


class MembershipUpdate(In):
    email: EmailStr | None = None
    full_name: str | None = Field(None, min_length=2, max_length=200)
    employee_no: str | None = None
    role: str | None = None
    department_id: uuid.UUID | None = None
    department_ids: list[uuid.UUID] | None = None
    is_active: bool | None = None
    trade: str | None = None
    hourly_rate: float | None = Field(None, ge=0)
    daily_summary: bool | None = None  # receives the daily summary e-mail


def _org_roles(ctx: Ctx):  # noqa: ANN202 - SQL condition
    """Roles this organization may use: the built-in ones and its own custom roles."""
    return or_(Role.organization_id.is_(None), Role.organization_id == ctx.user.organization_id)


def _role(db: Session, code: str, ctx: Ctx) -> Role:
    role = db.execute(select(Role).where(Role.code == code, _org_roles(ctx))).scalar_one_or_none()
    if role is None:
        raise HTTPException(422, f"Unknown role {code}")
    return role


@router.get("/users", response_model=list[MemberOut])
def list_users(ctx: Ctx = Depends(require("wo.view")), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.plant_id == ctx.plant_id)
        .order_by(User.full_name)
    ).all()
    return [_member_out(m, u) for m, u in rows]


def _member_out(m: Membership, u: User) -> dict:
    return {
        "user": u,
        "role_code": m.role.code,
        "department_id": m.department_id,
        "department_ids": m.department_ids,
        "is_active": m.is_active and u.is_active,
        "daily_summary": m.daily_summary,
    }


def _dept_list(db: Session, ctx: Ctx, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    for d in ids:
        _check_dept(db, ctx, d)
    return list(dict.fromkeys(ids))


@router.post("/users", response_model=MemberOut, status_code=201)
def create_user(body: UserCreate, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")) -> dict:
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    role = _role(db, body.role, ctx)
    if role.code == "system_admin" and not ctx.user.is_system_admin:
        raise HTTPException(403, "Only system administrators can grant the system administrator role")
    depts = _dept_list(db, ctx, body.department_ids if body.department_ids is not None else [d for d in [body.department_id] if d])
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
    elif not db.execute(select(Membership.id).where(Membership.user_id == user.id, Membership.is_active.is_(True))).first():
        # Re-adding someone removed earlier: the form's details and password replace the old ones (history is kept).
        user.full_name, user.password_hash, user.password_changed_at = body.full_name, hash_password(body.password), utcnow()
        user.employee_no, user.trade, user.hourly_rate, user.is_active = body.employee_no, body.trade, body.hourly_rate, True
    m = Membership(user_id=user.id, plant_id=ctx.plant_id, role_id=role.id)
    m.set_departments(depts)
    db.add(m)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "User is already a member of this plant") from e
    audit(db, "user.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="user", entity_id=user.id, data={"role": role.code})
    return _member_out(m, user)


def _check_dept(db: Session, ctx: Ctx, dept_id: uuid.UUID | None) -> None:
    if dept_id is not None:
        d = db.get(Department, dept_id)
        if d is None or d.plant_id != ctx.plant_id:
            raise HTTPException(422, "Department not in this plant")


@router.get("/users/import/template.xlsx")
def users_template(ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")) -> Response:
    """The plant's current users in the import layout: change rows or add new ones, then upload."""
    return Response(
        user_import.template_xlsx(db, ctx.plant),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="users.xlsx"'},
    )


@router.post("/users/import")
def users_import(
    apply: bool = False,
    file: UploadFile = File(...),
    ctx: Ctx = Depends(require("user.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    """apply=false: preview. apply=true: add and update everyone, or nothing if any row is wrong. Temporary passwords of
    new people are in the answer, once."""
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5 MB)")
    try:
        checked = user_import.check(db, ctx.plant, file.filename or "", content, ctx.user.is_system_admin)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if not apply:
        return checked["preview"]
    try:
        return {**checked["preview"], **user_import.commit(db, ctx.plant, checked, ctx.user.id)}
    except ValueError as e:
        raise HTTPException(422, {"message": str(e), **checked["preview"]}) from e


@router.patch("/users/{user_id}", response_model=MemberOut)
def update_membership(
    user_id: uuid.UUID, body: MembershipUpdate, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")
) -> dict:
    m = db.execute(select(Membership).where(Membership.user_id == user_id, Membership.plant_id == ctx.plant_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Member not found")
    data = body.model_dump(exclude_unset=True)
    if "role" in data:
        role = _role(db, data["role"], ctx)
        if role.code == "system_admin" and not ctx.user.is_system_admin:
            raise HTTPException(403, "Only system administrators can grant the system administrator role")
        m.role_id = role.id
    if data.get("department_ids") is not None:
        m.set_departments(_dept_list(db, ctx, data["department_ids"]))
    elif "department_id" in data:
        m.set_departments(_dept_list(db, ctx, [d for d in [data["department_id"]] if d]))
    user = db.get(User, user_id)
    assert user is not None
    if data.get("email") and data["email"].lower() != user.email:
        if db.execute(select(User.id).where(User.email == data["email"].lower())).first():
            raise HTTPException(409, "Another user already has this e-mail")
        user.email = data["email"].lower()
    if data.get("full_name"):
        user.full_name = data["full_name"]
    if "employee_no" in data:
        user.employee_no = data["employee_no"]
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
    if data.get("daily_summary") is not None:
        m.daily_summary = data["daily_summary"]
    db.flush()
    db.refresh(m)
    audit(db, "user.update", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="user", entity_id=user_id, data=data)
    return _member_out(m, user)


class PasswordResetIn(In):
    password: str


def _member(db: Session, ctx: Ctx, user_id: uuid.UUID) -> tuple[Membership, User]:
    m = db.execute(select(Membership).where(Membership.user_id == user_id, Membership.plant_id == ctx.plant_id)).scalar_one_or_none()
    user = db.get(User, user_id)
    if m is None or user is None:
        raise HTTPException(404, "Member not found")
    if user.is_system_admin and not ctx.user.is_system_admin:
        raise HTTPException(403, "Only system administrators can change a system administrator")
    return m, user


def _revoke_sessions(db: Session, user_id: uuid.UUID) -> None:
    for s in db.execute(select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))).scalars():
        s.revoked_at = utcnow()


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_user_password(
    user_id: uuid.UUID, body: PasswordResetIn, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")
) -> None:
    """Administrator sets a new temporary password (the user should change it after signing in)."""
    _, user = _member(db, ctx, user_id)
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    user.password_hash, user.password_changed_at = hash_password(body.password), utcnow()
    user.failed_login_count, user.locked_until = 0, None
    _revoke_sessions(db, user.id)
    audit(db, "user.password_reset", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="user", entity_id=user.id)


@router.delete("/users/{user_id}", status_code=204)
def remove_user(user_id: uuid.UUID, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")) -> None:
    """Remove a user from this plant. Their name stays on past work orders, labour and audit records; adding the same
    e-mail again later restores access."""
    if user_id == ctx.user.id:
        raise HTTPException(409, "You cannot remove yourself")
    m, user = _member(db, ctx, user_id)
    db.delete(m)
    db.flush()
    if not db.execute(select(Membership.id).where(Membership.user_id == user.id, Membership.is_active.is_(True))).first():
        _revoke_sessions(db, user.id)
    audit(db, "user.remove", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="user", entity_id=user.id, data={"email": user.email})


@router.get("/trades")
def list_trades(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function")) -> list[str]:
    """Trades to offer: the default list plus any trade already used in this plant (people or job plans)."""
    from app.core.trades import DEFAULT_TRADES
    from app.models.pm import JobPlan

    used = set(
        db.execute(
            select(User.trade)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.plant_id == ctx.plant_id, User.trade.is_not(None))
        ).scalars()
    )
    used |= set(db.execute(select(JobPlan.trade).where(JobPlan.plant_id == ctx.plant_id, JobPlan.trade.is_not(None))).scalars())
    out = list(DEFAULT_TRADES)
    seen = {t.casefold() for t in out}
    for t in sorted(x.strip() for x in used if x and x.strip()):
        if t.casefold() not in seen:
            seen.add(t.casefold())
            out.append(t)
    return out


@router.get("/roles")
def list_roles(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    return [{"code": r.code, "name": r.name} for r in db.execute(select(Role).where(_org_roles(ctx)).order_by(Role.name)).scalars()]


# ---------- roles & permissions (what each role may do) ----------
# The matrix is shared by every plant of the organization. Only a System Administrator edits it; the System
# Administrator role itself is not editable, so the administrator can never lock themselves out.
LOCKED_ROLES = {"system_admin"}


def _sysadmin(ctx: Ctx, what: str) -> None:
    if not ctx.user.is_system_admin:
        raise HTTPException(403, f"Only a System Administrator can {what}")


def _editable_role(db: Session, code: str, ctx: Ctx) -> Role:
    _sysadmin(ctx, "change roles")
    role = _role(db, code, ctx)
    if role.code in LOCKED_ROLES:
        raise HTTPException(409, "The System Administrator role always has every permission and cannot be changed")
    return role


@router.get("/permissions")
def list_permissions(ctx: Ctx = Depends(require("user.manage"))) -> list[dict]:
    from app.core.permissions import PERMISSIONS

    return [{"code": c, "description": d, "group": c.split(".")[0]} for c, d in PERMISSIONS.items()]


@router.get("/roles/matrix")
def roles_matrix(ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    from app.core.permissions import ROLES

    roles = list(db.execute(select(Role).where(_org_roles(ctx)).order_by(Role.name)).scalars())
    perms: dict[uuid.UUID, list[str]] = {r.id: [] for r in roles}
    for rid, code in db.execute(select(RolePermission.role_id, RolePermission.permission_code).where(RolePermission.role_id.in_(perms))):
        perms[rid].append(code)
    members: dict[uuid.UUID, int] = {
        rid: n
        for rid, n in db.execute(
            select(Membership.role_id, func.count())
            .join(Plant, Plant.id == Membership.plant_id)
            .where(Plant.organization_id == ctx.user.organization_id, Membership.is_active.is_(True))
            .group_by(Membership.role_id)
        )
    }
    return [
        {
            "code": r.code,
            "name": r.name,
            "builtin": r.code in ROLES,
            "customized": r.customized,
            "locked": r.code in LOCKED_ROLES,
            "members": members.get(r.id, 0),
            "permissions": sorted(perms[r.id]),
        }
        for r in roles
    ]


class RolePermissionsIn(In):
    permissions: list[str]


@router.put("/roles/{code}/permissions")
def set_role_permissions(
    code: str, body: RolePermissionsIn, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")
) -> dict:
    from app.core.permissions import PERMISSIONS, ROLES

    role = _editable_role(db, code, ctx)
    wanted = set(body.permissions)
    unknown = wanted - set(PERMISSIONS)
    if unknown:
        raise HTTPException(422, f"Unknown permission(s): {', '.join(sorted(unknown))}")
    before = role_permissions(db, role.id)
    for p in wanted - before:
        db.add(RolePermission(role_id=role.id, permission_code=p))
    for p in before - wanted:
        db.execute(delete(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_code == p))
    if role.code in ROLES:
        role.customized = True
    audit(
        db,
        "role.permissions",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="role",
        entity_id=role.id,
        data={"role": role.code, "added": sorted(wanted - before), "removed": sorted(before - wanted)},
    )
    return {"code": role.code, "permissions": sorted(wanted)}


class RoleCreate(In):
    name: str = Field(min_length=2, max_length=120)
    copy_from: str | None = None  # start with the permissions of this role


@router.post("/roles", status_code=201)
def create_role(body: RoleCreate, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")) -> dict:
    _sysadmin(ctx, "create roles")
    name = body.name.strip()
    if db.execute(select(Role.id).where(_org_roles(ctx), func.lower(Role.name) == name.lower())).first():
        raise HTTPException(409, f"A role named {name} already exists")
    perms: set[str] = set()
    if body.copy_from:
        src = _role(db, body.copy_from, ctx)
        perms = role_permissions(db, src.id)
    role = Role(code=f"c_{uuid.uuid4().hex[:12]}", name=name, organization_id=ctx.user.organization_id, customized=True)
    db.add(role)
    db.flush()
    for p in perms:
        db.add(RolePermission(role_id=role.id, permission_code=p))
    audit(
        db,
        "role.create",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="role",
        entity_id=role.id,
        data={"name": name, "copy_from": body.copy_from},
    )
    return {"code": role.code, "name": role.name, "permissions": sorted(perms)}


class RoleRename(In):
    name: str = Field(min_length=2, max_length=120)


@router.patch("/roles/{code}")
def rename_role(
    code: str, body: RoleRename, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")
) -> dict:
    from app.core.permissions import ROLES

    role = _editable_role(db, code, ctx)
    name = body.name.strip()
    if db.execute(select(Role.id).where(_org_roles(ctx), func.lower(Role.name) == name.lower(), Role.id != role.id)).first():
        raise HTTPException(409, f"A role named {name} already exists")
    role.name = name
    if role.code in ROLES:
        role.customized = True
    audit(db, "role.rename", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="role", entity_id=role.id, data={"name": name})
    return {"code": role.code, "name": role.name}


@router.post("/roles/{code}/reset")
def reset_builtin_role(code: str, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")) -> dict:
    from app.core.permissions import ROLES

    role = _editable_role(db, code, ctx)
    if role.code not in ROLES:
        raise HTTPException(409, "Only built-in roles have a default to go back to")
    reset_role(db, role)
    audit(db, "role.reset", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="role", entity_id=role.id, data={"role": role.code})
    return {"code": role.code, "permissions": sorted(role_permissions(db, role.id))}


@router.delete("/roles/{code}", status_code=204)
def delete_role(code: str, ctx: Ctx = Depends(require("user.manage")), db: Session = Depends(get_db, scope="function")) -> None:
    from app.core.permissions import ROLES

    role = _editable_role(db, code, ctx)
    if role.code in ROLES:
        raise HTTPException(409, "Built-in roles cannot be deleted; take permissions away instead")
    used = db.execute(select(func.count()).select_from(Membership).where(Membership.role_id == role.id)).scalar_one()
    if used:
        raise HTTPException(409, f"{used} user(s) still have this role; give them another role first")
    audit(db, "role.delete", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="role", entity_id=role.id, data={"name": role.name})
    db.delete(role)


# ---------- plants (a new, empty plant / mill) ----------
class PlantCreate(In):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=200)
    timezone: str = "Asia/Riyadh"
    currency: str = Field("SAR", min_length=3, max_length=3)
    departments: str = Field("general", pattern="^(general|paper|none)$")


@router.get("/plants")
def list_plants(ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    rows = db.execute(select(Plant).where(Plant.organization_id == ctx.user.organization_id).order_by(Plant.code)).scalars()
    return [
        {"id": p.id, "code": p.code, "name": p.name, "timezone": p.timezone, "currency": p.currency, "is_active": p.is_active} for p in rows
    ]


@router.post("/plants", status_code=201)
def new_plant(body: PlantCreate, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> dict:
    """An empty plant in the same organization: starting departments and the default workflow, nothing else.
    System Administrators see it at once in the plant switcher; other users are added from Admin → Users there."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    _sysadmin(ctx, "create plants")
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise HTTPException(422, f"Unknown time zone {body.timezone}") from e
    plant = create_plant(db, ctx.user.organization_id, body.code, body.name, body.timezone, body.currency, body.departments)
    audit(
        db,
        "plant.create",
        user_id=ctx.user.id,
        plant_id=plant.id,
        entity_type="plant",
        entity_id=plant.id,
        data={"code": plant.code, "name": plant.name, "departments": body.departments},
    )
    return {"id": plant.id, "code": plant.code, "name": plant.name}


# ---------- failure codes ----------
class FailureCodeIn(In):
    kind: FailureCodeKind
    code: str = Field(min_length=1, max_length=32)
    description: str
    description_ar: str | None = None
    equipment_type: str | None = Field(None, max_length=60)
    category: str | None = Field(None, max_length=30)


class FailureCodeOut(ORM):
    id: uuid.UUID
    kind: FailureCodeKind
    code: str
    description: str
    description_ar: str | None
    equipment_type: str | None
    category: str | None
    suggested: bool = False  # matches the equipment type of the asset asked about


@router.get("/failure-codes", response_model=list[FailureCodeOut])
def list_failure_codes(
    asset_id: uuid.UUID | None = None, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function")
) -> list:
    """With `asset_id`, the failure modes of that equipment's type come first, marked `suggested`."""
    from app.models.assets import Asset, FailureCode

    codes = db.execute(
        select(FailureCode)
        .where(FailureCode.plant_id == ctx.plant_id, FailureCode.is_active.is_(True))
        .order_by(FailureCode.kind, FailureCode.equipment_type.nulls_first(), FailureCode.code)
    ).scalars()
    out = [FailureCodeOut.model_validate(c) for c in codes]
    asset = db.get(Asset, asset_id) if asset_id else None
    etype = fm.asset_type(db, asset) if asset is not None and asset.plant_id == ctx.plant_id else None
    if etype:
        for c in out:
            c.suggested = (c.equipment_type or "").casefold() == etype.casefold()
        out.sort(key=lambda c: not c.suggested)  # stable: keeps kind/type/code order within each group
    return out


@router.get("/failure-codes/export.xlsx")
def export_failure_codes(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function")) -> Response:
    """The catalogue in the import layout: add or change rows and upload it again."""
    return Response(
        fm.export_xlsx(db, ctx.plant),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="failure_codes.xlsx"'},
    )


@router.post("/failure-codes/import")
def import_failure_codes(
    apply: bool = False,
    file: UploadFile = File(...),
    ctx: Ctx = Depends(require("plant.admin")),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    """apply=false: preview. apply=true: add new codes and update existing ones, or nothing if any row has an error."""
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5 MB)")
    try:
        checked = fm.check(db, ctx.plant, file.filename or "", content)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if not apply:
        return checked["preview"]
    try:
        return {**checked["preview"], **fm.commit(db, ctx.plant, checked, ctx.user.id)}
    except ValueError as e:
        raise HTTPException(422, {"message": str(e), **checked["preview"]}) from e


@router.post("/failure-codes", response_model=FailureCodeOut, status_code=201)
def create_failure_code(body: FailureCodeIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")):
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
def list_transitions(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function")) -> list:
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
    tid: uuid.UUID, body: TransitionUpdate, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")
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
def set_numbering(body: SequenceIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> dict:
    seq = db.execute(
        select(NumberSequence)
        .where(NumberSequence.plant_id == ctx.plant_id, NumberSequence.key == body.key)
        .with_for_update(key_share=True)
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
def create_token(body: TokenIn, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> dict:
    token = "cmmsgw_" + new_token(32)
    t = IntegrationToken(plant_id=ctx.plant_id, name=body.name, token_hash=hash_token(token), notes=body.notes, created_by_id=ctx.user.id)
    db.add(t)
    db.flush()
    audit(db, "integration_token.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="integration_token", entity_id=t.id)
    return {"id": t.id, "token": token, "note": "Store this token now; it is not retrievable later."}


@router.get("/integration-tokens")
def list_tokens(ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    return [
        {"id": t.id, "name": t.name, "scopes": t.scopes, "revoked_at": t.revoked_at, "last_used_at": t.last_used_at}
        for t in db.execute(select(IntegrationToken).where(IntegrationToken.plant_id == ctx.plant_id)).scalars()
    ]


@router.delete("/integration-tokens/{tid}", status_code=204)
def revoke_token(tid: uuid.UUID, ctx: Ctx = Depends(require("plant.admin")), db: Session = Depends(get_db, scope="function")) -> None:
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
    db: Session = Depends(get_db, scope="function"),
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
