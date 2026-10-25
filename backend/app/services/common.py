"""Cross-cutting services: audit trail, numbering, RBAC sync, plant-local time."""

import uuid
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS, ROLES
from app.models.identity import Permission, Role, RolePermission
from app.models.system import AuditLog
from app.models.tenancy import NumberSequence, Plant


def utcnow() -> datetime:
    return datetime.now(UTC)


def plant_today(plant: Plant, now: datetime | None = None) -> date:
    """'Today' as seen by the plant (due dates are plant-local calendar dates)."""
    return (now or utcnow()).astimezone(ZoneInfo(plant.timezone)).date()


def audit(
    db: Session,
    action: str,
    *,
    user_id: uuid.UUID | None = None,
    plant_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    data: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            at=utcnow(),
            action=action,
            user_id=user_id,
            plant_id=plant_id,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            data=_jsonable(data or {}),
            ip=ip,
        )
    )


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, uuid.UUID | date | datetime):
        return str(v)
    if hasattr(v, "value"):
        return v.value
    if isinstance(v, int | float | str | bool) or v is None:
        return v
    return str(v)


DEFAULT_PREFIXES = {"WO": "WO-", "WR": "WR-", "PO": "PR-"}


def next_number(db: Session, plant: Plant, key: str) -> str:
    """Allocate the next number for a sequence under a row lock (gap-free within committed txns)."""
    db.execute(
        pg_insert(NumberSequence)
        .values(
            id=uuid.uuid4(),
            plant_id=plant.id,
            key=key,
            prefix=f"{DEFAULT_PREFIXES.get(key, key + '-')}{plant.code}-",
            padding=6,
            next_value=1,
        )
        .on_conflict_do_nothing(index_elements=["plant_id", "key"])
    )
    seq = db.execute(
        select(NumberSequence).where(NumberSequence.plant_id == plant.id, NumberSequence.key == key).with_for_update()
    ).scalar_one()
    value = seq.next_value
    seq.next_value = value + 1
    return f"{seq.prefix}{str(value).zfill(seq.padding)}"


def sync_rbac(db: Session) -> None:
    """Idempotently upsert the permission catalogue and the default role matrix."""
    for code, desc in PERMISSIONS.items():
        db.execute(
            pg_insert(Permission)
            .values(code=code, description=desc)
            .on_conflict_do_update(index_elements=["code"], set_={"description": desc})
        )
    for code, (name, perms) in ROLES.items():
        db.execute(
            pg_insert(Role)
            .values(id=uuid.uuid4(), code=code, name=name)
            .on_conflict_do_update(index_elements=["code"], set_={"name": name})
        )
        role = db.execute(select(Role).where(Role.code == code)).scalar_one()
        existing = set(db.execute(select(RolePermission.permission_code).where(RolePermission.role_id == role.id)).scalars())
        for p in perms - existing:
            db.add(RolePermission(role_id=role.id, permission_code=p))
        for p in existing - perms:
            db.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role.id, RolePermission.permission_code == p))
    db.flush()


def role_permissions(db: Session, role_id: uuid.UUID) -> set[str]:
    return set(db.execute(select(RolePermission.permission_code).where(RolePermission.role_id == role_id)).scalars())
