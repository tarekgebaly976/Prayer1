import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.assets import Asset
from app.models.enums import LubeTaskStatus, Priority, WOStatus, WOType
from app.models.inventory import Part, Warehouse
from app.models.lubrication import LubeRoute, LubeTask, Lubricant, LubricantAlternative, LubricationPoint
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services.common import audit, plant_today, utcnow
from app.services.notifications import notify, notify_permission


def point_is_due(db: Session, p: LubricationPoint, on: date) -> date | None:
    """Return the due date if the point is due on/before `on` (calendar or operating-hours trigger)."""
    if p.frequency_days and p.next_due_date and p.next_due_date <= on:
        return p.next_due_date
    if p.frequency_days and p.next_due_date is None:
        return on
    if p.hours_interval:
        asset = db.get(Asset, p.asset_id)
        hours = Decimal(str(asset.operating_hours if asset else 0))
        base = Decimal(str(p.last_done_hours or 0))
        if hours - base >= Decimal(str(p.hours_interval)):
            return on
    return None


def generate_route(
    db: Session, plant: Plant, route: LubeRoute, today: date | None = None, user_id: uuid.UUID | None = None
) -> WorkOrder | None:
    """Create one lubrication WO for all points on the route that are due within the route lead time.
    Idempotent: lube_tasks are unique per (point, due_date), and points already holding a pending task are skipped."""
    from app.services.workorders import create_work_order

    today = today or plant_today(plant)
    horizon = today + timedelta(days=route.lead_days)
    points = (
        db.execute(
            select(LubricationPoint)
            .where(LubricationPoint.route_id == route.id, LubricationPoint.is_active.is_(True))
            .order_by(LubricationPoint.route_seq, LubricationPoint.code)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    due: list[tuple[LubricationPoint, date]] = []
    for p in points:
        pending = db.execute(
            select(LubeTask.id).where(LubeTask.point_id == p.id, LubeTask.status == LubeTaskStatus.PENDING).limit(1)
        ).first()
        if pending:
            continue
        dd = point_is_due(db, p, horizon)
        if dd is not None:
            exists = db.execute(select(LubeTask.id).where(LubeTask.point_id == p.id, LubeTask.due_date == dd)).first()
            if not exists:
                due.append((p, dd))
    if not due:
        return None
    first_asset = db.get(Asset, due[0][0].asset_id)
    assert first_asset is not None
    wo = create_work_order(
        db,
        plant,
        asset=first_asset,
        type=WOType.LUBRICATION,
        priority=Priority.P3_MEDIUM,
        user_id=user_id,
        title=f"Lubrication route {route.code} {route.name}",
        due_date=min(d for _, d in due),
        description=f"{len(due)} lubrication point(s). Use only the specified lubricant or an approved alternative.",
    )
    wo.department_id = route.department_id
    for p, dd in due:
        db.add(LubeTask(plant_id=plant.id, point_id=p.id, route_id=route.id, work_order_id=wo.id, due_date=dd))
    db.flush()
    audit(
        db,
        "lube.route_generated",
        user_id=user_id,
        plant_id=plant.id,
        entity_type="lube_route",
        entity_id=route.id,
        data={"wo": wo.number, "points": len(due)},
    )
    return wo


def check_lubricant(db: Session, point: LubricationPoint, used_id: uuid.UUID) -> None:
    if used_id == point.lubricant_id:
        return
    alt = db.execute(
        select(LubricantAlternative).where(
            LubricantAlternative.lubricant_id == point.lubricant_id,
            LubricantAlternative.alternative_id == used_id,
            LubricantAlternative.approved_at.is_not(None),
        )
    ).scalar_one_or_none()
    if alt is None:
        raise DomainError(
            "This lubricant is not the specified product or an approved alternative. Mixing or substituting "
            "lubricants requires verified compatibility and technical approval.",
            "lubricant_not_approved",
            409,
        )


def record_task(
    db: Session,
    plant: Plant,
    task: LubeTask,
    user_id: uuid.UUID,
    quantity: float,
    lubricant_used_id: uuid.UUID | None,
    note: str | None,
    done_date: date | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> dict:
    if task.status != LubeTaskStatus.PENDING:
        raise DomainError("Task already recorded", "invalid_state", 409)
    if quantity <= 0:
        raise DomainError("Quantity must be positive", "invalid_qty", 422)
    point = db.get(LubricationPoint, task.point_id)
    assert point is not None
    used = lubricant_used_id or point.lubricant_id
    check_lubricant(db, point, used)
    done = done_date or plant_today(plant)
    task.status = LubeTaskStatus.DONE
    task.done_at = utcnow()
    task.done_date = done
    task.done_by_id = user_id
    task.quantity_actual = quantity
    task.lubricant_used_id = used
    task.condition_note = note
    point.last_done_date = done
    asset = db.get(Asset, point.asset_id)
    point.last_done_hours = asset.operating_hours if asset else None
    point.next_due_date = done + timedelta(days=point.frequency_days) if point.frequency_days else None
    warnings: list[str] = []
    q, req = Decimal(str(quantity)), Decimal(str(point.quantity))
    if req and abs(q - req) / req > Decimal("0.2"):
        warnings.append(f"Quantity {quantity}{point.unit} differs by more than 20% from specified {point.quantity}{point.unit}")
    lub = db.get(Lubricant, used)
    if warehouse_id and lub and lub.part_id:
        from app.services.inventory import issue

        part, wh = db.get(Part, lub.part_id), db.get(Warehouse, warehouse_id)
        if part and wh:
            wo = db.get(WorkOrder, task.work_order_id) if task.work_order_id else None
            issue(db, plant, part, wh, quantity / _uom_factor(point.unit, part.uom), user_id, wo=wo, reference=f"lube {point.code}")
    return {"next_due_date": point.next_due_date, "warnings": warnings}


def _uom_factor(point_unit: str, stock_uom: str) -> float:
    """Convert point units to stock units for simple metric cases (g->kg, ml->L)."""
    pu, su = point_unit.lower(), stock_uom.lower()
    if (pu, su) in {("g", "kg"), ("ml", "l")}:
        return 1000.0
    return 1.0


def skip_task(db: Session, task: LubeTask, user_id: uuid.UUID, reason: str) -> None:
    if task.status != LubeTaskStatus.PENDING:
        raise DomainError("Task already recorded", "invalid_state", 409)
    if not reason:
        raise DomainError("Reason required", "reason_required", 422)
    task.status = LubeTaskStatus.SKIPPED
    task.done_by_id = user_id
    task.condition_note = reason
    task.done_at = utcnow()


def pending_count(db: Session, wo_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count()).select_from(LubeTask).where(LubeTask.work_order_id == wo_id, LubeTask.status == LubeTaskStatus.PENDING)
    ).scalar_one()


def on_wo_completed(db: Session, plant: Plant, wo: WorkOrder, user_id: uuid.UUID) -> None:
    """Completion guard already ensured no pending tasks; nothing else to do (next-due set per task)."""


def flag_missed(db: Session, plant: Plant, today: date | None = None) -> int:
    today = today or plant_today(plant)
    grace = int((plant.settings or {}).get("lube_grace_days", 1))
    rows = db.execute(
        select(LubeTask, LubricationPoint)
        .join(LubricationPoint, LubricationPoint.id == LubeTask.point_id)
        .where(
            LubeTask.plant_id == plant.id,
            LubeTask.status == LubeTaskStatus.PENDING,
            LubeTask.due_date < today - timedelta(days=grace),
            LubeTask.missed_notified.is_(False),
        )
    ).all()
    for task, point in rows:
        task.missed_notified = True
        targets = [point.responsible_user_id] if point.responsible_user_id else []
        if targets:
            notify(
                db,
                plant.id,
                targets,
                kind="lube_missed",
                severity="warning",
                title=f"Missed lubrication {point.code}",
                body=f"Due {task.due_date}",
                link="/lubrication",
                dedupe_key=f"lube-missed:{task.id}",
            )
        notify_permission(
            db,
            plant.id,
            "lube.manage",
            kind="lube_missed",
            severity="warning",
            title=f"Missed lubrication {point.code}",
            body=f"Due {task.due_date}",
            link="/lubrication",
            dedupe_key=f"lube-missed:{task.id}",
        )
    return len(rows)


def run_routes(db: Session, plant: Plant, today: date | None = None) -> list[str]:
    out = []
    for r in db.execute(select(LubeRoute).where(LubeRoute.plant_id == plant.id, LubeRoute.is_active.is_(True))).scalars().all():
        wo = generate_route(db, plant, r, today)
        if wo:
            out.append(wo.number)
    return out


def assert_wo_lube_done(db: Session, wo: WorkOrder) -> str | None:
    if wo.type == WOType.LUBRICATION and wo.status != WOStatus.CANCELLED:
        n = pending_count(db, wo.id)
        if n:
            return f"{n} lubrication task(s) not recorded"
    return None
