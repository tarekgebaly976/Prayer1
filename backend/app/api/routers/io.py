import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.core.db import get_db
from app.models.assets import Asset
from app.models.tenancy import Department
from app.models.workorders import WorkOrder
from app.services import imports as imp
from app.services import kpi as kpisvc
from app.services import reports
from app.services.common import plant_today

router = APIRouter(tags=["import/export"])
MAX_IMPORT_BYTES = 10 * 1024 * 1024


def _read(file: UploadFile) -> list[dict]:
    content = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "Import file too large (max 10 MB)")
    try:
        return imp.read_rows(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001 - malformed spreadsheets
        raise HTTPException(422, f"Could not read file: {type(e).__name__}") from e


def _strip(v: dict) -> dict:
    return {
        "total": v["total"],
        "valid": v["valid"],
        "invalid": v["invalid"],
        "errors": v["errors"],
        "warnings": v.get("warnings", []),
        "preview": [{"row": r["row"], "code": r["code"], "ok": not r["errors"]} for r in v["rows"][:200]],
    }


@router.get("/imports/templates/{kind}.xlsx")
def template(kind: str, ctx: Ctx = Depends(require("asset.view"))) -> Response:
    if kind not in imp.TEMPLATES:
        raise HTTPException(404, "Unknown template")
    return Response(
        imp.template_xlsx(kind),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{kind}_import_template.xlsx"'},
    )


@router.post("/imports/assets/preview")
def preview_assets(file: UploadFile = File(...), ctx: Ctx = Depends(require("asset.import")), db: Session = Depends(get_db)) -> dict:
    return _strip(imp.validate_assets(db, ctx.plant, _read(file)))


@router.post("/imports/assets/commit")
def commit_assets(file: UploadFile = File(...), ctx: Ctx = Depends(require("asset.import")), db: Session = Depends(get_db)) -> dict:
    rows = _read(file)
    v = imp.validate_assets(db, ctx.plant, rows)
    if v["invalid"]:
        raise HTTPException(422, {"message": "Import has validation errors; nothing was imported", **_strip(v)})
    return {"created": imp.commit_assets(db, ctx.plant, rows, ctx.user.id)}


@router.post("/imports/parts/preview")
def preview_parts(file: UploadFile = File(...), ctx: Ctx = Depends(require("inventory.manage")), db: Session = Depends(get_db)) -> dict:
    return _strip(imp.validate_parts(db, ctx.plant, _read(file)))


@router.post("/imports/parts/commit")
def commit_parts(file: UploadFile = File(...), ctx: Ctx = Depends(require("inventory.manage")), db: Session = Depends(get_db)) -> dict:
    rows = _read(file)
    v = imp.validate_parts(db, ctx.plant, rows)
    if v["invalid"]:
        raise HTTPException(422, {"message": "Import has validation errors; nothing was imported", **_strip(v)})
    return {"created": imp.commit_parts(db, ctx.plant, rows, ctx.user.id)}


@router.post("/imports/{kind}/errors.csv")
def error_report(
    kind: str, file: UploadFile = File(...), ctx: Ctx = Depends(require("asset.view")), db: Session = Depends(get_db)
) -> Response:
    rows = _read(file)
    if kind == "assets":
        ctx.require("asset.import")
        v = imp.validate_assets(db, ctx.plant, rows)
    elif kind == "parts":
        ctx.require("inventory.manage")
        v = imp.validate_parts(db, ctx.plant, rows)
    else:
        raise HTTPException(404, "Unknown import")
    return Response(
        imp.errors_csv(v["errors"]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{kind}_import_errors.csv"'},
    )


def _csv_safe(v: object) -> object:
    """Neutralise spreadsheet formula injection in exported cells."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


WO_COLS = [
    "number",
    "type",
    "status",
    "priority",
    "asset",
    "department",
    "title",
    "due_date",
    "planned_start",
    "completed_at",
    "estimated_hours",
    "actual_labor_hours",
    "actual_cost",
    "currency",
]


def _wo_rows(db: Session, ctx: Ctx, start: date | None, end: date | None) -> list[list]:
    assets = {a.id: a.code for a in db.execute(select(Asset).where(Asset.plant_id == ctx.plant_id)).scalars()}
    depts = {d.id: d.code for d in db.execute(select(Department).where(Department.plant_id == ctx.plant_id)).scalars()}
    q = select(WorkOrder).where(WorkOrder.plant_id == ctx.plant_id)
    if ctx.department_id:
        q = q.where(WorkOrder.department_id == ctx.department_id)
    s = kpisvc.Scope(plant=ctx.plant, start=start or date(2000, 1, 1), end=end or plant_today(ctx.plant))
    q = q.where(WorkOrder.created_at >= s.t0, WorkOrder.created_at < s.t1)
    out = []
    for w in db.execute(q.order_by(WorkOrder.created_at).limit(100000)).scalars():
        out.append(
            [
                _csv_safe(x)
                for x in [
                    w.number,
                    w.type.value,
                    w.status.value,
                    w.priority.value,
                    assets.get(w.asset_id),
                    depts.get(w.department_id),
                    w.title,
                    w.due_date,
                    w.planned_start,
                    w.completed_at,
                    float(w.estimated_hours) if w.estimated_hours is not None else None,
                    float(w.actual_labor_hours),
                    round(w.actual_cost, 2),
                    w.currency,
                ]
            ]
        )
    return out


@router.get("/exports/work-orders.{fmt}")
def export_wos(
    fmt: str,
    ctx: Ctx = Depends(require("report.export")),
    db: Session = Depends(get_db),
    start: date | None = None,
    end: date | None = None,
) -> Response:
    rows = _wo_rows(db, ctx, start, end)
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(WO_COLS)
        for r in rows:
            w.writerow(["" if x is None else (x.isoformat() if hasattr(x, "isoformat") else x) for x in r])
        return Response(
            "﻿" + buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="work_orders.csv"'}
        )
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Work orders"
        ws.append(WO_COLS)
        for r in rows:
            ws.append([x.replace(tzinfo=None) if hasattr(x, "tzinfo") and getattr(x, "tzinfo", None) else x for x in r])
        b = io.BytesIO()
        wb.save(b)
        return Response(
            b.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="work_orders.xlsx"'},
        )
    raise HTTPException(404, "Unsupported format")


@router.get("/exports/assets.csv")
def export_assets(ctx: Ctx = Depends(require("report.export")), db: Session = Depends(get_db)) -> Response:
    depts = {d.id: d.code for d in db.execute(select(Department).where(Department.plant_id == ctx.plant_id)).scalars()}
    assets = db.execute(select(Asset).where(Asset.plant_id == ctx.plant_id).order_by(Asset.path)).scalars().all()
    codes = {a.id: a.code for a in assets}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "code",
            "name",
            "department_code",
            "parent_code",
            "level",
            "criticality",
            "oem",
            "model",
            "serial_number",
            "install_date",
            "location",
            "status",
        ]
    )
    for a in assets:
        w.writerow(
            [
                _csv_safe(x)
                for x in [
                    a.code,
                    a.name,
                    depts.get(a.department_id),
                    codes.get(a.parent_id) if a.parent_id else "",
                    a.level.value,
                    a.criticality.value,
                    a.oem or "",
                    a.model or "",
                    a.serial_number or "",
                    a.install_date.isoformat() if a.install_date else "",
                    a.location or "",
                    a.status.value,
                ]
            ]
        )
    return Response("﻿" + buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="assets.csv"'})


@router.get("/exports/kpis.xlsx")
def export_kpis(
    ctx: Ctx = Depends(require("report.export")),
    db: Session = Depends(get_db),
    start: date | None = None,
    end: date | None = None,
    department_id: uuid.UUID | None = None,
) -> Response:
    today = plant_today(ctx.plant)
    s = kpisvc.Scope(
        plant=ctx.plant, start=start or today.replace(day=1), end=end or today, department_id=ctx.department_id or department_id
    )
    data = reports.kpi_xlsx(db, s)
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="kpi_report.xlsx"'},
    )


@router.get("/reports/work-orders/{wo_id}.pdf")
def wo_pdf(wo_id: uuid.UUID, ctx: Ctx = Depends(require("wo.view")), db: Session = Depends(get_db)) -> StreamingResponse:
    from app.api.routers.workorders import wo_detail

    detail = wo_detail(wo_id, ctx, db)
    pdf = reports.work_order_pdf(ctx.plant, detail)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{detail["work_order"]["number"]}.pdf"'},
    )


@router.get("/reports/kpis.pdf")
def kpi_pdf(
    ctx: Ctx = Depends(require("report.export")), db: Session = Depends(get_db), start: date | None = None, end: date | None = None
) -> StreamingResponse:
    today = plant_today(ctx.plant)
    s = kpisvc.Scope(plant=ctx.plant, start=start or today.replace(day=1), end=end or today, department_id=ctx.department_id)
    return StreamingResponse(
        io.BytesIO(reports.kpi_pdf(db, s)),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="kpi_report.pdf"'},
    )
