import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Ctx
from app.core.errors import DomainError
from app.models.assets import Asset
from app.models.enums import (
    OPEN_WO_STATUSES,
    AssetStatus,
    OccurrenceStatus,
    Priority,
    ReservationStatus,
    RosterKind,
    WOStatus,
    WOType,
)
from app.models.identity import Membership, User
from app.models.inventory import Reservation
from app.models.pm import JobPlan, JobPlanTask, PMOccurrence
from app.models.shifts import RosterEntry
from app.models.tenancy import Plant
from app.models.workorders import LotoIsolation, WOAssignment, WOChecklistItem, WOLabor, WorkOrder, WOStatusHistory
from app.services.common import audit, next_number, plant_today, utcnow
from app.services.notifications import notify, notify_permission
from app.services.workflow import get_transition


def create_work_order(
    db: Session,
    plant: Plant,
    *,
    asset: Asset,
    type: WOType,
    title: str,
    user_id: uuid.UUID | None,
    priority: Priority = Priority.P3_MEDIUM,
    description: str | None = None,
    symptoms: str | None = None,
    job_plan: JobPlan | None = None,
    due_date: date | None = None,
    status: WOStatus | None = None,
    **extra: object,
) -> WorkOrder:
    if asset.plant_id != plant.id:
        raise DomainError("Asset is not in this plant", "cross_plant", 422)
    if status is None:
        # Emergency breakdowns start in triage but may be fast-tracked; PMs are pre-approved by their plan.
        status = WOStatus.APPROVED if type in (WOType.PREVENTIVE, WOType.LUBRICATION) else WOStatus.TRIAGE
    wo = WorkOrder(
        id=uuid.uuid4(),
        plant_id=plant.id,
        number=next_number(db, plant, "WO"),
        type=type,
        status=status,
        priority=Priority.P1_EMERGENCY if type == WOType.EMERGENCY else priority,
        asset_id=asset.id,
        department_id=asset.department_id,
        title=title,
        description=description,
        symptoms=symptoms,
        due_date=due_date,
        currency=plant.currency,
        created_by_id=user_id,
        **extra,
    )
    if job_plan is not None:
        wo.estimated_hours = job_plan.estimated_hours
        wo.requires_loto = wo.requires_loto or job_plan.requires_loto
        wo.requires_permit = wo.requires_permit or job_plan.requires_permit
        wo.permit_types = wo.permit_types or job_plan.permit_types
        wo.requires_testing = wo.requires_testing or job_plan.requires_testing
        wo.safety_requirements = job_plan.safety_precautions
        if not wo.description:
            wo.description = job_plan.description
    db.add(wo)
    db.flush()
    if job_plan is not None:
        tasks = db.execute(select(JobPlanTask).where(JobPlanTask.job_plan_id == job_plan.id).order_by(JobPlanTask.seq)).scalars()
        for t in tasks:
            db.add(
                WOChecklistItem(
                    work_order_id=wo.id,
                    seq=t.seq,
                    description=t.description,
                    kind=t.kind,
                    is_required=t.is_required,
                    unit=t.unit,
                    min_value=t.min_value,
                    max_value=t.max_value,
                )
            )
    db.add(
        WOStatusHistory(
            work_order_id=wo.id, from_status=None, to_status=wo.status.value, changed_by_id=user_id, changed_at=utcnow(), comment="created"
        )
    )
    audit(
        db,
        "wo.create",
        user_id=user_id,
        plant_id=plant.id,
        entity_type="work_order",
        entity_id=wo.id,
        data={"number": wo.number, "type": type, "asset": asset.code},
    )
    if type == WOType.EMERGENCY:
        notify_permission(
            db,
            plant.id,
            "wo.close_emergency",
            department_id=wo.department_id,
            kind="emergency",
            severity="critical",
            title=f"Emergency breakdown {wo.number}",
            body=f"{asset.code} — {title}",
            link=f"/work-orders/{wo.id}",
            dedupe_key=f"wo-emergency:{wo.id}",
            email=True,
        )
    return wo


def _settings(plant: Plant) -> dict:
    return plant.settings or {}


def locks_on(db: Session, wo: WorkOrder) -> int:
    """Isolation points still locked on this work order."""
    return db.execute(
        select(func.count()).select_from(LotoIsolation).where(LotoIsolation.work_order_id == wo.id, LotoIsolation.removed_at.is_(None))
    ).scalar_one()


