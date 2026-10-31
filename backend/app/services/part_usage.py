"""Spare parts used on work orders without moving stock (see PartUsage)."""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.assets import Asset
from app.models.enums import WOStatus
from app.models.inventory import Part, PartUsage
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services.common import plant_today, utcnow

CENT = Decimal("0.01")


def record(
    db: Session,
    plant: Plant,
    wo: WorkOrder,
    user_id: uuid.UUID,
    quantity: float,
    part: Part | None = None,
    description: str | None = None,
    uom: str | None = None,
    unit_cost: float | None = None,
    used_on: date | None = None,
    note: str | None = None,
) -> PartUsage:
    if wo.status in (WOStatus.CLOSED, WOStatus.CANCELLED):
        raise DomainError("Cannot record parts on a closed or cancelled work order", "wo_finished", 409)
    if part is None and not (description or "").strip():
        raise DomainError("Choose a spare part or describe the item", "part_required", 422)
    q = Decimal(str(quantity))
    if q <= 0:
        raise DomainError("Quantity must be positive", "invalid_qty", 422)
    if unit_cost is None:  # default: the item's book cost (moving average, else last price)
        cost = Decimal(str((part.average_cost or part.unit_price) if part else 0))
    else:
        cost = Decimal(str(unit_cost))
    if cost < 0:
        raise DomainError("Unit cost cannot be negative", "invalid_cost", 422)
    u = PartUsage(
        plant_id=plant.id,
        work_order_id=wo.id,
        asset_id=wo.asset_id,
        part_id=part.id if part else None,
        description=None if part else description.strip()[:300],  # type: ignore[union-attr]
        quantity=q,
        uom=(uom or (part.uom if part else None) or "EA")[:16],
        unit_cost=cost,
        total_cost=(q * cost).quantize(CENT),
        used_on=used_on or plant_today(plant),
        note=note,
        created_by_id=user_id,
        created_at=utcnow(),
    )
    db.add(u)
    wo.actual_material_cost = Decimal(str(wo.actual_material_cost or 0)) + u.total_cost
    db.flush()
    return u


def remove(db: Session, wo: WorkOrder, usage: PartUsage) -> None:
    if wo.status in (WOStatus.CLOSED, WOStatus.CANCELLED):
        raise DomainError("Cannot change parts on a closed or cancelled work order", "wo_finished", 409)
    wo.actual_material_cost = max(Decimal(str(wo.actual_material_cost or 0)) - Decimal(str(usage.total_cost)), Decimal(0))
    db.delete(usage)
    db.flush()


def report_query(
    plant_id: uuid.UUID,
    start: date | None = None,
    end: date | None = None,
    asset: Asset | None = None,
    part_id: uuid.UUID | None = None,
    department_ids: Sequence[uuid.UUID] = (),
) -> Select:
    """Usage rows with work order, machine and part; `asset` includes everything below it in the hierarchy."""
    q = (
        select(PartUsage, WorkOrder, Asset, Part)
        .join(WorkOrder, WorkOrder.id == PartUsage.work_order_id)
        .join(Asset, Asset.id == PartUsage.asset_id)
        .outerjoin(Part, Part.id == PartUsage.part_id)
        .where(PartUsage.plant_id == plant_id)
    )
    if start:
        q = q.where(PartUsage.used_on >= start)
    if end:
        q = q.where(PartUsage.used_on <= end)
    if asset is not None:
        q = q.where(Asset.path.startswith(asset.path))
    if part_id:
        q = q.where(PartUsage.part_id == part_id)
    if department_ids:
        q = q.where(WorkOrder.department_id.in_(department_ids))
    return q.order_by(PartUsage.used_on.desc(), WorkOrder.number)


def row(u: PartUsage, wo: WorkOrder, a: Asset, p: Part | None) -> dict:
    return {
        "id": u.id,
        "used_on": u.used_on,
        "work_order_id": wo.id,
        "work_order": wo.number,
        "wo_title": wo.title,
        "wo_type": wo.type,
        "asset_id": a.id,
        "asset_code": a.code,
        "asset_name": a.name,
        "part_id": p.id if p else None,
        "part_code": p.code if p else None,
        "description": p.description if p else u.description,
        "quantity": u.quantity,
        "uom": u.uom,
        "unit_cost": u.unit_cost,
        "total_cost": u.total_cost,
        "note": u.note,
    }
