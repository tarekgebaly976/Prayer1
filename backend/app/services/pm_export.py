"""PM / PdM plans to Excel, so planners can copy plan codes and build a work-plan import.

Sheet "work_plan" (first, so the file imports as it is): the Import work plan layout, one row per waiting occurrence (no
work order yet) in the coming weeks; delete the rows you do not want and import. Sheet "pm_plans": every plan with its
code and schedule."""

import io
from datetime import timedelta
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.enums import OccurrenceStatus, PMTrigger
from app.models.pm import JobPlan, PMOccurrence, PMPlan
from app.models.tenancy import Department, Plant
from app.services.common import plant_today
from app.services.imports import TEMPLATES

WAITING = [OccurrenceStatus.SCHEDULED, OccurrenceStatus.DEFERRED]


def plans_xlsx(db: Session, plant: Plant, dept_where: Any, days_ahead: int = 60) -> bytes:
    today = plant_today(plant)
    rows = db.execute(
        select(PMPlan, Asset, Department, JobPlan)
        .join(Asset, Asset.id == PMPlan.asset_id)
        .outerjoin(Department, Department.id == Asset.department_id)
        .outerjoin(JobPlan, JobPlan.id == PMPlan.job_plan_id)
        .where(PMPlan.plant_id == plant.id, dept_where(Asset.department_id))
        .order_by(Department.code, PMPlan.code)
    ).all()
    waiting = dict(
        db.execute(
            select(PMOccurrence.pm_plan_id, func.count())
            .where(PMOccurrence.plant_id == plant.id, PMOccurrence.work_order_id.is_(None), PMOccurrence.status.in_(WAITING))
            .group_by(PMOccurrence.pm_plan_id)
        ).all()
    )
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "pm_plans"
    head = ["code", "name", "type", "asset_code", "department", "frequency", "trade", "estimated_hours", "next_due", "last_completed",
            "active", "waiting_occurrences"]  # fmt: skip
    ws.append(head)
    for plan, asset, dept, jp in rows:
        if plan.trigger == PMTrigger.CALENDAR:
            freq = f"{plan.frequency_interval} {plan.frequency_unit.value if plan.frequency_unit else ''}".strip()
        else:
            freq = f"every {plan.meter_interval} (meter)"
        ws.append(
            [
                plan.code,
                plan.name,
                plan.wo_type.value,
                asset.code,
                dept.code if dept else None,
                freq,
                jp.trade if jp else None,
                float(jp.estimated_hours) if jp else None,
                plan.next_due_date,
                plan.last_completed_date,
                "yes" if plan.is_active else "no",
                waiting.get(plan.id, 0),
            ]
        )
    # Ready-to-import work plan: waiting occurrences in the coming weeks.
    wp = wb.create_sheet("work_plan")
    cols = [c for c, _ in TEMPLATES["work_orders"]]
    wp.append(cols)
    plan_ids = [p.id for p, *_ in rows if p.is_active]
    if plan_ids:
        occs = db.execute(
            select(PMOccurrence, PMPlan, Asset)
            .join(PMPlan, PMPlan.id == PMOccurrence.pm_plan_id)
            .join(Asset, Asset.id == PMPlan.asset_id)
            .where(
                PMOccurrence.pm_plan_id.in_(plan_ids),
                PMOccurrence.work_order_id.is_(None),
                PMOccurrence.status.in_(WAITING),
                PMOccurrence.due_date <= today + timedelta(days=days_ahead),
            )
            .order_by(PMOccurrence.due_date, PMPlan.code)
        ).all()
        for occ, plan, asset in occs:
            row = dict.fromkeys(cols)
            row.update({"asset_code": asset.code, "title": f"{plan.code} {plan.name}"[:200], "priority": plan.priority.value,
                        "due_date": occ.due_date, "pm_plan_code": plan.code})  # fmt: skip
            wp.append([row[c] for c in cols])
    for sheet in (ws, wp):
        for c in sheet[1]:
            c.font = Font(bold=True)
        for col in sheet.columns:
            width = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 50)
        sheet.freeze_panes = "A2"
    wb.move_sheet(wp, offset=-1)  # first sheet: the file can be imported as it is (imports read the first sheet)
    info = wb.create_sheet("instructions")
    for line in (
        ["pm_plans", "All PM / PdM plans you can see, with the code to use in pm_plan_code."],
        [
            "work_plan",
            f"Waiting occurrences (no work order yet) due in the next {days_ahead} days, already in the Import work plan layout.",
        ],
        ["", "Delete the rows you do not want, add technicians in assign_to (e-mail), save, then Work orders > Import work plan."],
    ):
        info.append(line)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
