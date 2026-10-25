import uuid
from datetime import date, datetime

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
from app.models.enums import PackageStatus, ReadinessStatus, ShutdownStatus


class Shutdown(Base, PlantScoped, Timestamped):
    __tablename__ = "shutdowns"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = fk("departments.id", nullable=True)
    planned_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ShutdownStatus] = enum_col(ShutdownStatus, default=ShutdownStatus.PLANNING)
    budget: Mapped[float | None] = mapped_column(Numeric(16, 2))
    completion_report: Mapped[str | None] = mapped_column(Text)
    lessons_learned: Mapped[str | None] = mapped_column(Text)


class ShutdownPackage(Base, PlantScoped, Timestamped):
    __tablename__ = "shutdown_packages"
    __table_args__ = (
        UniqueConstraint("shutdown_id", "code"),
        CheckConstraint("progress_pct BETWEEN 0 AND 100", name="progress_range"),
        CheckConstraint("duration_hours > 0", name="duration_pos"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    shutdown_id: Mapped[uuid.UUID] = fk("shutdowns.id", ondelete="CASCADE")
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    asset_id: Mapped[uuid.UUID | None] = fk("assets.id", nullable=True)
    contractor_id: Mapped[uuid.UUID | None] = fk("suppliers.id", nullable=True)
    owner_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    duration_hours: Mapped[float] = mapped_column(Numeric(8, 2))
    planned_manpower: Mapped[int] = mapped_column(Integer, default=1)
    contractor_manpower: Mapped[int] = mapped_column(Integer, default=0)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # computed by CPM
    planned_finish: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_finish: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    status: Mapped[PackageStatus] = enum_col(PackageStatus, default=PackageStatus.NOT_STARTED)
    material_status: Mapped[ReadinessStatus] = enum_col(ReadinessStatus, ck_name="material_status", default=ReadinessStatus.NOT_READY)
    permit_status: Mapped[ReadinessStatus] = enum_col(ReadinessStatus, ck_name="permit_status", default=ReadinessStatus.NOT_READY)
    loto_status: Mapped[ReadinessStatus] = enum_col(ReadinessStatus, ck_name="loto_status", default=ReadinessStatus.NOT_READY)
    procurement_note: Mapped[str | None] = mapped_column(Text)
    delay_reason: Mapped[str | None] = mapped_column(Text)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)  # set by CPM
    total_float_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))


class PackageDependency(Base):
    __tablename__ = "package_dependencies"
    __table_args__ = (UniqueConstraint("package_id", "predecessor_id"), CheckConstraint("package_id <> predecessor_id", name="not_self"))
    id: Mapped[uuid.UUID] = uuid_pk()
    package_id: Mapped[uuid.UUID] = fk("shutdown_packages.id", ondelete="CASCADE")
    predecessor_id: Mapped[uuid.UUID] = fk("shutdown_packages.id", ondelete="CASCADE")
    lag_hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0)


class ShutdownProgressLog(Base):
    __tablename__ = "shutdown_progress_logs"
    id: Mapped[uuid.UUID] = uuid_pk()
    package_id: Mapped[uuid.UUID] = fk("shutdown_packages.id", ondelete="CASCADE")
    log_date: Mapped[date] = mapped_column(Date)
    progress_pct: Mapped[float] = mapped_column(Numeric(5, 2))
    note: Mapped[str | None] = mapped_column(Text)
    delay_reason: Mapped[str | None] = mapped_column(Text)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ShutdownCheck(Base):
    """Pre-startup inspections and commissioning checks."""

    __tablename__ = "shutdown_checks"
    id: Mapped[uuid.UUID] = uuid_pk()
    shutdown_id: Mapped[uuid.UUID] = fk("shutdowns.id", ondelete="CASCADE")
    category: Mapped[str] = mapped_column(String(30))  # pre_startup | commissioning
    description: Mapped[str] = mapped_column(String(400))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[str | None] = mapped_column(Text)
    done_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
