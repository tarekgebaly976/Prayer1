import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Ctx, require
from app.api.pagination import PageQ, paginate
from app.core.db import get_db
from app.core.errors import DomainError
from app.models.enums import Criticality, POStatus, TxnType
from app.models.inventory import (
    InventoryTransaction,
    Part,
    PartSubstitute,
    PurchaseOrder,
    PurchaseOrderLine,
    Reservation,
    StockLevel,
    Supplier,
    Warehouse,
)
from app.schemas.common import ORM, In
from app.services import inventory as svc
from app.services.common import audit, next_number, utcnow

router = APIRouter(prefix="/inventory", tags=["inventory"])


class WarehouseIn(In):
    code: str
    name: str


@router.get("/warehouses")
def list_wh(ctx: Ctx = Depends(require("inventory.view")), db: Session = Depends(get_db)) -> list[dict]:
    return [
        {"id": w.id, "code": w.code, "name": w.name}
        for w in db.execute(select(Warehouse).where(Warehouse.plant_id == ctx.plant_id).order_by(Warehouse.code)).scalars()
    ]


@router.post("/warehouses", status_code=201)
def create_wh(body: WarehouseIn, ctx: Ctx = Depends(require("inventory.manage")), db: Session = Depends(get_db)) -> dict:
    w = Warehouse(plant_id=ctx.plant_id, **body.model_dump())
    db.add(w)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Warehouse code exists") from e
    return {"id": w.id}


class SupplierIn(In):
    code: str
    name: str
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    is_contractor: bool = False
    default_lead_time_days: int | None = Field(None, ge=0)


@router.get("/suppliers")
def list_suppliers(ctx: Ctx = Depends(require("inventory.view")), db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "is_contractor": s.is_contractor,
            "email": s.email,
            "default_lead_time_days": s.default_lead_time_days,
        }
        for s in db.execute(select(Supplier).where(Supplier.plant_id == ctx.plant_id).order_by(Supplier.code)).scalars()
    ]


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, ctx: Ctx = Depends(require("purchase.manage")), db: Session = Depends(get_db)) -> dict:
    s = Supplier(plant_id=ctx.plant_id, **body.model_dump())
    db.add(s)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Supplier code exists") from e
    return {"id": s.id}


class PartIn(In):
    code: str = Field(min_length=1, max_length=60)
    description: str
    description_ar: str | None = None
    oem_part_number: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    uom: str = "EA"
    criticality: Criticality = Criticality.C
    is_critical_spare: bool = False
    min_qty: float = Field(0, ge=0)
    max_qty: float = Field(0, ge=0)
    safety_stock: float = Field(0, ge=0)
    reorder_point: float = Field(0, ge=0)
    lead_time_days: int | None = Field(None, ge=0)
    preferred_supplier_id: uuid.UUID | None = None
    unit_price: float = Field(0, ge=0)
    currency: str | None = None


class PartUpdate(In):
    description: str | None = None
    description_ar: str | None = None
    oem_part_number: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    criticality: Criticality | None = None
    is_critical_spare: bool | None = None
    min_qty: float | None = Field(None, ge=0)
    max_qty: float | None = Field(None, ge=0)
    safety_stock: float | None = Field(None, ge=0)
    reorder_point: float | None = Field(None, ge=0)
    lead_time_days: int | None = Field(None, ge=0)
    preferred_supplier_id: uuid.UUID | None = None
    is_obsolete: bool | None = None


class PartOut(ORM):
    id: uuid.UUID
    code: str
    description: str
    description_ar: str | None
    oem_part_number: str | None
    manufacturer: str | None
    category: str | None
    uom: str
    criticality: Criticality
    is_critical_spare: bool
    min_qty: float
    max_qty: float
    safety_stock: float
    reorder_point: float
    lead_time_days: int | None
    preferred_supplier_id: uuid.UUID | None
    unit_price: float
    average_cost: float
    currency: str
    is_obsolete: bool
    last_issue_at: datetime | None


def _part(db: Session, ctx: Ctx, pid: uuid.UUID) -> Part:
    p = db.get(Part, pid)
    if p is None or p.plant_id != ctx.plant_id:
        raise HTTPException(404, "Part not found")
    return p


