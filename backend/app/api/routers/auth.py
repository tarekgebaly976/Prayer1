import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CSRF_COOKIE, SESSION_COOKIE, Principal, client_ip, get_principal
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    validate_password_strength,
    verify_password,
)
from app.models.identity import LoginAttempt, Membership, User, UserSession
from app.models.tenancy import Plant
from app.schemas.common import In
from app.services.common import audit, role_permissions, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])
# Constant-time-ish failure path: verify against a dummy hash when the user does not exist.
_DUMMY_HASH = hash_password("dummy-password-for-timing-1A!")


class LoginIn(In):
    email: str = Field(min_length=3, max_length=254)  # lookup only; format validated at user creation
    password: str = Field(min_length=1, max_length=1024)


class PlantAccess(BaseModel):
    plant_id: uuid.UUID
    plant_code: str
    plant_name: str
    timezone: str
    currency: str
    role: str
    department_id: uuid.UUID | None
    permissions: list[str]


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    locale: str
    is_system_admin: bool
    plants: list[PlantAccess]
    csrf_token: str


def _set_cookies(response: Response, token: str, csrf: str, max_age: int) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain, path="/"
    )
    # Readable by JS so the SPA can echo it in X-CSRF-Token (double-submit, bound to the session).
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain, path="/"
    )


def build_me(db: Session, user: User, csrf: str) -> MeOut:
    plants: list[PlantAccess] = []
    if user.is_system_admin:
        from app.core.permissions import PERMISSIONS

        for p in db.execute(
            select(Plant).where(Plant.organization_id == user.organization_id, Plant.is_active.is_(True)).order_by(Plant.code)
        ).scalars():
            plants.append(
                PlantAccess(
                    plant_id=p.id,
                    plant_code=p.code,
                    plant_name=p.name,
                    timezone=p.timezone,
                    currency=p.currency,
                    role="system_admin",
                    department_id=None,
                    permissions=sorted(PERMISSIONS),
                )
            )
    else:
        rows = db.execute(
            select(Membership, Plant)
            .join(Plant, Plant.id == Membership.plant_id)
            .where(Membership.user_id == user.id, Membership.is_active.is_(True), Plant.is_active.is_(True))
            .order_by(Plant.code)
        ).all()
        for m, p in rows:
            plants.append(
                PlantAccess(
                    plant_id=p.id,
                    plant_code=p.code,
                    plant_name=p.name,
                    timezone=p.timezone,
                    currency=p.currency,
                    role=m.role.code,
                    department_id=m.department_id,
                    permissions=sorted(role_permissions(db, m.role_id)),
                )
            )
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        locale=user.locale,
        is_system_admin=user.is_system_admin,
        plants=plants,
        csrf_token=csrf,
    )


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    s = get_settings()
    now = utcnow()
    ip = client_ip(request)
    email = body.email.lower()
    window = now - timedelta(minutes=s.login_window_minutes)
    ip_failures = db.execute(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.ip == ip, LoginAttempt.success.is_(False), LoginAttempt.at >= window)
    ).scalar_one()
    if ip_failures >= s.login_max_attempts * 4:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts. Try again later.")

    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user is None:
        verify_password(_DUMMY_HASH, body.password)
        db.add(LoginAttempt(email=email, ip=ip, success=False, at=now))
        db.commit()
        raise generic
    if user.locked_until and user.locked_until > now:
        db.add(LoginAttempt(email=email, ip=ip, success=False, at=now))
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Account temporarily locked. Try again later.")
    if not verify_password(user.password_hash, body.password) or not user.is_active:
        user.failed_login_count += 1
        if user.failed_login_count >= s.login_max_attempts:
            user.locked_until = now + timedelta(minutes=s.login_lockout_minutes)
            user.failed_login_count = 0
            audit(db, "auth.lockout", user_id=user.id, organization_id=user.organization_id, ip=ip)
        db.add(LoginAttempt(email=email, ip=ip, success=False, at=now))
        db.commit()
        raise generic

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    token, csrf = new_token(), new_token(24)
    ttl = timedelta(hours=s.session_ttl_hours)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_token=csrf,
            created_at=now,
            expires_at=now + ttl,
            last_seen_at=now,
            ip=ip,
            user_agent=(request.headers.get("user-agent") or "")[:300],
        )
    )
    db.add(LoginAttempt(email=email, ip=ip, success=True, at=now))
    audit(db, "auth.login", user_id=user.id, organization_id=user.organization_id, ip=ip)
    _set_cookies(response, token, csrf, int(ttl.total_seconds()))
    return build_me(db, user, csrf)


@router.post("/logout", status_code=204)
def logout(response: Response, p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> Response:
    p.session.revoked_at = utcnow()
    audit(db, "auth.logout", user_id=p.user.id, organization_id=p.user.organization_id)
    response.status_code = 204
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


@router.get("/me", response_model=MeOut)
def me(p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> MeOut:
    return build_me(db, p.user, p.session.csrf_token)


class ChangePasswordIn(In):
    current_password: str
    new_password: str


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> None:
    if not verify_password(p.user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    p.user.password_hash = hash_password(body.new_password)
    p.user.password_changed_at = utcnow()
    # Revoke every other session of this user.
    for s in db.execute(
        select(UserSession).where(UserSession.user_id == p.user.id, UserSession.id != p.session.id, UserSession.revoked_at.is_(None))
    ).scalars():
        s.revoked_at = utcnow()
    audit(db, "auth.password_changed", user_id=p.user.id, organization_id=p.user.organization_id)


class LocaleIn(In):
    locale: str


@router.post("/locale", status_code=204)
def set_locale(body: LocaleIn, p: Principal = Depends(get_principal)) -> None:
    if body.locale not in {"en", "ar"}:
        raise HTTPException(422, "Unsupported locale")
    p.user.locale = body.locale
