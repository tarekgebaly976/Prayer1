import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Attributed, Base, PlantScoped, Timestamped, enum_col, fk, uuid_pk
from app.models.enums import Criticality, POStatus, ReservationStatus, TxnType


class Supplier(Base, PlantScoped, Timestamped):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    is_contractor: Mapped[bool] = mapped_column(Boolean, default=False)
    default_lead_time_days: Mapped[int | None] = mapped_column(Integer)


class Warehouse(Base, PlantScoped):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))


class Part(Base, PlantScoped, Timestamped, Attributed):
    __tablename__ = "parts"
    __table_args__ = (
        UniqueConstraint("plant_id", "code"),
        Index("ix_parts_oem_pn", "plant_id", "oem_part_number"),
        CheckConstraint("min_qty >= 0 AND max_qty >= 0 AND safety_stock >= 0", name="levels_nonneg"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    description_ar: Mapped[str | None] = mapped_column(String(300))
    oem_part_number: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(60))
    uom: Mapped[str] = mapped_column(String(16), default="EA")
    criticality: Mapped[Criticality] = enum_col(Criticality, default=Criticality.C)
    is_critical_spare: Mapped[bool] = mapped_column(Boolean, default=False)
    min_qty: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    max_qty: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    safety_stock: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    reorder_point: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    preferred_supplier_id: Mapped[uuid.UUID | None] = fk("suppliers.id", nullable=True)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0)  # last purchase price
    average_cost: Mapped[float] = mapped_column(Numeric(14, 4), default=0)  # moving-average valuation
    currency: Mapped[str] = mapped_column(String(3), default="SAR")
    is_obsolete: Mapped[bool] = mapped_column(Boolean, default=False)
    last_issue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_receipt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PartSubstitute(Base):
    __tablename__ = "part_substitutes"
    __table_args__ = (UniqueConstraint("part_id", "substitute_id"), CheckConstraint("part_id <> substitute_id", name="not_self"))
    id: Mapped[uuid.UUID] = uuid_pk()
    part_id: Mapped[uuid.UUID] = fk("parts.id", ondelete="CASCADE")
    substitute_id: Mapped[uuid.UUID] = fk("parts.id", ondelete="CASCADE")
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)


class StockLevel(Base, PlantScoped):
    """Current balance per part per warehouse/bin. Changed only by the inventory service, under row lock,
    and always together with an InventoryTransaction row."""

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("part_id", "warehouse_id"),
        CheckConstraint("qty_reserved >= 0", name="reserved_nonneg"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    warehouse_id: Mapped[uuid.UUID] = fk("warehouses.id")
    bin: Mapped[str | None] = mapped_column(String(40))
    qty_on_hand: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    qty_reserved: Mapped[float] = mapped_column(Numeric(14, 3), default=0)


class InventoryTransaction(Base, PlantScoped):
    """Append-only stock ledger (UPDATE/DELETE blocked by trigger)."""

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        Index("ix_inv_txn_part_time", "part_id", "created_at"),
        CheckConstraint("quantity <> 0", name="qty_nonzero"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    part_id: Mapped[uuid.UUID] = fk("parts.id", index=False)
    warehouse_id: Mapped[uuid.UUID] = fk("warehouses.id")
    type: Mapped[TxnType] = enum_col(TxnType)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3))  # signed: + into stock, - out of stock
    unit_cost: Mapped[float] = mapped_column(Numeric(14, 4))
    total_cost: Mapped[float] = mapped_column(Numeric(16, 2))
    balance_after: Mapped[float] = mapped_column(Numeric(14, 3))
    work_order_id: Mapped[uuid.UUID | None] = fk("work_orders.id", nullable=True)
    po_line_id: Mapped[uuid.UUID | None] = fk("purchase_order_lines.id", nullable=True)
    reference: Mapped[str | None] = mapped_column(String(120))
    reason: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Reservation(Base, PlantScoped, Timestamped, Attributed):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="qty_pos"),
        CheckConstraint("qty_issued >= 0 AND qty_issued <= quantity", name="issued_range"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id", ondelete="CASCADE")
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    warehouse_id: Mapped[uuid.UUID] = fk("warehouses.id")
    quantity: Mapped[float] = mapped_column(Numeric(14, 3))
    qty_issued: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    status: Mapped[ReservationStatus] = enum_col(ReservationStatus, default=ReservationStatus.ACTIVE)
    needed_by: Mapped[date | None] = mapped_column(Date)


class PurchaseOrder(Base, PlantScoped, Timestamped, Attributed):
    """Local purchase requisition / PO reference. Not an ERP integration."""

    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("plant_id", "number"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    number: Mapped[str] = mapped_column(String(40))
    external_reference: Mapped[str | None] = mapped_column(String(80))  # e.g. ERP PO number, typed manually
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers.id", nullable=True)
    status: Mapped[POStatus] = enum_col(POStatus, default=POStatus.REQUESTED)
    expected_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="SAR")
    notes: Mapped[str | None] = mapped_column(Text)


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="qty_pos"),
        CheckConstraint("qty_received >= 0", name="recv_nonneg"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    purchase_order_id: Mapped[uuid.UUID] = fk("purchase_orders.id", ondelete="CASCADE")
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    quantity: Mapped[float] = mapped_column(Numeric(14, 3))
    qty_received: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4))
    work_order_id: Mapped[uuid.UUID | None] = fk("work_orders.id", nullable=True)


class StockoutEvent(Base, PlantScoped):
    """Recorded when an issue/reservation request could not be met from stock (KPI: stockout rate)."""

    __tablename__ = "stockout_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    work_order_id: Mapped[uuid.UUID | None] = fk("work_orders.id", nullable=True)
    requested_qty: Mapped[float] = mapped_column(Numeric(14, 3))
    available_qty: Mapped[float] = mapped_column(Numeric(14, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
