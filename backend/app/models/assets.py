import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Attributed, Base, PlantScoped, Timestamped, enum_col, fk, uuid_pk
from app.models.enums import AssetLevel, AssetStatus, Criticality, FailureCodeKind


class Asset(Base, PlantScoped, Timestamped, Attributed):
    """Asset hierarchy node: Production Line -> Unit -> Assembly -> Sub-Assembly -> Component.

    Plant and Department are the two levels above (separate tables). `path` is a materialised
    path of ancestor ids ("/<id>/<id>/") for efficient subtree queries on 100k+ rows.
    """

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("plant_id", "code"),
        Index("ix_assets_path", "path", postgresql_ops={"path": "text_pattern_ops"}),
        Index("ix_assets_plant_parent", "plant_id", "parent_id"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID] = fk("departments.id")
    parent_id: Mapped[uuid.UUID | None] = fk("assets.id", nullable=True, index=False)
    level: Mapped[AssetLevel] = enum_col(AssetLevel)
    path: Mapped[str] = mapped_column(String(2000), default="/")
    code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    oem: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    install_date: Mapped[date | None] = mapped_column(Date)
    criticality: Mapped[Criticality] = enum_col(Criticality, default=Criticality.C)
    status: Mapped[AssetStatus] = enum_col(AssetStatus, default=AssetStatus.IN_SERVICE)
    location: Mapped[str | None] = mapped_column(String(200))
    specifications: Mapped[dict] = mapped_column(JSONB, default=dict)
    operating_limits: Mapped[dict] = mapped_column(JSONB, default=dict)
    operating_hours: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    qr_token: Mapped[str] = mapped_column(String(32), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    parent: Mapped["Asset | None"] = relationship(remote_side="Asset.id")


class AssetStatusHistory(Base):
    __tablename__ = "asset_status_history"
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = fk("assets.id", ondelete="CASCADE")
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)


class AssetBOM(Base):
    __tablename__ = "asset_bom"
    __table_args__ = (UniqueConstraint("asset_id", "part_id"), CheckConstraint("quantity > 0", name="qty_pos"))
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = fk("assets.id", ondelete="CASCADE")
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    position: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)


class Meter(Base, PlantScoped, Timestamped):
    __tablename__ = "meters"
    __table_args__ = (UniqueConstraint("asset_id", "name"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = fk("assets.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(80))  # e.g. "Running hours"
    unit: Mapped[str] = mapped_column(String(20), default="h")
    is_operating_hours: Mapped[bool] = mapped_column(Boolean, default=True)
    current_value: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MeterReading(Base):
    __tablename__ = "meter_readings"
    __table_args__ = (Index("ix_meter_readings_meter_time", "meter_id", "read_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    meter_id: Mapped[uuid.UUID] = fk("meters.id", ondelete="CASCADE", index=False)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(20), default="manual")


class FailureCode(Base, PlantScoped):
    __tablename__ = "failure_codes"
    __table_args__ = (UniqueConstraint("plant_id", "kind", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[FailureCodeKind] = enum_col(FailureCodeKind)
    code: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(200))
    description_ar: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DowntimeEvent(Base, PlantScoped, Timestamped, Attributed):
    """Equipment downtime. `is_failure` events count toward MTBF; breakdown hours toward KPIs."""

    __tablename__ = "downtime_events"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="end_after_start"),
        Index("ix_downtime_asset_time", "asset_id", "started_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = fk("assets.id", index=False)
    work_order_id: Mapped[uuid.UUID | None] = fk("work_orders.id", nullable=True, ondelete="SET NULL")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_failure: Mapped[bool] = mapped_column(Boolean, default=True)
    is_planned: Mapped[bool] = mapped_column(Boolean, default=False)
    production_loss_tons: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    reason: Mapped[str | None] = mapped_column(Text)
