import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PlantScoped, Timestamped, enum_col, fk, uuid_pk
from app.models.enums import AlertStatus, ConditionStatus, Priority, Technique


class MeasurementPoint(Base, PlantScoped, Timestamped):
    """Rule-based condition monitoring point with transparent limits (no ML claims)."""

    __tablename__ = "measurement_points"
    __table_args__ = (UniqueConstraint("plant_id", "code"), CheckConstraint("priority BETWEEN 1 AND 3", name="priority_range"))
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    asset_id: Mapped[uuid.UUID] = fk("assets.id")
    technique: Mapped[Technique] = enum_col(Technique)
    unit: Mapped[str] = mapped_column(String(20))
    baseline: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    warning_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    warning_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    alarm_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    alarm_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    stale_after_hours: Mapped[int | None] = mapped_column()  # Unknown status if no reading for this long
    auto_create_wo: Mapped[bool] = mapped_column(Boolean, default=False)
    wo_priority_on_critical: Mapped[Priority] = enum_col(Priority, default=Priority.P2_HIGH)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    external_tag: Mapped[str | None] = mapped_column(String(200))  # OPC UA node id / MQTT topic mapping
    last_status: Mapped[ConditionStatus] = enum_col(ConditionStatus, default=ConditionStatus.UNKNOWN)
    last_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    last_reading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")  # 1 critical, 2 high, 3 normal: list order


class ConditionReading(Base, PlantScoped):
    __tablename__ = "condition_readings"
    __table_args__ = (
        Index("ix_cond_read_point_time", "point_id", "measured_at"),
        UniqueConstraint("point_id", "measured_at", "source"),  # de-duplicates gateway re-sends
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    point_id: Mapped[uuid.UUID] = fk("measurement_points.id", ondelete="CASCADE", index=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[ConditionStatus] = enum_col(ConditionStatus)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import | gateway
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConditionAlert(Base, PlantScoped, Timestamped):
    __tablename__ = "condition_alerts"
    __table_args__ = (Index("ix_alert_point_status", "point_id", "status"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    point_id: Mapped[uuid.UUID] = fk("measurement_points.id", ondelete="CASCADE", index=False)
    asset_id: Mapped[uuid.UUID] = fk("assets.id")
    reading_id: Mapped[uuid.UUID] = fk("condition_readings.id")
    severity: Mapped[ConditionStatus] = enum_col(ConditionStatus)
    status: Mapped[AlertStatus] = enum_col(AlertStatus, default=AlertStatus.OPEN)
    message: Mapped[str] = mapped_column(Text)
    defect_description: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
