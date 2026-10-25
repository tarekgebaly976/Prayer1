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
