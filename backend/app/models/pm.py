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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Attributed, Base, PlantScoped, Timestamped, enum_col, fk, uuid_pk
from app.models.enums import (
    ChecklistKind,
    FrequencyUnit,
    OccurrenceStatus,
    PMTrigger,
    Priority,
    ScheduleBasis,
    WOType,
)


class JobPlan(Base, PlantScoped, Timestamped, Attributed):
    """Reusable PM task template / job plan."""

    __tablename__ = "job_plans"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    trade: Mapped[str | None] = mapped_column(String(40))
    estimated_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=1)
    crew_size: Mapped[int] = mapped_column(Integer, default=1)
    tools: Mapped[str | None] = mapped_column(Text)
    safety_precautions: Mapped[str | None] = mapped_column(Text)
    requires_loto: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_permit: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_testing: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class JobPlanTask(Base):
    __tablename__ = "job_plan_tasks"
    __table_args__ = (UniqueConstraint("job_plan_id", "seq"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    job_plan_id: Mapped[uuid.UUID] = fk("job_plans.id", ondelete="CASCADE")
    seq: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(400))
    kind: Mapped[ChecklistKind] = enum_col(ChecklistKind, default=ChecklistKind.CHECK)
    unit: Mapped[str | None] = mapped_column(String(20))
    min_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)


class JobPlanMaterial(Base):
    __tablename__ = "job_plan_materials"
    __table_args__ = (UniqueConstraint("job_plan_id", "part_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    job_plan_id: Mapped[uuid.UUID] = fk("job_plans.id", ondelete="CASCADE")
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))


class PMPlan(Base, PlantScoped, Timestamped, Attributed):
    __tablename__ = "pm_plans"
    __table_args__ = (
        UniqueConstraint("plant_id", "code"),
        CheckConstraint("frequency_interval IS NULL OR frequency_interval > 0", name="freq_pos"),
        CheckConstraint("meter_interval IS NULL OR meter_interval > 0", name="meter_int_pos"),
        CheckConstraint("horizon_days BETWEEN 1 AND 730", name="horizon_range"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    asset_id: Mapped[uuid.UUID] = fk("assets.id")
    job_plan_id: Mapped[uuid.UUID] = fk("job_plans.id")
    trigger: Mapped[PMTrigger] = enum_col(PMTrigger, default=PMTrigger.CALENDAR)
    wo_type: Mapped[WOType] = enum_col(WOType, default=WOType.PREVENTIVE)
    priority: Mapped[Priority] = enum_col(Priority, default=Priority.P3_MEDIUM)
    # Calendar trigger
    frequency_unit: Mapped[FrequencyUnit | None] = enum_col(FrequencyUnit, nullable=True)
    frequency_interval: Mapped[int | None] = mapped_column(Integer)
    schedule_basis: Mapped[ScheduleBasis] = enum_col(ScheduleBasis, default=ScheduleBasis.FIXED)
    start_date: Mapped[date | None] = mapped_column(Date)
    # Meter trigger
    meter_id: Mapped[uuid.UUID | None] = fk("meters.id", nullable=True)
    meter_interval: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    last_meter_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    # Generation rules
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)  # how far ahead to create occurrences
    lead_days: Mapped[int] = mapped_column(Integer, default=7)  # create the WO this many days before due
    tolerance_days: Mapped[int] = mapped_column(Integer, default=0)  # completion grace for compliance
    last_completed_date: Mapped[date | None] = mapped_column(Date)
    next_due_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PMOccurrence(Base, PlantScoped, Timestamped):
    """One scheduled instance of a PM plan.

    (pm_plan_id, occurrence_key) is unique, so re-running the scheduler can never create the same
    occurrence twice; work_orders.pm_occurrence_id is unique, so an occurrence yields at most one WO.
    """

    __tablename__ = "pm_occurrences"
    __table_args__ = (
        UniqueConstraint("pm_plan_id", "occurrence_key"),
        Index("ix_pm_occ_plant_due", "plant_id", "due_date"),
        Index("ix_pm_occ_status", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pm_plan_id: Mapped[uuid.UUID] = fk("pm_plans.id", ondelete="CASCADE", index=False)
    occurrence_key: Mapped[str] = mapped_column(String(64))  # "D:2026-11-01" or "M:12000"
    due_date: Mapped[date] = mapped_column(Date)
    original_due_date: Mapped[date] = mapped_column(Date)
    due_meter: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    status: Mapped[OccurrenceStatus] = enum_col(OccurrenceStatus, default=OccurrenceStatus.SCHEDULED)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[date | None] = mapped_column(Date)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    request_reason: Mapped[str | None] = mapped_column(Text)
    requested_new_date: Mapped[date | None] = mapped_column(Date)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