def _wh(db: Session, ctx: Ctx, wid: uuid.UUID) -> Warehouse:
    w = db.get(Warehouse, wid)
    if w is None or w.plant_id != ctx.plant_id:
        raise HTTPException(404, "Warehouse not found")
    return w


@router.get("/parts")
def list_parts(
    ctx: Ctx = Depends(require("inventory.view")),
    db: Session = Depends(get_db),
    page: PageQ = Depends(),
    q: str | None = None,
    critical_only: bool = False,
    below_reorder: bool = False,
) -> dict:
    stmt = select(Part).where(Part.plant_id == ctx.plant_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Part.code.ilike(like), Part.description.ilike(like), Part.oem_part_number.ilike(like)))
    if critical_only:
        stmt = stmt.where(Part.is_critical_spare.is_(True))
    if below_reorder:
        onhand = (
            select(func.coalesce(func.sum(StockLevel.qty_on_hand - StockLevel.qty_reserved), 0))
            .where(StockLevel.part_id == Part.id)
            .correlate(Part)
            .scalar_subquery()
        )
        stmt = stmt.where(Part.reorder_point > 0, onhand <= Part.reorder_point)
    res = paginate(db, stmt.order_by(Part.code), page, PartOut)
    ids = [p.id for p in res["items"]]
    if ids:
        agg = {
            pid: (oh, rs)
            for pid, oh, rs in db.execute(
                select(StockLevel.part_id, func.sum(StockLevel.qty_on_hand), func.sum(StockLevel.qty_reserved))
                .where(StockLevel.part_id.in_(ids))
                .group_by(StockLevel.part_id)
            ).all()
        }
        items = []
        for p in res["items"]:
            oh, rs = agg.get(p.id, (0, 0))
            items.append(
                {
                    **p.model_dump(),
                    "qty_on_hand": float(oh or 0),
                    "qty_reserved": float(rs or 0),
                    "qty_available": float((oh or 0) - (rs or 0)),
                    "qty_on_order": float(svc.on_order_qty(db, p.id)),
                }
            )
        res["items"] = items
    return res


