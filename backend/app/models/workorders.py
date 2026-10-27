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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Attributed, Base, PlantScoped, Timestamped, enum_col, fk, uuid_pk
from app.models.enums import ChecklistKind, Priority, RequestStatus, WOStatus, WOType


class WorkRequest(Base, PlantScoped, Timestamped, Attributed):
    __tablename__ = "work_requests"
    __table_args__ = (UniqueConstraint("plant_id", "number"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    number: Mapped[str] = mapped_column(String(40))
    asset_id: Mapped[uuid.UUID] = fk("assets.id")
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    symptoms: Mapped[str | None] = mapped_column(Text)
    suggested_priority: Mapped[Priority] = enum_col(Priority, default=Priority.P3_MEDIUM)
    is_breakdown: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[RequestStatus] = enum_col(RequestStatus, default=RequestStatus.SUBMITTED)
    triaged_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triage_note: Mapped[str | None] = mapped_column(Text)
    work_order_id: Mapped[uuid.UUID | None] = fk("work_orders.id", nullable=True)


class WorkOrder(Base, PlantScoped, Timestamped, Attributed):
    __tablename__ = "work_orders"
    __table_args__ = (
        UniqueConstraint("plant_id", "number"),
        # One work order per PM occurrence: the hard guarantee behind idempotent PM generation.
        UniqueConstraint("pm_occurrence_id"),
        Index("ix_wo_plant_status", "plant_id", "status"),
        Index("ix_wo_plant_asset", "plant_id", "asset_id"),
        Index("ix_wo_plant_created", "plant_id", "created_at"),
        CheckConstraint("estimated_hours IS NULL OR estimated_hours >= 0", name="est_hours_nonneg"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    number: Mapped[str] = mapped_column(String(40))
    type: Mapped[WOType] = enum_col(WOType)
    status: Mapped[WOStatus] = enum_col(WOStatus, default=WOStatus.TRIAGE)
    priority: Mapped[Priority] = enum_col(Priority, default=Priority.P3_MEDIUM)
    asset_id: Mapped[uuid.UUID] = fk("assets.id", index=False)
    department_id: Mapped[uuid.UUID] = fk("departments.id")
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    symptoms: Mapped[str | None] = mapped_column(Text)
    problem_code_id: Mapped[uuid.UUID | None] = fk("failure_codes.id", nullable=True, index=False)
    cause_code_id: Mapped[uuid.UUID | None] = fk("failure_codes.id", nullable=True, index=False)
    remedy_code_id: Mapped[uuid.UUID | None] = fk("failure_codes.id", nullable=True, index=False)
    supervisor_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)

    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    actual_labor_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    actual_labor_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    actual_material_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    actual_service_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="SAR")

    downtime_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    production_impact: Mapped[str | None] = mapped_column(Text)
    production_loss_tons: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    requires_loto: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_permit: Mapped[bool] = mapped_column(Boolean, default=False)
    permit_reference: Mapped[str | None] = mapped_column(String(80))
    permit_types: Mapped[str | None] = mapped_column(String(200))  # comma-separated PERMIT_TYPES codes
    permit_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safety_requirements: Mapped[str | None] = mapped_column(Text)
    safety_signed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    safety_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requires_testing: Mapped[bool] = mapped_column(Boolean, default=False)
    test_result: Mapped[str | None] = mapped_column(Text)
    test_passed: Mapped[bool | None] = mapped_column(Boolean)
    tested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    findings: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    corrective_action: Mapped[str | None] = mapped_column(Text)
    is_repeat_failure: Mapped[bool] = mapped_column(Boolean, default=False)

    pm_occurrence_id: Mapped[uuid.UUID | None] = fk("pm_occurrences.id", nullable=True, index=False)
    condition_alert_id: Mapped[uuid.UUID | None] = fk("condition_alerts.id", nullable=True)
    shutdown_package_id: Mapped[uuid.UUID | None] = fk("shutdown_packages.id", nullable=True)
    work_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic concurrency token
    __mapper_args__ = {"version_id_col": version}

    assignments: Mapped[list["WOAssignment"]] = relationship(back_populates="work_order", cascade="all, delete-orphan", lazy="selectin")

    @property
    def actual_cost(self) -> float:
        return float(self.actual_labor_cost or 0) + float(self.actual_material_cost or 0) + float(self.actual_service_cost or 0)


class WOAssignment(Base):
    __tablename__ = "wo_assignments"
    __table_args__ = (UniqueConstraint("work_order_id", "user_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id", ondelete="CASCADE")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    work_order: Mapped[WorkOrder] = relationship(back_populates="assignments")


class WOStatusHistory(Base):
    """Append-only approval / status trail (UPDATE/DELETE blocked by trigger)."""

    __tablename__ = "wo_status_history"
    id: Mapped[uuid.UUID] = uuid_pk()
    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id", ondelete="CASCADE")
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)


class WOStatusTransition(Base, PlantScoped):
    """Configurable workflow: allowed status transitions and the permission each one requires."""

    __tablename__ = "wo_status_transitions"
    __table_args__ = (UniqueConstraint("plant_id", "from_status", "to_status"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    from_status: Mapped[str] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    permission: Mapped[str] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WOLabor(Base, Attributed):
    __tablename__ = "wo_labor"
    __table_args__ = (CheckConstraint("hours > 0 AND hours <= 24", name="hours_range"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id", ondelete="CASCADE")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    work_date: Mapped[date] = mapped_column(Date)
    hours: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    is_overtime: Mapped[bool] = mapped_column(Boolean, default=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WOService(Base, Attributed):
    """Contractor / external services."""

    __tablename__ = "wo_services"
    id: Mapped[uuid.UUID] = uuid_pk()
    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id", ondelete="CASCADE")
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers.id", nullable=True)
    description: Mapped[str] = mapped_column(String(300))
    po_reference: Mapped[str | None] = mapped_column(String(60))
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WOChecklistItem(Base):
    __tablename__ = "wo_checklist_items"
    __table_args__ = (UniqueConstraint("work_order_id", "seq"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id", ondelete="CASCADE")
    seq: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(400))
    kind: Mapped[ChecklistKind] = enum_col(ChecklistKind, default=ChecklistKind.CHECK)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    unit: Mapped[str | None] = mapped_column(String(20))
    min_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ok: Mapped[bool | None] = mapped_column(Boolean)
    reading_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    remark: Mapped[str | None] = mapped_column(Text)
    done_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WOComment(Base):
    __tablename__ = "wo_comments"
    id: Mapped[uuid.UUID] = uuid_pk()
    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id", ondelete="CASCADE")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)


PERMIT_TYPES = ("cold_work", "hot_work", "electrical", "confined_space", "work_at_height", "excavation", "lifting", "chemical")
ENERGY_TYPES = ("electrical", "mechanical", "hydraulic", "pneumatic", "steam", "thermal", "chemical", "gravity", "other")


class LotoIsolation(Base, PlantScoped):
    """One isolation point of a work order's LOTO: locked when recorded, released before the work order can complete."""

    __tablename__ = "loto_isolations"
    __table_args__ = (Index("ix_loto_wo", "work_order_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    work_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"))
    point: Mapped[str] = mapped_column(String(200))  # e.g. "MCC-3 breaker Q12", "Steam valve HV-204"
    energy_type: Mapped[str] = mapped_column(String(20))
    lock_number: Mapped[str | None] = mapped_column(String(40))
    zero_energy_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    applied_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