def check_safety_ready(db: Session, wo: WorkOrder) -> None:
    """Conditions for the supervisor's LOTO / permit sign-off."""
    errors: list[str] = []
    if wo.requires_permit and not wo.permit_reference:
        errors.append("Permit reference is required")
    if wo.permit_valid_until and wo.permit_valid_until < utcnow():
        errors.append("The permit has expired")
    if wo.requires_loto:
        rows = (
            db.execute(select(LotoIsolation).where(LotoIsolation.work_order_id == wo.id, LotoIsolation.removed_at.is_(None)))
            .scalars()
            .all()
        )
        if not rows:
            errors.append("Record at least one LOTO isolation point (lock applied) before sign-off")
        elif not all(r.zero_energy_verified for r in rows):
            errors.append("Zero energy must be verified on every isolation point")
    if errors:
        raise DomainError("; ".join(errors), "safety_not_ready", 409)


def check_completion_guards(db: Session, plant: Plant, wo: WorkOrder) -> None:
    errors: list[str] = []
    if locks_on(db, wo):
        errors.append("Remove all LOTO locks (isolation register) before completing the work")
    if (wo.requires_loto or wo.requires_permit) and not wo.safety_signed_at:
        errors.append("Safety (LOTO/permit) sign-off is required")
    if wo.requires_permit and not wo.permit_reference:
        errors.append("Permit reference is required")
    if wo.requires_testing and (not wo.test_result or wo.test_passed is not True):
        errors.append("A passed test / inspection result is required")
    pending = db.execute(
        select(func.count())
        .select_from(WOChecklistItem)
        .where(WOChecklistItem.work_order_id == wo.id, WOChecklistItem.is_required.is_(True), WOChecklistItem.is_done.is_(False))
    ).scalar_one()
    if pending:
        errors.append(f"{pending} required checklist item(s) not completed")
    need_codes = _settings(plant).get("require_failure_codes_for", ["corrective", "emergency"])
    if wo.type.value in need_codes and not (wo.problem_code_id and wo.cause_code_id and wo.remedy_code_id):
        errors.append("Problem, cause and remedy codes are required for this work order type")
    from app.services.lubrication import assert_wo_lube_done

    lube_msg = assert_wo_lube_done(db, wo)
    if lube_msg:
        errors.append(lube_msg)
    if wo.type == WOType.EMERGENCY and not wo.root_cause:
        errors.append("Root cause is required for emergency breakdowns")
    if errors:
        raise DomainError("; ".join(errors), "completion_blocked", 409)


def change_status(db: Session, ctx: Ctx, wo: WorkOrder, to: WOStatus, comment: str | None = None) -> WorkOrder:
    plant = ctx.plant
    frm = wo.status
    if frm == to:
        return wo
    t = get_transition(db, plant.id, frm, to)
    if t is None:
        raise DomainError(f"Transition {frm.value} → {to.value} is not allowed", "invalid_transition", 409)
    ctx.require(t.permission)

    # ---- non-configurable business guards ----
    if frm == WOStatus.TRIAGE and to == WOStatus.IN_PROGRESS and wo.type != WOType.EMERGENCY:
        raise DomainError("Only emergency breakdowns may bypass approval", "invalid_transition", 409)
    if to == WOStatus.SCHEDULED and not wo.planned_start:
        raise DomainError("Planned start date is required to schedule", "missing_planned_start", 409)
    if to == WOStatus.IN_PROGRESS and (wo.requires_loto or wo.requires_permit) and not wo.safety_signed_at:
        raise DomainError("LOTO / permit sign-off is required before work starts", "safety_signoff_required", 409)
    if to == WOStatus.IN_PROGRESS and wo.requires_permit and wo.permit_valid_until and wo.permit_valid_until < utcnow():
        raise DomainError("The permit has expired; renew it before work restarts", "permit_expired", 409)
    if to == WOStatus.COMPLETED:
        check_completion_guards(db, plant, wo)
    if to == WOStatus.CLOSED:
        if wo.type == WOType.EMERGENCY:
            ctx.require("wo.close_emergency")
        check_completion_guards(db, plant, wo)
    if to == WOStatus.CANCELLED:
        if not comment:
            raise DomainError("A cancellation reason is required", "reason_required", 422)
        if wo.pm_occurrence_id:
            ctx.require("pm.approve_deferral")  # supervisor approval to cancel a scheduled PM

    now = utcnow()
    wo.status = to
    if to == WOStatus.IN_PROGRESS and wo.actual_start is None:
        wo.actual_start = now
        asset = db.get(Asset, wo.asset_id)
        if asset and wo.type == WOType.EMERGENCY and asset.status == AssetStatus.IN_SERVICE:
            from app.services.assets import change_status as asset_status

            asset_status(db, asset, AssetStatus.UNDER_MAINTENANCE, ctx.user.id, f"Breakdown {wo.number}")
    if to == WOStatus.AWAITING_REVIEW:
        wo.actual_end = wo.actual_end or now
        if wo.supervisor_id:
            notify(
                db,
                plant.id,
                [wo.supervisor_id],
                kind="approval",
                title=f"{wo.number} submitted for review",
                link=f"/work-orders/{wo.id}",
                dedupe_key=f"wo-review:{wo.id}:{now.isoformat()}",
            )
        else:
            notify_permission(
                db,
                plant.id,
                "wo.review",
                department_id=wo.department_id,
                kind="approval",
                title=f"{wo.number} submitted for review",
                link=f"/work-orders/{wo.id}",
                dedupe_key=f"wo-review:{wo.id}:{now.isoformat()}",
            )
    if to == WOStatus.AWAITING_APPROVAL:
        notify_permission(
            db,
            plant.id,
            "wo.approve",
            department_id=wo.department_id,
            kind="approval",
            title=f"{wo.number} awaiting approval",
            link=f"/work-orders/{wo.id}",
            dedupe_key=f"wo-approve:{wo.id}:{now.isoformat()}",
        )
    if to == WOStatus.COMPLETED:
        wo.completed_at = now
        wo.actual_end = wo.actual_end or now
        _on_completed(db, plant, wo, ctx.user.id)
    if to == WOStatus.CLOSED:
        wo.closed_at = now
        _release_reservations(db, wo)
    if to == WOStatus.CANCELLED:
        _release_reservations(db, wo)
        if wo.pm_occurrence_id:
            occ = db.get(PMOccurrence, wo.pm_occurrence_id)
            if occ:
                occ.status = OccurrenceStatus.CANCELLED
                occ.decided_by_id, occ.decided_at, occ.request_reason = ctx.user.id, now, comment

    db.add(
        WOStatusHistory(
            work_order_id=wo.id, from_status=frm.value, to_status=to.value, changed_by_id=ctx.user.id, changed_at=now, comment=comment
        )
    )
    audit(
        db,
        "wo.status",
        user_id=ctx.user.id,
        plant_id=plant.id,
        entity_type="work_order",
        entity_id=wo.id,
        data={"from": frm, "to": to, "comment": comment},
        ip=ctx.ip,
    )
    return wo


