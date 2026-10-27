"""QR label sheets: A4 with 24 labels (3 columns × 8 rows of 70 × 37 mm, no page margin), the common
self-adhesive sheet. Each label: the QR code the in-app scanner reads, the code in bold, the name, one sub-line."""

import io
import re
from dataclasses import dataclass
from datetime import datetime

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

COLS, ROWS = 3, 8
LABEL_W, LABEL_H = 70 * mm, 37 * mm
PER_SHEET = COLS * ROWS
MAX_LABELS = 100 * PER_SHEET  # 100 sheets per print run
PAD = 2.5 * mm
QR_SIZE = LABEL_H - 2 * PAD


@dataclass
class Label:
    payload: str  # what the QR holds, e.g. "cmms:asset:<token>"
    code: str
    name: str
    sub: str = ""


def _fit(text: str, font: str, size: float, width: float, max_lines: int) -> list[str]:
    """Greedy word wrap; the last line is cut with an ellipsis if the text does not fit."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if stringWidth(trial, font, size) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = w
        while stringWidth(cur, font, size) > width:  # a single word longer than the line
            cut = len(cur)
            while cut > 1 and stringWidth(cur[:cut], font, size) > width:
                cut -= 1
            lines.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and stringWidth(last + "…", font, size) > width:
            last = last[:-1]
        lines = lines[: max_lines - 1] + [last.rstrip() + "…"]
    return lines


def _tail(text: str, font: str, size: float, width: float) -> str:
    """One line keeping the END of the text (e.g. the most specific part of a location path)."""
    if stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth("…" + text, font, size) > width:
        text = text[1:]
    return "…" + text.lstrip()


def file_name(subject: str) -> str:
    """A different name for every download (subject + time), so phones never open an older copy of the file."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", subject).strip("-")[:40] or "labels"
    return f"QR_labels_{safe}_{datetime.now():%Y%m%d-%H%M%S}.pdf"


def sheet_pdf(labels: list[Label], skip: int = 0, title: str = "QR labels") -> bytes:
    """`skip` leaves the first positions of the first sheet empty (a partly used sheet)."""
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    c.setTitle(title)
    page_w, page_h = A4
    left = (page_w - COLS * LABEL_W) / 2
    top = page_h - (page_h - ROWS * LABEL_H) / 2
    text_x0 = PAD + QR_SIZE + 2 * mm
    text_w = LABEL_W - text_x0 - PAD
    slot = skip % PER_SHEET
    for lab in labels:
        if slot == PER_SHEET:
            c.showPage()
            slot = 0
        col, row = slot % COLS, slot // COLS
        x, y = left + col * LABEL_W, top - (row + 1) * LABEL_H
        qr = QrCodeWidget(lab.payload, barLevel="M")
        bx0, by0, bx1, by1 = qr.getBounds()
        d = Drawing(QR_SIZE, QR_SIZE, transform=[QR_SIZE / (bx1 - bx0), 0, 0, QR_SIZE / (by1 - by0), 0, 0])
        d.add(qr)
        renderPDF.draw(d, c, x + PAD, y + PAD)
        ty = y + LABEL_H - PAD - 9
        code_lines = _fit(lab.code, "Helvetica-Bold", 9, text_w, 2)
        for line in code_lines:
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x + text_x0, ty, line)
            ty -= 10.5
        ty -= 1
        for line in _fit(lab.name, "Helvetica", 7.5, text_w, 5 - len(code_lines)):
            c.setFont("Helvetica", 7.5)
            c.drawString(x + text_x0, ty, line)
            ty -= 8.8
        if lab.sub:
            c.setFont("Helvetica", 6.5)
            c.setFillGray(0.35)
            c.drawString(x + text_x0, y + PAD + 1, _tail(lab.sub, "Helvetica", 6.5, text_w))
            c.setFillGray(0)
        slot += 1
    if not labels:
        c.setFont("Helvetica", 12)
        c.drawString(30 * mm, page_h - 30 * mm, "No labels match the selection.")
    c.showPage()
    c.save()
    return buf.getvalue()
