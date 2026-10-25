import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PlantScoped, enum_col, fk, uuid_pk
from app.models.enums import DeliveryStatus


class AuditLog(Base):
    """Append-only (UPDATE/DELETE blocked by trigger). Bigint PK preserves insertion order."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_plant_time", "plant_id", "at"), Index("ix_audit_entity", "entity_type", "entity_id"))
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    plant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))


class Notification(Base, PlantScoped):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notif_user_unread", "user_id", "read_at"),
        # dedupe_key prevents the scheduler from notifying the same event twice
        UniqueConstraint("user_id", "dedupe_key"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE", index=False)
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    dedupe_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_outbox_status", "status", "next_attempt_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    notification_id: Mapped[uuid.UUID | None] = fk("notifications.id", nullable=True, ondelete="SET NULL")
    to_address: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[DeliveryStatus] = enum_col(DeliveryStatus, default=DeliveryStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Attachment(Base, PlantScoped):
    __tablename__ = "attachments"
    __table_args__ = (Index("ix_attach_entity", "entity_type", "entity_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(40))  # asset | work_order | shutdown | ...
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    category: Mapped[str] = mapped_column(String(30), default="document")  # manual|drawing|photo|report|document
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(400), unique=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # soft delete (documented)


class JobRun(Base):
    """Observability for background jobs."""

    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_job_time", "job", "started_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    job: Mapped[str] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|failed|skipped
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class ProductionRecord(Base, PlantScoped):
    """Daily production per department/line: needed for cost-per-ton and OEE (never estimated)."""

    __tablename__ = "production_records"
    __table_args__ = (UniqueConstraint("plant_id", "department_id", "asset_id", "record_date"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID] = fk("departments.id")
    asset_id: Mapped[uuid.UUID | None] = fk("assets.id", nullable=True)  # usually the production line
    record_date: Mapped[date] = mapped_column(Date)
    tons_produced: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    good_tons: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    planned_production_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    run_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    ideal_rate_tph: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class MaintenanceBudget(Base, PlantScoped):
    __tablename__ = "maintenance_budgets"
    __table_args__ = (UniqueConstraint("plant_id", "department_id", "year", "month"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID | None] = fk("departments.id", nullable=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="SAR")


class KPIDefinition(Base):
    """Documented KPI definitions; `config` holds tunable parameters. Plant overrides live in plant.settings."""

    __tablename__ = "kpi_definitions"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    formula: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20))
    source_data: Mapped[str] = mapped_column(Text)
    inclusion_rules: Mapped[str] = mapped_column(Text)
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class KPISnapshot(Base, PlantScoped):
    """Monthly KPI values persisted by the scheduler for trend reporting."""

    __tablename__ = "kpi_snapshots"
    __table_args__ = (UniqueConstraint("plant_id", "kpi_code", "period_start", "scope_key"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    kpi_code: Mapped[str] = mapped_column(String(40), ForeignKey("kpi_definitions.code"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    scope_key: Mapped[str] = mapped_column(String(80), default="plant")
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