def _release_reservations(db: Session, wo: WorkOrder) -> None:
    from app.services.inventory import cancel_reservation

    for r in db.execute(
        select(Reservation).where(Reservation.work_order_id == wo.id, Reservation.status == ReservationStatus.ACTIVE)
    ).scalars():
        cancel_reservation(db, r)


def _on_completed(db: Session, plant: Plant, wo: WorkOrder, user_id: uuid.UUID) -> None:
    from app.services.lubrication import on_wo_completed as lube_done
    from app.services.pm import on_occurrence_completed

    if wo.pm_occurrence_id:
        on_occurrence_completed(db, plant, wo)
    if wo.type == WOType.LUBRICATION:
        lube_done(db, plant, wo, user_id)
    asset = db.get(Asset, wo.asset_id)
    if asset and asset.status == AssetStatus.UNDER_MAINTENANCE:
        others = db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                WorkOrder.asset_id == asset.id,
                WorkOrder.id != wo.id,
                WorkOrder.type == WOType.EMERGENCY,
                WorkOrder.status.in_([WOStatus.IN_PROGRESS, WOStatus.ON_HOLD]),
            )
        ).scalar_one()
        if not others:
            from app.services.assets import change_status as asset_status

            asset_status(db, asset, AssetStatus.IN_SERVICE, user_id, f"Returned to service after {wo.number}")
    # Repeat-failure flag: corrective/emergency on the same asset with the same problem code within N days.
    if wo.type in (WOType.CORRECTIVE, WOType.EMERGENCY) and wo.problem_code_id:
        days = int(_settings(plant).get("repeat_failure_days", 30))
        from datetime import timedelta

        prior = db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                WorkOrder.asset_id == wo.asset_id,
                WorkOrder.id != wo.id,
                WorkOrder.problem_code_id == wo.problem_code_id,
                WorkOrder.type.in_([WOType.CORRECTIVE, WOType.EMERGENCY]),
                WorkOrder.completed_at.is_not(None),
                WorkOrder.completed_at >= (wo.completed_at or utcnow()) - timedelta(days=days),
            )
        ).scalar_one()
        wo.is_repeat_failure = prior > 0


