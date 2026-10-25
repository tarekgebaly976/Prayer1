"""Inventory ledger. Every balance change:
  1. locks the stock_levels row (SELECT ... FOR UPDATE) - concurrent issues serialise on it;
  2. validates availability (no negative stock unless the plant explicitly allows it);
  3. writes an append-only inventory_transactions row with cost and balance_after.
Valuation: moving-average cost; issues are costed at the average at time of issue."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.errors import DomainError
from app.models.enums import POStatus, ReservationStatus, TxnType, WOStatus
from app.models.inventory import (
    InventoryTransaction,
    Part,
    PurchaseOrder,
    PurchaseOrderLine,
    Reservation,
    StockLevel,
    StockoutEvent,
    Warehouse,
)
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services.common import plant_today, utcnow
from app.services.notifications import notify_permission

D = Decimal
Q3 = D("0.001")


def d(v: object) -> Decimal:
    return D(str(v if v is not None else 0))


def _check_scope(plant: Plant, part: Part, wh: Warehouse) -> None:
    if part.plant_id != plant.id or wh.plant_id != plant.id:
        raise DomainError("Part or warehouse not in this plant", "cross_plant", 422)


def lock_stock(db: Session, plant: Plant, part: Part, wh: Warehouse) -> StockLevel:
    _check_scope(plant, part, wh)
    db.execute(
        pg_insert(StockLevel)
        .values(id=uuid.uuid4(), plant_id=plant.id, part_id=part.id, warehouse_id=wh.id, qty_on_hand=0, qty_reserved=0)
        .on_conflict_do_nothing(index_elements=["part_id", "warehouse_id"])
    )
    return db.execute(
        select(StockLevel)
        .where(StockLevel.part_id == part.id, StockLevel.warehouse_id == wh.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).scalar_one()


def _lock_part(db: Session, part: Part) -> Part:
    return db.execute(select(Part).where(Part.id == part.id).with_for_update(key_share=True).execution_options(populate_existing=True)).scalar_one()


def _txn(
    db: Session,
    plant: Plant,
    part: Part,
    wh: Warehouse,
    t: TxnType,
    qty: Decimal,
    unit_cost: Decimal,
    balance: Decimal,
    user_id: uuid.UUID | None,
    wo: WorkOrder | None = None,
    reference: str | None = None,
    reason: str | None = None,
    po_line_id: uuid.UUID | None = None,
) -> InventoryTransaction:
    tx = InventoryTransaction(
        plant_id=plant.id,
        part_id=part.id,
        warehouse_id=wh.id,
        type=t,
        quantity=qty,
        unit_cost=unit_cost,
        total_cost=(qty * unit_cost).quantize(D("0.01")),
        balance_after=balance,
        work_order_id=wo.id if wo else None,
        reference=reference,
        reason=reason,
        po_line_id=po_line_id,
        created_by_id=user_id,
        created_at=utcnow(),
    )
    db.add(tx)
    return tx


def on_order_qty(db: Session, part_id: uuid.UUID) -> Decimal:
    v = db.execute(
        select(func.coalesce(func.sum(PurchaseOrderLine.quantity - PurchaseOrderLine.qty_received), 0))
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(PurchaseOrderLine.part_id == part_id, PurchaseOrder.status.in_([POStatus.REQUESTED, POStatus.ORDERED, POStatus.PARTIAL]))
    ).scalar()
    return d(v)


def total_available(db: Session, part_id: uuid.UUID) -> Decimal:
    v = db.execute(
        select(func.coalesce(func.sum(StockLevel.qty_on_hand - StockLevel.qty_reserved), 0)).where(StockLevel.part_id == part_id)
    ).scalar()
    return d(v)


def receive(
    db: Session,
    plant: Plant,
    part: Part,
    wh: Warehouse,
    qty: float,
    unit_cost: float,
    user_id: uuid.UUID | None,
    reference: str | None = None,
    po_line: PurchaseOrderLine | None = None,
) -> InventoryTransaction:
    q, c = d(qty), d(unit_cost)
    if q <= 0 or c < 0:
        raise DomainError("Receipt quantity must be positive and cost non-negative", "invalid_qty", 422)
    part = _lock_part(db, part)
    sl = lock_stock(db, plant, part, wh)
    total_on_hand = d(db.execute(select(func.coalesce(func.sum(StockLevel.qty_on_hand), 0)).where(StockLevel.part_id == part.id)).scalar())
    if total_on_hand <= 0:
        part.average_cost = c
    else:
        part.average_cost = ((total_on_hand * d(part.average_cost) + q * c) / (total_on_hand + q)).quantize(D("0.0001"))
    part.unit_price = c
    part.last_receipt_at = utcnow()
    sl.qty_on_hand = d(sl.qty_on_hand) + q
    if po_line is not None:
        po_line.qty_received = d(po_line.qty_received) + q
        _update_po_status(db, po_line.purchase_order_id)
    return _txn(
        db,
        plant,
        part,
        wh,
        TxnType.RECEIPT,
        q,
        c,
        d(sl.qty_on_hand),
        user_id,
        reference=reference,
        po_line_id=po_line.id if po_line else None,
    )


def _update_po_status(db: Session, po_id: uuid.UUID) -> None:
    po = db.get(PurchaseOrder, po_id)
    assert po is not None
    db.flush()
    lines = db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po_id)).scalars().all()
    if all(d(ln.qty_received) >= d(ln.quantity) for ln in lines):
        po.status = POStatus.RECEIVED
    elif any(d(ln.qty_received) > 0 for ln in lines):
        po.status = POStatus.PARTIAL


def record_stockout(plant_id: uuid.UUID, part_id: uuid.UUID, wo_id: uuid.UUID | None, requested: Decimal, available: Decimal) -> None:
    """Persist in an independent transaction so the event survives the caller's rollback."""
    with SessionLocal() as s, s.begin():
        s.add(
            StockoutEvent(
                plant_id=plant_id,
                part_id=part_id,
                work_order_id=wo_id,
                requested_qty=requested,
                available_qty=available,
                created_at=utcnow(),
            )
        )


