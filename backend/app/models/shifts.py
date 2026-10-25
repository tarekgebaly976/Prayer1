import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PlantScoped, Timestamped, enum_col, fk, uuid_pk
from app.models.enums import HandoverStatus, RosterKind, ShiftKind


class ShiftDefinition(Base, PlantScoped):
    __tablename__ = "shift_definitions"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(8))  # D, E, N, G
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[ShiftKind] = enum_col(ShiftKind)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)  # may be < start_time for overnight shifts
    paid_hours: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=8)


class ShiftPattern(Base, PlantScoped):
    """Rotation cycle: list of shift codes (or "OFF") per day, e.g. ["D","D","E","E","N","N","OFF","OFF"]."""

    __tablename__ = "shift_patterns"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    cycle: Mapped[list[str]] = mapped_column(JSONB)


class Team(Base, PlantScoped, Timestamped):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[uuid.UUID | None] = fk("departments.id", nullable=True)
    supervisor_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    pattern_id: Mapped[uuid.UUID | None] = fk("shift_patterns.id", nullable=True)
    pattern_anchor_date: Mapped[date | None] = mapped_column(Date)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    team_id: Mapped[uuid.UUID] = fk("teams.id", ondelete="CASCADE")
    user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE")


class RosterEntry(Base, PlantScoped, Timestamped):
    """One person on one day. A person can have at most one entry per day (prevents double-rostering);
    overtime/callout on a day already worked are recorded as extra hours on that entry."""

    __tablename__ = "roster_entries"
    __table_args__ = (UniqueConstraint("user_id", "work_date"), Index("ix_roster_plant_date", "plant_id", "work_date"))
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE", index=False)
    work_date: Mapped[date] = mapped_column(Date)
    shift_id: Mapped[uuid.UUID | None] = fk("shift_definitions.id", nullable=True)
    kind: Mapped[RosterKind] = enum_col(RosterKind, default=RosterKind.WORK)
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=8)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    callout_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    team_id: Mapped[uuid.UUID | None] = fk("teams.id", nullable=True)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | pattern


class ShiftHandover(Base, PlantScoped, Timestamped):
    __tablename__ = "shift_handovers"
    __table_args__ = (UniqueConstraint("plant_id", "department_id", "shift_date", "shift_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID] = fk("departments.id")
    shift_date: Mapped[date] = mapped_column(Date)
    shift_id: Mapped[uuid.UUID] = fk("shift_definitions.id")
    outgoing_user_id: Mapped[uuid.UUID] = fk("users.id")
    incoming_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    outstanding_breakdowns: Mapped[str | None] = mapped_column(Text)
    pending_work: Mapped[str | None] = mapped_column(Text)
    safety_concerns: Mapped[str | None] = mapped_column(Text)
    equipment_abnormalities: Mapped[str | None] = mapped_column(Text)
    pending_permits: Mapped[str | None] = mapped_column(Text)
    critical_risks: Mapped[str | None] = mapped_column(Text)
    open_work_order_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)  # snapshot at submit
    status: Mapped[HandoverStatus] = enum_col(HandoverStatus, default=HandoverStatus.DRAFT)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supervisor_comment: Mapped[str | None] = mapped_column(Text)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
