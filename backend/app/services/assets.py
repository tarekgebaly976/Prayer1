import secrets
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.assets import Asset, AssetStatusHistory
from app.models.enums import ASSET_LEVEL_ORDER, AssetLevel, AssetStatus
from app.models.tenancy import Department
from app.services.common import utcnow


def new_qr_token() -> str:
    return secrets.token_hex(12)


def validate_parent(
    db: Session, plant_id: uuid.UUID, level: AssetLevel, parent_id: uuid.UUID | None, department_id: uuid.UUID
) -> Asset | None:
    """Enforce Production Line -> Unit -> Assembly -> Sub-Assembly -> Component ordering."""
    dept = db.get(Department, department_id)
    if dept is None or dept.plant_id != plant_id:
        raise DomainError("Department not found in this plant", "invalid_department", 422)
    if parent_id is None:
        if level != AssetLevel.PRODUCTION_LINE:
            raise DomainError("Only production lines may sit directly under a department", "invalid_hierarchy", 422)
        return None
    parent = db.get(Asset, parent_id)
    if parent is None or parent.plant_id != plant_id:
        raise DomainError("Parent asset not found in this plant", "invalid_parent", 422)
    if parent.department_id != department_id:
        raise DomainError("Child asset must belong to the same department as its parent", "invalid_hierarchy", 422)
    if ASSET_LEVEL_ORDER.index(level) <= ASSET_LEVEL_ORDER.index(parent.level):
        raise DomainError(f"A {level.value} cannot be placed under a {parent.level.value}", "invalid_hierarchy", 422)
    return parent


def compute_path(parent: Asset | None, asset_id: uuid.UUID) -> str:
    return f"{parent.path if parent else '/'}{asset_id}/"


def move_asset(db: Session, asset: Asset, new_parent_id: uuid.UUID | None) -> None:
    if new_parent_id == asset.id:
        raise DomainError("Asset cannot be its own parent", "invalid_hierarchy", 422)
    parent = validate_parent(db, asset.plant_id, asset.level, new_parent_id, asset.department_id)
    if parent is not None and parent.path.startswith(asset.path):
        raise DomainError("Cannot move an asset beneath its own descendant", "invalid_hierarchy", 422)
    old_path = asset.path
    new_path = compute_path(parent, asset.id)
    asset.parent_id = new_parent_id
    asset.path = new_path
    # Re-root the whole subtree in one statement.
    from sqlalchemy import func

    db.execute(
        update(Asset)
        .where(Asset.plant_id == asset.plant_id, Asset.path.startswith(old_path), Asset.id != asset.id)
        .values(path=func.concat(new_path, func.substr(Asset.path, len(old_path) + 1)))
        .execution_options(synchronize_session=False)
    )


def change_status(db: Session, asset: Asset, status: AssetStatus, user_id: uuid.UUID | None, note: str | None) -> None:
    if asset.status == status:
        return
    db.add(
        AssetStatusHistory(
            asset_id=asset.id, from_status=asset.status.value, to_status=status.value, changed_at=utcnow(), changed_by_id=user_id, note=note
        )
    )
    asset.status = status
    if status == AssetStatus.DECOMMISSIONED:
        asset.is_active = False


def subtree_ids(db: Session, asset: Asset) -> list[uuid.UUID]:
    return list(db.execute(select(Asset.id).where(Asset.plant_id == asset.plant_id, Asset.path.startswith(asset.path))).scalars())


def repair_paths(db: Session, plant_id: uuid.UUID, apply: bool = False) -> dict:
    """Recompute every asset's materialized path from parent_id (the source of truth). Subtree queries (labels,
    parts-used per machine, asset history with children) use the path, so a path left behind by an old import or a
    direct database edit hides assets from them. Assets whose parent is missing or that sit in a cycle become roots."""
    rows = db.execute(select(Asset.id, Asset.parent_id, Asset.path).where(Asset.plant_id == plant_id)).all()
    parent = {r.id: r.parent_id for r in rows}
    current = {r.id: r.path for r in rows}
    kids: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for aid, pid in parent.items():
        kids.setdefault(pid if pid in parent else None, []).append(aid)
    expected: dict[uuid.UUID, str] = {}
    stack = [(aid, "/") for aid in kids.get(None, [])]
    while stack:
        aid, base = stack.pop()
        expected[aid] = f"{base}{aid}/"
        stack.extend((k, expected[aid]) for k in kids.get(aid, []))
    orphans = [aid for aid in parent if aid not in expected]  # unreachable from a root: a parent cycle
    for aid in orphans:
        expected[aid] = f"/{aid}/"
    wrong = {aid: p for aid, p in expected.items() if current[aid] != p}
    if apply:
        for aid, p in wrong.items():
            values: dict = {"path": p}
            if aid in orphans:
                values["parent_id"] = None
            db.execute(update(Asset).where(Asset.id == aid).values(**values).execution_options(synchronize_session=False))
    return {"assets": len(rows), "paths_wrong": len(wrong), "cycles_broken": len(orphans), "applied": apply}
