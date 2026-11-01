import uuid
from datetime import date as date_
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PlantScoped, Timestamped, enum_col, fk, uuid_pk
from app.models.enums import DepartmentType


class Organization(Base, Timestamped):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Plant(Base, Timestamped):
    __tablename__ = "plants"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = fk("organizations.id")
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Riyadh")
    currency: Mapped[str] = mapped_column(String(3), default="SAR")
    default_locale: Mapped[str] = mapped_column(String(8), default="en")
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    # Working calendar: ISO weekdays that are working days (Saudi default Sun-Thu) and hours/day.
    working_days: Mapped[list[int]] = mapped_column(JSONB, default=lambda: [7, 1, 2, 3, 4])
    working_hours_per_day: Mapped[float] = mapped_column(default=8.0)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Summary e-mail (administrators only): sent on these ISO weekdays (1 = Monday .. 7 = Sunday) at this plant-local
    # time to members flagged for it. All 7 days = daily; working days; or one day = weekly.
    daily_summary_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    daily_summary_time: Mapped[time] = mapped_column(Time, default=time(7, 0), server_default="07:00")
    daily_summary_days: Mapped[list[int]] = mapped_column(
        JSONB, default=lambda: [1, 2, 3, 4, 5, 6, 7], server_default=text("'[1, 2, 3, 4, 5, 6, 7]'::jsonb")
    )

    organization: Mapped[Organization] = relationship()


class Holiday(Base, PlantScoped):
    __tablename__ = "plant_holidays"
    __table_args__ = (UniqueConstraint("plant_id", "date"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    date: Mapped[date_] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(120))


class Department(Base, PlantScoped, Timestamped):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("plant_id", "code"),
        CheckConstraint("pdm_alert_action IN ('wo', 'wr', 'none')", name="pdm_alert_action"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[DepartmentType] = enum_col(DepartmentType)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Work-order generation: True = the scheduler / critical alerts create work orders automatically; False = they are
    # held and the planning team releases them (or imports its own plan). PdM covers predictive rounds and alerts.
    pm_auto_wo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    pdm_auto_wo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())  # PdM rounds
    lube_auto_wo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())  # lubrication routes
    # Critical condition alert on a point set to auto-create: "wo" work order, "wr" work request for triage, "none" alert only.
    pdm_alert_action: Mapped[str] = mapped_column(String(8), default="wo", server_default="wo")


class NumberSequence(Base, PlantScoped):
    """Configurable per-plant numbering, e.g. WO-PM1-000123. Allocated under row lock."""

    __tablename__ = "number_sequences"
    __table_args__ = (UniqueConstraint("plant_id", "key"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(32))
    prefix: Mapped[str] = mapped_column(String(32))
    padding: Mapped[int] = mapped_column(Integer, default=6)
    next_value: Mapped[int] = mapped_column(Integer, default=1)


class IntegrationToken(Base, PlantScoped, Timestamped):
    """Credentials for the read-only industrial data gateway (stored hashed, write-only for readings)."""

    __tablename__ = "integration_tokens"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["readings:write"])
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
