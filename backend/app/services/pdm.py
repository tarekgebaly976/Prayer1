"""Transparent rule-based condition monitoring: each reading is compared with configured limits.
No statistical failure-probability or AI prediction is made."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.assets import Asset
from app.models.enums import AlertStatus, ConditionStatus, WOType
from app.models.pdm import ConditionAlert, ConditionReading, MeasurementPoint
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services.common import audit, utcnow
from app.services.notifications import notify_permission

_RANK = {ConditionStatus.UNKNOWN: 0, ConditionStatus.NORMAL: 1, ConditionStatus.WARNING: 2, ConditionStatus.CRITICAL: 3}


def evaluate(p: MeasurementPoint, value: float) -> tuple[ConditionStatus, str]:
    v = Decimal(str(value))

    def lim(x: object) -> Decimal | None:
        return Decimal(str(x)) if x is not None else None

    ah, al, wh, wl = lim(p.alarm_high), lim(p.alarm_low), lim(p.warning_high), lim(p.warning_low)
    if all(x is None for x in (ah, al, wh, wl)):
        return ConditionStatus.UNKNOWN, "No limits configured"
    if ah is not None and v >= ah:
        return ConditionStatus.CRITICAL, f"{v} {p.unit} ≥ alarm high {ah}"
    if al is not None and v <= al:
        return ConditionStatus.CRITICAL, f"{v} {p.unit} ≤ alarm low {al}"
    if wh is not None and v >= wh:
        return ConditionStatus.WARNING, f"{v} {p.unit} ≥ warning high {wh}"
    if wl is not None and v <= wl:
        return ConditionStatus.WARNING, f"{v} {p.unit} ≤ warning low {wl}"
    return ConditionStatus.NORMAL, "Within limits"


def validate_limits(p: MeasurementPoint) -> None:
    def f(x: object) -> float | None:
        return float(x) if x is not None else None  # type: ignore[arg-type]

    wh, ah, wl, al = f(p.warning_high), f(p.alarm_high), f(p.warning_low), f(p.alarm_low)
    if wh is not None and ah is not None and ah < wh:
        raise DomainError("Alarm high must be ≥ warning high", "invalid_limits", 422)
    if wl is not None and al is not None and al > wl:
        raise DomainError("Alarm low must be ≤ warning low", "invalid_limits", 422)


def record_reading(
    db: Session,
    plant: Plant,
    p: MeasurementPoint,
    value: float,
    measured_at: datetime,
    user_id: uuid.UUID | None,
    source: str = "manual",
    note: str | None = None,
) -> dict:
    if p.plant_id != plant.id:
        raise DomainError("Measurement point not in this plant", "cross_plant", 422)
    if measured_at > utcnow() + timedelta(minutes=10):
        raise DomainError("Measurement time is in the future", "future_reading", 422)
    status, msg = evaluate(p, value)
    rid = uuid.uuid4()
    res = db.execute(
        pg_insert(ConditionReading)
        .values(
            id=rid,
            plant_id=plant.id,
            point_id=p.id,
            value=value,
            measured_at=measured_at,
            status=status,
            source=source,
            recorded_by_id=user_id,
            note=note,
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["point_id", "measured_at", "source"])
    )
    if not res.rowcount:  # type: ignore[attr-defined]
        return {"duplicate": True, "status": status}
    if p.last_reading_at is None or measured_at >= p.last_reading_at:
        p.last_value, p.last_reading_at, p.last_status = value, measured_at, status
    alert = None
    wo = None
    if status in (ConditionStatus.WARNING, ConditionStatus.CRITICAL):
        alert = db.execute(
            select(ConditionAlert)
            .where(
                ConditionAlert.point_id == p.id,
                ConditionAlert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.WO_CREATED]),
            )
            .with_for_update()
        ).scalar_one_or_none()
        asset = db.get(Asset, p.asset_id)
        label = f"{asset.code if asset else ''} {p.name}"
        if alert is None:
            alert = ConditionAlert(
                plant_id=plant.id,
                point_id=p.id,
                asset_id=p.asset_id,
                reading_id=rid,
                severity=status,
                message=msg,
                recommended_action=p.recommended_action,
            )
            db.add(alert)
            db.flush()
            _notify_alert(db, plant, alert, label)
        elif _RANK[status] > _RANK[alert.severity]:
            alert.severity, alert.message, alert.reading_id = status, f"Escalated: {msg}", rid
            _notify_alert(db, plant, alert, label)
        if status == ConditionStatus.CRITICAL and p.auto_create_wo and alert.work_order_id is None:
            wo = create_wo_from_alert(db, plant, alert, None)
    return {
        "duplicate": False,
        "status": status,
        "message": msg,
        "alert_id": alert.id if alert else None,
        "work_order_id": wo.id if wo else None,
        "reading_id": rid,
    }


def _notify_alert(db: Session, plant: Plant, alert: ConditionAlert, label: str) -> None:
    critical = alert.severity == ConditionStatus.CRITICAL
    notify_permission(
        db,
        plant.id,
        "pdm.alert_manage",
        kind="condition_alert",
        severity="critical" if critical else "warning",
        title=f"{alert.severity.value.upper()}: {label}",
        body=alert.message,
        link=f"/pdm/alerts/{alert.id}",
        dedupe_key=f"alert:{alert.id}:{alert.severity.value}",
        email=critical,
    )


def create_wo_from_alert(db: Session, plant: Plant, alert: ConditionAlert, user_id: uuid.UUID | None) -> WorkOrder:
    from app.services.workorders import create_work_order

    if alert.work_order_id:
        raise DomainError("A work order already exists for this alert", "duplicate", 409)
    p = db.get(MeasurementPoint, alert.point_id)
    asset = db.get(Asset, alert.asset_id)
    assert p is not None and asset is not None
    wo = create_work_order(
        db,
        plant,
        asset=asset,
        type=WOType.PREDICTIVE,
        user_id=user_id,
        priority=p.wo_priority_on_critical if alert.severity == ConditionStatus.CRITICAL else plant_priority_warning(),
        title=f"Condition alert: {p.name}",
        symptoms=alert.message,
        description=alert.recommended_action or p.recommended_action,
        condition_alert_id=alert.id,
    )
    alert.work_order_id = wo.id
    alert.status = AlertStatus.WO_CREATED
    audit(db, "pdm.alert_wo", user_id=user_id, plant_id=plant.id, entity_type="condition_alert", entity_id=alert.id, data={"wo": wo.number})
    return wo


def plant_priority_warning():  # type: ignore[no-untyped-def]
    from app.models.enums import Priority

    return Priority.P3_MEDIUM


def mark_stale(db: Session, plant: Plant) -> int:
    n = 0
    now = utcnow()
    for p in db.execute(
        select(MeasurementPoint).where(
            MeasurementPoint.plant_id == plant.id, MeasurementPoint.is_active.is_(True), MeasurementPoint.stale_after_hours.is_not(None)
        )
    ).scalars():
        if p.last_status != ConditionStatus.UNKNOWN and (
            p.last_reading_at is None or p.last_reading_at < now - timedelta(hours=p.stale_after_hours or 0)
        ):
            p.last_status = ConditionStatus.UNKNOWN
            n += 1
    return n