def reserve(db: Session, plant: Plant, wo: WorkOrder, part: Part, wh: Warehouse, qty: float, user_id: uuid.UUID | None) -> Reservation:
    if wo.plant_id != plant.id:
        raise DomainError("Work order not in this plant", "cross_plant", 422)
    if wo.status in (WOStatus.COMPLETED, WOStatus.CLOSED, WOStatus.CANCELLED):
        raise DomainError("Cannot reserve materials for a finished work order", "wo_finished", 409)
    q = d(qty)
    if q <= 0:
        raise DomainError("Quantity must be positive", "invalid_qty", 422)
    sl = lock_stock(db, plant, part, wh)
    available = d(sl.qty_on_hand) - d(sl.qty_reserved)
    if q > available:
        record_stockout(plant.id, part.id, wo.id, q, available)
        notify_permission(
            db,
            plant.id,
            "inventory.transact",
            kind="stockout",
            severity="warning",
            title=f"Stockout: {part.code}",
            body=f"{wo.number} needs {q} {part.uom}, available {available}",
            link=f"/inventory/parts/{part.id}",
            dedupe_key=f"stockout:{part.id}:{plant_today(plant)}",
        )
        raise DomainError(f"Insufficient stock for {part.code}: requested {q}, available {available}", "insufficient_stock", 409)
    sl.qty_reserved = d(sl.qty_reserved) + q
    r = Reservation(plant_id=plant.id, work_order_id=wo.id, part_id=part.id, warehouse_id=wh.id, quantity=q, created_by_id=user_id)
    db.add(r)
    db.flush()
    return r


