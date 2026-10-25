import io
from datetime import datetime

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.core.kpi_definitions import KPI_DEFINITIONS
from app.models.tenancy import Plant
from app.services import kpi as kpisvc

_styles = getSampleStyleSheet()


def _p(text: object) -> Paragraph:
    from xml.sax.saxutils import escape

    return Paragraph(escape("" if text is None else str(text)), _styles["BodyText"])


def _table(rows: list[list], widths: list[float] | None = None) -> Table:
    t = Table([[_p(c) for c in r] for r in rows], colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b57")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def work_order_pdf(plant: Plant, d: dict) -> bytes:
    """PDF uses Latin fonts; Arabic text is not shaped in PDFs in this version (documented limitation)."""
    wo = d["work_order"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title=wo["number"])
    el = [
        Paragraph(f"Work Order {wo['number']}", _styles["Title"]),
        _p(f"{plant.name} — generated {datetime.now().isoformat(timespec='minutes')}"),
        Spacer(1, 6),
    ]
    a = d.get("asset") or {}
    el.append(
        _table(
            [
                ["Field", "Value"],
                ["Title", wo["title"]],
                ["Type / Priority", f"{wo['type']} / {wo['priority']}"],
                ["Status", wo["status"]],
                ["Asset", f"{a.get('code')} {a.get('name')}"],
                ["Due", wo["due_date"]],
                ["Planned", f"{wo['planned_start']} → {wo['planned_end']}"],
                ["Actual", f"{wo['actual_start']} → {wo['actual_end']}"],
                [
                    "Safety",
                    f"LOTO={wo['requires_loto']} Permit={wo['requires_permit']} ({wo['permit_reference'] or '-'}) "
                    f"signed by {d.get('safety_signed_by') or '-'}",
                ],
                ["Testing", f"required={wo['requires_testing']} passed={wo['test_passed']} {wo['test_result'] or ''}"],
                ["Findings", wo["findings"]],
                ["Root cause", wo["root_cause"]],
                ["Corrective action", wo["corrective_action"]],
                [
                    "Cost",
                    f"labor {wo['actual_labor_cost']} + material {wo['actual_material_cost']} + services "
                    f"{wo['actual_service_cost']} = {wo['actual_cost']} {wo['currency']}",
                ],
            ],
            [45 * mm, 135 * mm],
        )
    )
    if d["checklist"]:
        el += [
            Spacer(1, 8),
            Paragraph("Checklist", _styles["Heading2"]),
            _table(
                [["#", "Task", "Done", "OK", "Reading"]]
                + [[c["seq"], c["description"], c["is_done"], c["is_ok"], c["reading_value"]] for c in d["checklist"]],
                [10 * mm, 100 * mm, 20 * mm, 20 * mm, 30 * mm],
            ),
        ]
    if d["labor"]:
        el += [
            Spacer(1, 8),
            Paragraph("Labor", _styles["Heading2"]),
            _table([["Date", "Technician", "Hours", "Cost"]] + [[x["work_date"], x["name"], x["hours"], x["cost"]] for x in d["labor"]]),
        ]
    if d["transactions"]:
        el += [
            Spacer(1, 8),
            Paragraph("Materials", _styles["Heading2"]),
            _table(
                [["Part", "Type", "Qty", "Unit cost", "Total"]]
                + [[t["part_code"], t["type"], t["quantity"], t["unit_cost"], t["total_cost"]] for t in d["transactions"]]
            ),
        ]
    el += [
        Spacer(1, 8),
        Paragraph("Approval history", _styles["Heading2"]),
        _table([["When", "From", "To", "By", "Comment"]] + [[h["at"], h["from"], h["to"], h["by"], h["comment"]] for h in d["history"]]),
    ]
    doc.build(el)
    return buf.getvalue()


def _fmt(k: dict) -> str:
    return "n/a — " + (k["reason"] or "") if not k["available"] else f"{k['value']} {k['unit']}"


def kpi_pdf(db: Session, s: kpisvc.Scope) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title="KPI report")
    names = {d["code"]: d["name"] for d in KPI_DEFINITIONS}
    rows = [["KPI", "Value"]] + [[names.get(k["code"], k["code"]), _fmt(k)] for k in kpisvc.compute_all(db, s)]
    doc.build(
        [
            Paragraph("Maintenance KPI report", _styles["Title"]),
            _p(
                f"{s.plant.name} — period {s.start} to {s.end}. Values are computed from recorded data only; "
                "unavailable KPIs show the reason."
            ),
            Spacer(1, 6),
            _table(rows, [70 * mm, 110 * mm]),
        ]
    )
    return buf.getvalue()


def kpi_xlsx(db: Session, s: kpisvc.Scope) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "KPIs"
    ws.append(["Plant", s.plant.name, "Period", str(s.start), str(s.end)])
    ws.append(["code", "name", "value", "unit", "available", "reason", "numerator", "denominator", "formula"])
    defs = {d["code"]: d for d in KPI_DEFINITIONS}
    for k in kpisvc.compute_all(db, s):
        d = defs.get(k["code"], {})
        ws.append(
            [
                k["code"],
                d.get("name"),
                k["value"],
                k["unit"],
                k["available"],
                k["reason"],
                k["numerator"],
                k["denominator"],
                d.get("formula"),
            ]
        )
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()
