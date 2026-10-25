import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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

    organization: Mapped[Organization] = relationship()


class Holiday(Base, PlantScoped):
    __tablename__ = "plant_holidays"
    __table_args__ = (UniqueConstraint("plant_id", "date"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    date: Mapped[date_] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(120))


class Department(Base, PlantScoped, Timestamped):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[DepartmentType] = enum_col(DepartmentType)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


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
