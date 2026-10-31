"""Authentication, CSRF and plant-scoped authorization. Every protected route depends on these."""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import ColumnElement, select, true
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_token
from app.models.identity import Membership, User, UserSession
from app.models.tenancy import Plant
from app.services.common import role_permissions, utcnow

SESSION_COOKIE = "cmms_session"
CSRF_COOKIE = "cmms_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Principal:
    user: User
    session: UserSession


@dataclass
class Ctx:
    """Resolved request context: who is calling, in which plant, with which permissions."""

    user: User
    plant: Plant
    membership: Membership | None
    permissions: set[str] = field(default_factory=set)
    ip: str | None = None

    @property
    def plant_id(self) -> uuid.UUID:
        return self.plant.id

    @property
    def department_ids(self) -> list[uuid.UUID]:
        """Departments the user is limited to ([] = whole plant)."""
        return self.membership.department_ids if self.membership else []

    @property
    def department_id(self) -> uuid.UUID | None:
        """The user's main department (None = whole plant). For access checks use dept_ok / dept_where."""
        return self.membership.department_id if self.membership else None

    def dept_ok(self, department_id: uuid.UUID | None) -> bool:
        """May the user see a record of this department?"""
        ids = self.department_ids
        return not ids or department_id in ids

    def dept_where(self, dept_col: Any) -> ColumnElement[bool]:
        """SQL condition on a department column: one of the user's departments (always true for whole-plant users)."""
        ids = self.department_ids
        return dept_col.in_(ids) if ids else true()

    def in_department(self, asset_col: Any) -> ColumnElement[bool]:
        """SQL condition: the row's asset is in one of the user's departments (always true for whole-plant users)."""
        ids = self.department_ids
        if not ids:
            return true()
        from app.models.assets import Asset

        return asset_col.in_(select(Asset.id).where(Asset.department_id.in_(ids)))

    def check_asset(self, db: Session, asset_id: uuid.UUID, missing: str = "Not found", code: int = 404) -> None:
        """Refuse a record whose asset is outside the user's departments (404 hides it; 403 for a create)."""
        if not self.department_ids:
            return
        from app.models.assets import Asset

        a = db.get(Asset, asset_id)
        if a is None or not self.dept_ok(a.department_id):
            raise HTTPException(code, missing if code == 404 else "Your access is limited to your department")

    def has(self, perm: str) -> bool:
        return perm in self.permissions

    def require(self, perm: str) -> None:
        if perm not in self.permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {perm}")


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def get_principal(request: Request, db: Session = Depends(get_db, scope="function")) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    sess = db.execute(select(UserSession).where(UserSession.token_hash == hash_token(token))).scalar_one_or_none()
    now = utcnow()
    s = get_settings()
    if (
        sess is None
        or sess.revoked_at is not None
        or sess.expires_at <= now
        or sess.last_seen_at + timedelta(minutes=s.session_idle_minutes) <= now
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    # CSRF: double-submit token bound to the server-side session, required for state-changing requests.
    if request.method not in SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER)
        if not header or header != sess.csrf_token:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    if (now - sess.last_seen_at).total_seconds() > 60:
        sess.last_seen_at = now
    return Principal(user=user, session=sess)


def get_ctx(
    request: Request,
    principal: Principal = Depends(get_principal),
    x_plant_id: str | None = Header(default=None, alias="X-Plant-Id"),
    db: Session = Depends(get_db, scope="function"),
) -> Ctx:
    if not x_plant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Plant-Id header required")
    try:
        plant_id = uuid.UUID(x_plant_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid X-Plant-Id") from e
    plant = db.get(Plant, plant_id)
    user = principal.user
    # Deny with 404-equivalent semantics for plants outside the user's organization.
    if plant is None or plant.organization_id != user.organization_id or not plant.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this plant")
    membership = db.execute(
        select(Membership).where(Membership.user_id == user.id, Membership.plant_id == plant.id, Membership.is_active.is_(True))
    ).scalar_one_or_none()
    if membership is None and not user.is_system_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this plant")
    if user.is_system_admin:
        from app.core.permissions import PERMISSIONS

        perms = set(PERMISSIONS)
    else:
        assert membership is not None
        perms = role_permissions(db, membership.role_id)
    return Ctx(user=user, plant=plant, membership=membership, permissions=perms, ip=client_ip(request))


def require(perm: str):
    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        ctx.require(perm)
        return ctx

    return dep