def assign(db: Session, ctx: Ctx, wo: WorkOrder, user_ids: list[uuid.UUID], lead_id: uuid.UUID | None, force: bool = False) -> list[str]:
    """Assign technicians. Hard-blocks people on leave/absence on the planned date; returns warnings for
    overlapping assignments (overridable with force)."""
    warnings: list[str] = []
    if wo.status in (WOStatus.COMPLETED, WOStatus.CLOSED, WOStatus.CANCELLED):
        raise DomainError("Cannot assign a finished work order", "wo_finished", 409)
    work_day = (
        wo.planned_start.astimezone(__import__("zoneinfo").ZoneInfo(ctx.plant.timezone)).date()
        if wo.planned_start
        else plant_today(ctx.plant)
    )
    for uid in user_ids:
        m = db.execute(
            select(Membership).where(Membership.user_id == uid, Membership.plant_id == ctx.plant_id, Membership.is_active.is_(True))
        ).scalar_one_or_none()
        user = db.get(User, uid)
        if m is None or user is None or not user.is_active:
            raise DomainError("Assignee is not an active member of this plant", "invalid_assignee", 422)
        r = db.execute(select(RosterEntry).where(RosterEntry.user_id == uid, RosterEntry.work_date == work_day)).scalar_one_or_none()
        if r is not None and r.kind in (RosterKind.LEAVE, RosterKind.ABSENCE):
            raise DomainError(f"{user.full_name} is on {r.kind.value} on {work_day}", "assignee_unavailable", 409)
        if wo.planned_start and wo.planned_end:
            clash = (
                db.execute(
                    select(WorkOrder.number)
                    .join(WOAssignment, WOAssignment.work_order_id == WorkOrder.id)
                    .where(
                        WOAssignment.user_id == uid,
                        WorkOrder.id != wo.id,
                        WorkOrder.status.in_(OPEN_WO_STATUSES),
                        WorkOrder.planned_start < wo.planned_end,
                        WorkOrder.planned_end > wo.planned_start,
                    )
                )
                .scalars()
                .all()
            )
            if clash:
                warnings.append(f"{user.full_name} already assigned to overlapping {', '.join(clash)}")
    if warnings and not force:
        raise DomainError(
            "Assignment conflicts: " + "; ".join(warnings) + " (resubmit with force=true to override)", "assignment_conflict", 409
        )
    existing = {a.user_id: a for a in wo.assignments}
    for uid in user_ids:
        if uid not in existing:
            wo.assignments.append(WOAssignment(user_id=uid, assigned_at=utcnow(), assigned_by_id=ctx.user.id, is_lead=uid == lead_id))
            notify(
                db,
                ctx.plant_id,
                [uid],
                kind="assignment",
                title=f"Assigned: {wo.number}",
                body=wo.title,
                link=f"/work-orders/{wo.id}",
                dedupe_key=f"wo-assign:{wo.id}",
            )
        else:
            existing[uid].is_lead = uid == lead_id
    audit(
        db,
        "wo.assign",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="work_order",
        entity_id=wo.id,
        data={"users": user_ids, "lead": lead_id, "warnings": warnings},
    )
    return warnings


def add_labor(
    db: Session, ctx: Ctx, wo: WorkOrder, user_id: uuid.UUID, work_date: date, hours: float, is_overtime: bool, notes: str | None
) -> WOLabor:
    if wo.status not in (WOStatus.IN_PROGRESS, WOStatus.ON_HOLD, WOStatus.AWAITING_REVIEW, WOStatus.SCHEDULED, WOStatus.APPROVED):
        raise DomainError("Labor can only be recorded on active work orders", "wo_not_active", 409)
    # Technicians may book only their own time; supervisors may book for anyone assigned.
    if user_id != ctx.user.id and not ctx.has("wo.assign"):
        raise DomainError("You can only record your own labor", "forbidden", 403)
    user = db.get(User, user_id)
    m = db.execute(select(Membership).where(Membership.user_id == user_id, Membership.plant_id == ctx.plant_id)).scalar_one_or_none()
    if user is None or m is None:
        raise DomainError("User is not a member of this plant", "invalid_user", 422)
    s = _settings(ctx.plant)
    rate = Decimal(str(user.hourly_rate if user.hourly_rate is not None else s.get("default_labor_rate", 0)))
    mult = Decimal(str(s.get("overtime_multiplier", 1.5))) if is_overtime else Decimal(1)
    cost = (Decimal(str(hours)) * rate * mult).quantize(Decimal("0.01"))
    lab = WOLabor(
        work_order_id=wo.id,
        user_id=user_id,
        work_date=work_date,
        hours=hours,
        is_overtime=is_overtime,
        rate=rate,
        cost=cost,
        notes=notes,
        created_at=utcnow(),
        created_by_id=ctx.user.id,
    )
    db.add(lab)
    wo.actual_labor_hours = Decimal(str(wo.actual_labor_hours or 0)) + Decimal(str(hours))
    wo.actual_labor_cost = Decimal(str(wo.actual_labor_cost or 0)) + cost
    db.flush()
    return lab


def is_overdue(wo: WorkOrder, today: date) -> bool:
    return wo.status in OPEN_WO_STATUSES and wo.due_date is not None and wo.due_date < today


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
