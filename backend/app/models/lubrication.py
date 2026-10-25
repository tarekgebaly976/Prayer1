import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PlantScoped, Timestamped, enum_col, fk, uuid_pk
from app.models.enums import LubeTaskStatus


class Lubricant(Base, PlantScoped, Timestamped):
    __tablename__ = "lubricants"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40))
    manufacturer: Mapped[str] = mapped_column(String(120))
    product: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(16))  # oil | grease
    viscosity_grade: Mapped[str | None] = mapped_column(String(40))  # e.g. ISO VG 220
    specification: Mapped[str | None] = mapped_column(String(200))  # e.g. NLGI 2 lithium complex
    part_id: Mapped[uuid.UUID | None] = fk("parts.id", nullable=True)  # stock item for consumption
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)


class LubricantAlternative(Base):
    """An alternative is usable only once compatibility has been verified and technically approved."""

    __tablename__ = "lubricant_alternatives"
    __table_args__ = (
        UniqueConstraint("lubricant_id", "alternative_id"),
        CheckConstraint("lubricant_id <> alternative_id", name="not_self"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    lubricant_id: Mapped[uuid.UUID] = fk("lubricants.id", ondelete="CASCADE")
    alternative_id: Mapped[uuid.UUID] = fk("lubricants.id", ondelete="CASCADE")
    compatibility_note: Mapped[str] = mapped_column(Text)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LubeRoute(Base, PlantScoped, Timestamped):
    __tablename__ = "lube_routes"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[uuid.UUID] = fk("departments.id")
    lead_days: Mapped[int] = mapped_column(Integer, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LubricationPoint(Base, PlantScoped, Timestamped):
    __tablename__ = "lubrication_points"
    __table_args__ = (
        UniqueConstraint("plant_id", "code"),
        CheckConstraint("frequency_days IS NOT NULL OR hours_interval IS NOT NULL", name="has_interval"),
        CheckConstraint("quantity > 0", name="qty_pos"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40))
    asset_id: Mapped[uuid.UUID] = fk("assets.id")
    component: Mapped[str | None] = mapped_column(String(120))  # e.g. "Drive-side bearing"
    location: Mapped[str | None] = mapped_column(String(200))
    lubricant_id: Mapped[uuid.UUID] = fk("lubricants.id")
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    unit: Mapped[str] = mapped_column(String(10), default="g")
    method: Mapped[str | None] = mapped_column(String(120))  # grease gun / oil can / top-up / change
    tools: Mapped[str | None] = mapped_column(String(200))
    frequency_days: Mapped[int | None] = mapped_column(Integer)
    hours_interval: Mapped[Decimal | None] = mapped_column(Numeric(10, 1))
    oem_recommendation: Mapped[str | None] = mapped_column(Text)
    route_id: Mapped[uuid.UUID | None] = fk("lube_routes.id", nullable=True)
    route_seq: Mapped[int] = mapped_column(Integer, default=0)
    responsible_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    last_done_date: Mapped[date | None] = mapped_column(Date)
    last_done_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))  # asset operating hours at last service
    next_due_date: Mapped[date | None] = mapped_column(Date, index=True)
    qr_token: Mapped[str] = mapped_column(String(32), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LubeTask(Base, PlantScoped, Timestamped):
    __tablename__ = "lube_tasks"
    __table_args__ = (UniqueConstraint("point_id", "due_date"),)  # idempotent route generation
    id: Mapped[uuid.UUID] = uuid_pk()
    point_id: Mapped[uuid.UUID] = fk("lubrication_points.id", ondelete="CASCADE")
    route_id: Mapped[uuid.UUID | None] = fk("lube_routes.id", nullable=True)
    work_order_id: Mapped[uuid.UUID | None] = fk("work_orders.id", nullable=True, ondelete="SET NULL")
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[LubeTaskStatus] = enum_col(LubeTaskStatus, default=LubeTaskStatus.PENDING)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_date: Mapped[date | None] = mapped_column(Date)
    done_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    quantity_actual: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    lubricant_used_id: Mapped[uuid.UUID | None] = fk("lubricants.id", nullable=True)
    condition_note: Mapped[str | None] = mapped_column(Text)
    missed_notified: Mapped[bool] = mapped_column(Boolean, default=False)