@router.post("/parts", response_model=PartOut, status_code=201)
def create_part(body: PartIn, ctx: Ctx = Depends(require("inventory.manage")), db: Session = Depends(get_db)) -> Part:
    if body.max_qty and body.min_qty > body.max_qty:
        raise HTTPException(422, "min_qty cannot exceed max_qty")
    data = body.model_dump()
    data["currency"] = data["currency"] or ctx.plant.currency
    p = Part(plant_id=ctx.plant_id, created_by_id=ctx.user.id, average_cost=body.unit_price, **data)
    db.add(p)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Part code exists") from e
    audit(db, "part.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="part", entity_id=p.id)
    return p


@router.get("/parts/{pid}")
def get_part(pid: uuid.UUID, ctx: Ctx = Depends(require("inventory.view")), db: Session = Depends(get_db)) -> dict:
    from app.models.assets import Asset, AssetBOM

    p = _part(db, ctx, pid)
    levels = db.execute(
        select(StockLevel, Warehouse).join(Warehouse, Warehouse.id == StockLevel.warehouse_id).where(StockLevel.part_id == p.id)
    ).all()
    subs = (
        db.execute(select(Part).join(PartSubstitute, PartSubstitute.substitute_id == Part.id).where(PartSubstitute.part_id == p.id))
        .scalars()
        .all()
    )
    used_on = db.execute(
        select(Asset.id, Asset.code, Asset.name, AssetBOM.quantity)
        .join(AssetBOM, AssetBOM.asset_id == Asset.id)
        .where(AssetBOM.part_id == p.id)
    ).all()
    res = db.execute(select(Reservation).where(Reservation.part_id == p.id, Reservation.status == "active")).scalars().all()
    return {
        **PartOut.model_validate(p).model_dump(mode="json"),
        "stock": [
            {
                "warehouse_id": w.id,
                "warehouse": w.code,
                "bin": s.bin,
                "on_hand": float(s.qty_on_hand),
                "reserved": float(s.qty_reserved),
                "available": float(s.qty_on_hand - s.qty_reserved),
            }
            for s, w in levels
        ],
        "on_order": float(svc.on_order_qty(db, p.id)),
        "substitutes": [{"id": s.id, "code": s.code, "description": s.description} for s in subs],
        "used_on": [{"asset_id": i, "code": c, "name": n, "quantity": float(q)} for i, c, n, q in used_on],
        "active_reservations": [
            {"id": r.id, "work_order_id": r.work_order_id, "quantity": float(r.quantity), "qty_issued": float(r.qty_issued)} for r in res
        ],
    }


@router.patch("/parts/{pid}", response_model=PartOut)
def update_part(pid: uuid.UUID, body: PartUpdate, ctx: Ctx = Depends(require("inventory.manage")), db: Session = Depends(get_db)) -> Part:
    p = _part(db, ctx, pid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    audit(
        db,
        "part.update",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="part",
        entity_id=p.id,
        data=body.model_dump(exclude_unset=True),
    )
    return p


class SubIn(In):
    substitute_id: uuid.UUID
    notes: str | None = None


@router.post("/parts/{pid}/substitutes", status_code=201)
def add_sub(pid: uuid.UUID, body: SubIn, ctx: Ctx = Depends(require("inventory.manage")), db: Session = Depends(get_db)) -> dict:
    p, s = _part(db, ctx, pid), _part(db, ctx, body.substitute_id)
    if p.id == s.id:
        raise HTTPException(422, "A part cannot substitute itself")
    db.add(PartSubstitute(part_id=p.id, substitute_id=s.id, approved_by_id=ctx.user.id, notes=body.notes))
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(409, "Substitute already recorded") from e
    return {"ok": True}


class ReceiptIn(In):
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: float = Field(gt=0)
    unit_cost: float = Field(ge=0)
    reference: str | None = None
    po_line_id: uuid.UUID | None = None


@router.post("/receipts", status_code=201)
def receipt(body: ReceiptIn, ctx: Ctx = Depends(require("inventory.transact")), db: Session = Depends(get_db)) -> dict:
    p, w = _part(db, ctx, body.part_id), _wh(db, ctx, body.warehouse_id)
    line = None
    if body.po_line_id:
        line = db.execute(
            select(PurchaseOrderLine).where(PurchaseOrderLine.id == body.po_line_id).with_for_update(key_share=True)
        ).scalar_one_or_none()
        po = db.get(PurchaseOrder, line.purchase_order_id) if line else None
        if line is None or po is None or po.plant_id != ctx.plant_id or line.part_id != p.id:
            raise HTTPException(422, "PO line not found for this part")
        if po.status in (POStatus.CANCELLED, POStatus.RECEIVED, POStatus.DRAFT):
            raise DomainError(f"Cannot receive against a {po.status.value} purchase order", "invalid_po", 409)
        if float(line.qty_received) + body.quantity > float(line.quantity) * 1.1:
            raise DomainError("Receipt exceeds ordered quantity by more than 10%", "over_receipt", 409)
    tx = svc.receive(db, ctx.plant, p, w, body.quantity, body.unit_cost, ctx.user.id, body.reference, line)
    audit(
        db,
        "inventory.receipt",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="inventory_txn",
        entity_id=tx.id,
        data={"part": p.code, "qty": body.quantity, "cost": body.unit_cost},
    )
    return {"transaction_id": tx.id, "balance_after": float(tx.balance_after), "average_cost": float(p.average_cost)}


class AdjustIn(In):
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    delta: float
    reason: str = Field(min_length=5)


@router.post("/adjustments", status_code=201)
def adjustment(body: AdjustIn, ctx: Ctx = Depends(require("inventory.adjust")), db: Session = Depends(get_db)) -> dict:
    p, w = _part(db, ctx, body.part_id), _wh(db, ctx, body.warehouse_id)
    tx = svc.adjust(db, ctx.plant, p, w, body.delta, body.reason, ctx.user.id)
    audit(
        db,
        "inventory.adjust",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type="inventory_txn",
        entity_id=tx.id,
        data=body.model_dump(),
    )
    return {"transaction_id": tx.id, "balance_after": float(tx.balance_after)}


class IssueIn(In):
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: float = Field(gt=0)
    reference: str = Field(min_length=2, description="Cost centre / purpose for issues not linked to a WO")


@router.post("/issues", status_code=201)
def issue_no_wo(body: IssueIn, ctx: Ctx = Depends(require("inventory.transact")), db: Session = Depends(get_db)) -> dict:
    p, w = _part(db, ctx, body.part_id), _wh(db, ctx, body.warehouse_id)
    tx = svc.issue(db, ctx.plant, p, w, body.quantity, ctx.user.id, reference=body.reference)
    audit(db, "inventory.issue", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="inventory_txn", entity_id=tx.id)
    return {"transaction_id": tx.id, "balance_after": float(tx.balance_after)}


class TransferIn(In):
    part_id: uuid.UUID
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    quantity: float = Field(gt=0)


@router.post("/transfers", status_code=201)
def transfer(body: TransferIn, ctx: Ctx = Depends(require("inventory.transact")), db: Session = Depends(get_db)) -> dict:
    p = _part(db, ctx, body.part_id)
    svc.transfer(db, ctx.plant, p, _wh(db, ctx, body.from_warehouse_id), _wh(db, ctx, body.to_warehouse_id), body.quantity, ctx.user.id)
    audit(db, "inventory.transfer", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="part", entity_id=p.id, data=body.model_dump())
    return {"ok": True}


class TxnOut(ORM):
    id: uuid.UUID
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    type: TxnType
    quantity: float
    unit_cost: float
    total_cost: float
    balance_after: float
    work_order_id: uuid.UUID | None
    reference: str | None
    reason: str | None
    created_by_id: uuid.UUID | None
    created_at: datetime


@router.get("/transactions")
def transactions(
    ctx: Ctx = Depends(require("inventory.view")),
    db: Session = Depends(get_db),
    page: PageQ = Depends(),
    part_id: uuid.UUID | None = None,
    work_order_id: uuid.UUID | None = None,
    type: TxnType | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    q = select(InventoryTransaction).where(InventoryTransaction.plant_id == ctx.plant_id)
    if part_id:
        q = q.where(InventoryTransaction.part_id == part_id)
    if work_order_id:
        q = q.where(InventoryTransaction.work_order_id == work_order_id)
    if type:
        q = q.where(InventoryTransaction.type == type)
    if start:
        q = q.where(InventoryTransaction.created_at >= datetime.combine(start, datetime.min.time()))
    if end:
        q = q.where(InventoryTransaction.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time()))
    return paginate(db, q.order_by(InventoryTransaction.created_at.desc()), page, TxnOut)


@router.get("/valuation")
def valuation(ctx: Ctx = Depends(require("inventory.view")), db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(Part.code, Part.description, Part.average_cost, func.sum(StockLevel.qty_on_hand))
        .join(StockLevel, StockLevel.part_id == Part.id)
        .where(Part.plant_id == ctx.plant_id)
        .group_by(Part.id)
        .order_by(Part.code)
    ).all()
    items = [
        {"code": c, "description": d, "average_cost": float(a), "on_hand": float(q or 0), "value": round(float(a) * float(q or 0), 2)}
        for c, d, a, q in rows
    ]
    return {"currency": ctx.plant.currency, "total_value": round(sum(i["value"] for i in items), 2), "items": items}


@router.get("/aging")
def aging(
    ctx: Ctx = Depends(require("inventory.view")), db: Session = Depends(get_db), slow_days: int = 180, obsolete_days: int = 730
) -> dict:
    now = utcnow()
    rows = db.execute(
        select(Part, func.sum(StockLevel.qty_on_hand))
        .join(StockLevel, StockLevel.part_id == Part.id)
        .where(Part.plant_id == ctx.plant_id)
        .group_by(Part.id)
    ).all()
    out: dict[str, list] = {"slow_moving": [], "obsolete_candidates": [], "excess": [], "no_movement_recorded": []}
    for p, qty in rows:
        qty = float(qty or 0)
        if qty <= 0:
            continue
        rec = {
            "id": p.id,
            "code": p.code,
            "description": p.description,
            "on_hand": qty,
            "value": round(qty * float(p.average_cost), 2),
            "last_issue_at": p.last_issue_at,
            "is_critical_spare": p.is_critical_spare,
        }
        last = p.last_issue_at or p.last_receipt_at
        if last is None:
            out["no_movement_recorded"].append(rec)
        elif p.is_obsolete or last < now - timedelta(days=obsolete_days):
            out["obsolete_candidates"].append(rec)
        elif last < now - timedelta(days=slow_days):
            out["slow_moving"].append(rec)
        if float(p.max_qty) > 0 and qty > float(p.max_qty):
            out["excess"].append({**rec, "max_qty": float(p.max_qty), "excess_qty": qty - float(p.max_qty)})
    out["note"] = ["Critical spares are flagged but should not be disposed of on movement criteria alone."]
    return out


# ---------------- purchase requisitions / PO references ----------------
class POLineIn(In):
    part_id: uuid.UUID
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    work_order_id: uuid.UUID | None = None


class POIn(In):
    supplier_id: uuid.UUID | None = None
    external_reference: str | None = None
    expected_date: date | None = None
    notes: str | None = None
    lines: list[POLineIn] = Field(min_length=1)


@router.get("/purchase-orders")
def list_pos(ctx: Ctx = Depends(require("inventory.view")), db: Session = Depends(get_db), status: POStatus | None = None) -> list[dict]:
    q = select(PurchaseOrder).where(PurchaseOrder.plant_id == ctx.plant_id)
    if status:
        q = q.where(PurchaseOrder.status == status)
    out = []
    for po in db.execute(q.order_by(PurchaseOrder.created_at.desc()).limit(500)).scalars():
        lines = db.execute(
            select(PurchaseOrderLine, Part)
            .join(Part, Part.id == PurchaseOrderLine.part_id)
            .where(PurchaseOrderLine.purchase_order_id == po.id)
        ).all()
        out.append(
            {
                "id": po.id,
                "number": po.number,
                "status": po.status,
                "supplier_id": po.supplier_id,
                "external_reference": po.external_reference,
                "expected_date": po.expected_date,
                "lines": [
                    {
                        "id": ln.id,
                        "part_id": p.id,
                        "part_code": p.code,
                        "quantity": float(ln.quantity),
                        "qty_received": float(ln.qty_received),
                        "unit_price": float(ln.unit_price),
                    }
                    for ln, p in lines
                ],
            }
        )
    return out


@router.post("/purchase-orders", status_code=201)
def create_po(body: POIn, ctx: Ctx = Depends(require("purchase.manage")), db: Session = Depends(get_db)) -> dict:
    if body.supplier_id:
        s = db.get(Supplier, body.supplier_id)
        if s is None or s.plant_id != ctx.plant_id:
            raise HTTPException(422, "Supplier not found")
    po = PurchaseOrder(
        plant_id=ctx.plant_id,
        number=next_number(db, ctx.plant, "PO"),
        currency=ctx.plant.currency,
        created_by_id=ctx.user.id,
        **body.model_dump(exclude={"lines"}),
    )
    db.add(po)
    db.flush()
    for ln in body.lines:
        _part(db, ctx, ln.part_id)
        db.add(PurchaseOrderLine(purchase_order_id=po.id, **ln.model_dump()))
    audit(db, "po.create", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="purchase_order", entity_id=po.id)
    return {"id": po.id, "number": po.number}


class POStatusIn(In):
    status: POStatus
    external_reference: str | None = None


@router.post("/purchase-orders/{po_id}/status")
def po_status(po_id: uuid.UUID, body: POStatusIn, ctx: Ctx = Depends(require("purchase.manage")), db: Session = Depends(get_db)) -> dict:
    po = db.get(PurchaseOrder, po_id)
    if po is None or po.plant_id != ctx.plant_id:
        raise HTTPException(404, "PO not found")
    allowed = {
        POStatus.DRAFT: {POStatus.REQUESTED, POStatus.CANCELLED},
        POStatus.REQUESTED: {POStatus.ORDERED, POStatus.CANCELLED},
        POStatus.ORDERED: {POStatus.CANCELLED},
        POStatus.PARTIAL: {POStatus.CANCELLED},
    }
    if body.status not in allowed.get(po.status, set()):
        raise DomainError(f"Cannot move PO from {po.status.value} to {body.status.value}", "invalid_transition", 409)
    po.status = body.status
    if body.external_reference:
        po.external_reference = body.external_reference
    audit(
        db, "po.status", user_id=ctx.user.id, plant_id=ctx.plant_id, entity_type="purchase_order", entity_id=po.id, data=body.model_dump()
    )
    return {"status": po.status}