def cancel_reservation(db: Session, r: Reservation) -> None:
    if r.status != ReservationStatus.ACTIVE:
        return
    sl = db.execute(
        select(StockLevel)
        .where(StockLevel.part_id == r.part_id, StockLevel.warehouse_id == r.warehouse_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).scalar_one()
    remaining = d(r.quantity) - d(r.qty_issued)
    sl.qty_reserved = max(D(0), d(sl.qty_reserved) - remaining)
    r.status = ReservationStatus.CANCELLED if d(r.qty_issued) == 0 else ReservationStatus.FULFILLED


def issue(
    db: Session,
    plant: Plant,
    part: Part,
    wh: Warehouse,
    qty: float,
    user_id: uuid.UUID | None,
    wo: WorkOrder | None = None,
    reservation: Reservation | None = None,
    reference: str | None = None,
) -> InventoryTransaction:
    q = d(qty)
    if q <= 0:
        raise DomainError("Quantity must be positive", "invalid_qty", 422)
    if wo is not None:
        if wo.plant_id != plant.id:
            raise DomainError("Work order not in this plant", "cross_plant", 422)
        if wo.status in (WOStatus.CLOSED, WOStatus.CANCELLED):
            raise DomainError("Cannot issue to a closed or cancelled work order", "wo_finished", 409)
    part = _lock_part(db, part)
    sl = lock_stock(db, plant, part, wh)
    reserved_for_this = D(0)
    if reservation is not None:
        if (
            reservation.status != ReservationStatus.ACTIVE
            or reservation.part_id != part.id
            or reservation.warehouse_id != wh.id
            or (wo and reservation.work_order_id != wo.id)
        ):
            raise DomainError("Reservation does not match this issue", "invalid_reservation", 409)
        reserved_for_this = min(q, d(reservation.quantity) - d(reservation.qty_issued))
    free = d(sl.qty_on_hand) - d(sl.qty_reserved) + reserved_for_this
    if q > free and not plant.allow_negative_stock:
        record_stockout(plant.id, part.id, wo.id if wo else None, q, free)
        raise DomainError(f"Insufficient stock for {part.code}: requested {q}, available {free}", "insufficient_stock", 409)
    cost = d(part.average_cost)
    sl.qty_on_hand = d(sl.qty_on_hand) - q
    if reservation is not None:
        sl.qty_reserved = d(sl.qty_reserved) - reserved_for_this
        reservation.qty_issued = d(reservation.qty_issued) + reserved_for_this
        if d(reservation.qty_issued) >= d(reservation.quantity):
            reservation.status = ReservationStatus.FULFILLED
    part.last_issue_at = utcnow()
    tx = _txn(db, plant, part, wh, TxnType.ISSUE, -q, cost, d(sl.qty_on_hand), user_id, wo=wo, reference=reference)
    if wo is not None:
        wo.actual_material_cost = d(wo.actual_material_cost) + (q * cost).quantize(D("0.01"))
    db.flush()
    _reorder_check(db, plant, part)
    return tx


def return_to_stock(
    db: Session, plant: Plant, part: Part, wh: Warehouse, qty: float, user_id: uuid.UUID | None, wo: WorkOrder, reason: str | None = None
) -> InventoryTransaction:
    q = d(qty)
    if q <= 0:
        raise DomainError("Quantity must be positive", "invalid_qty", 422)
    if wo.status == WOStatus.CLOSED:
        raise DomainError("Cannot return against a closed work order", "wo_finished", 409)
    rows = db.execute(
        select(InventoryTransaction.quantity, InventoryTransaction.total_cost).where(
            InventoryTransaction.work_order_id == wo.id,
            InventoryTransaction.part_id == part.id,
            InventoryTransaction.type.in_([TxnType.ISSUE, TxnType.RETURN]),
        )
    ).all()
    net_issued = -sum((d(r[0]) for r in rows), D(0))
    net_cost = -sum((d(r[1]) for r in rows), D(0))
    if q > net_issued:
        raise DomainError(f"Cannot return {q}: only {net_issued} net issued to {wo.number}", "invalid_return", 409)
    unit_cost = (net_cost / net_issued).quantize(D("0.0001")) if net_issued else d(part.average_cost)
    part = _lock_part(db, part)
    sl = lock_stock(db, plant, part, wh)
    total_on_hand = d(db.execute(select(func.coalesce(func.sum(StockLevel.qty_on_hand), 0)).where(StockLevel.part_id == part.id)).scalar())
    if total_on_hand + q > 0:
        part.average_cost = ((max(total_on_hand, D(0)) * d(part.average_cost) + q * unit_cost) / (max(total_on_hand, D(0)) + q)).quantize(
            D("0.0001")
        )
    sl.qty_on_hand = d(sl.qty_on_hand) + q
    wo.actual_material_cost = d(wo.actual_material_cost) - (q * unit_cost).quantize(D("0.01"))
    return _txn(db, plant, part, wh, TxnType.RETURN, q, unit_cost, d(sl.qty_on_hand), user_id, wo=wo, reason=reason)


def adjust(
    db: Session, plant: Plant, part: Part, wh: Warehouse, delta: float, reason: str, user_id: uuid.UUID | None
) -> InventoryTransaction:
    q = d(delta)
    if q == 0:
        raise DomainError("Adjustment cannot be zero", "invalid_qty", 422)
    if not reason or len(reason) < 5:
        raise DomainError("A reason is required for stock adjustments", "reason_required", 422)
    part = _lock_part(db, part)
    sl = lock_stock(db, plant, part, wh)
    new = d(sl.qty_on_hand) + q
    if new < d(sl.qty_reserved) and not plant.allow_negative_stock:
        raise DomainError("Adjustment would leave less stock than is reserved", "insufficient_stock", 409)
    if new < 0 and not plant.allow_negative_stock:
        raise DomainError("Adjustment would make stock negative", "negative_stock", 409)
    sl.qty_on_hand = new
    tx = _txn(db, plant, part, wh, TxnType.ADJUSTMENT, q, d(part.average_cost), new, user_id, reason=reason)
    db.flush()
    _reorder_check(db, plant, part)
    return tx


def transfer(db: Session, plant: Plant, part: Part, src: Warehouse, dst: Warehouse, qty: float, user_id: uuid.UUID | None) -> None:
    q = d(qty)
    if src.id == dst.id or q <= 0:
        raise DomainError("Invalid transfer", "invalid_transfer", 422)
    part = _lock_part(db, part)
    # Lock in a deterministic order to avoid deadlocks between opposite transfers.
    first, second = sorted([src, dst], key=lambda w: str(w.id))
    s1, s2 = lock_stock(db, plant, part, first), lock_stock(db, plant, part, second)
    ss, ds = (s1, s2) if first.id == src.id else (s2, s1)
    if d(ss.qty_on_hand) - d(ss.qty_reserved) < q:
        raise DomainError("Insufficient free stock in source warehouse", "insufficient_stock", 409)
    ss.qty_on_hand = d(ss.qty_on_hand) - q
    ds.qty_on_hand = d(ds.qty_on_hand) + q
    c = d(part.average_cost)
    _txn(db, plant, part, src, TxnType.TRANSFER_OUT, -q, c, d(ss.qty_on_hand), user_id, reference=f"to {dst.code}")
    _txn(db, plant, part, dst, TxnType.TRANSFER_IN, q, c, d(ds.qty_on_hand), user_id, reference=f"from {src.code}")


def _reorder_check(db: Session, plant: Plant, part: Part) -> None:
    on_hand = d(db.execute(select(func.coalesce(func.sum(StockLevel.qty_on_hand), 0)).where(StockLevel.part_id == part.id)).scalar())
    position = total_available(db, part.id) + on_order_qty(db, part.id)
    today = plant_today(plant)
    if on_hand <= 0:
        notify_permission(
            db,
            plant.id,
            "inventory.transact",
            kind="stockout",
            severity="critical" if part.is_critical_spare else "warning",
            title=f"Out of stock: {part.code}",
            body=part.description,
            link=f"/inventory/parts/{part.id}",
            dedupe_key=f"oos:{part.id}:{today}",
        )
    elif d(part.reorder_point) > 0 and position <= d(part.reorder_point):
        notify_permission(
            db,
            plant.id,
            "purchase.manage",
            kind="reorder",
            severity="warning",
            title=f"Reorder point reached: {part.code}",
            body=f"Stock position {position} ≤ reorder point {part.reorder_point}",
            link=f"/inventory/parts/{part.id}",
            dedupe_key=f"reorder:{part.id}:{today}",
        )
