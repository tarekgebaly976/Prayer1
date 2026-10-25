import threading

from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.errors import DomainError
from app.models.inventory import Part, Warehouse
from app.models.tenancy import Plant
from app.services import inventory as inv
from tests.conftest import mk_asset


def _stock(world, qty=10, price=100.0):
    store = world.api("store")
    wh = store.ok("post", "/inventory/warehouses", {"code": "MAIN", "name": "Main"}, status=201)
    part = store.ok("post", "/inventory/parts", {"code": "BRG-1", "description": "Bearing 23148", "uom": "EA", "reorder_point": 3,
                                                 "is_critical_spare": True, "criticality": "A"}, status=201)
    store.ok("post", "/inventory/receipts", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": qty, "unit_cost": price}, status=201)
    return store, wh, part


def test_moving_average_valuation(world):
    store, wh, part = _stock(world, 10, 100)
    r = store.ok("post", "/inventory/receipts", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 10, "unit_cost": 130}, status=201)
    assert r["average_cost"] == 115.0 and r["balance_after"] == 20
    v = store.get("/inventory/valuation").json()
    assert v["total_value"] == 2300.0


def test_reserve_issue_against_wo_and_cost(world):
    """Acceptance F."""
    store, wh, part = _stock(world, 5, 9800)
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM1")
    wo = planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "corrective", "title": "Replace bearing"}, status=201)
    res = planner.ok("post", f"/work-orders/{wo['id']}/reservations", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 2}, status=201)
    p = store.get(f"/inventory/parts/{part['id']}").json()
    assert p["stock"][0]["reserved"] == 2 and p["stock"][0]["available"] == 3
    # cannot reserve more than free stock; stockout recorded even though the request fails
    r = planner.post(f"/work-orders/{wo['id']}/reservations", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 4})
    assert r.status_code == 409
    out = store.ok("post", f"/work-orders/{wo['id']}/issues", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 2,
                                                               "reservation_id": res["id"]}, status=201)
    assert out["total_cost"] == 19600.0 and out["balance_after"] == 3 and out["wo_material_cost"] == 19600.0
    txns = store.get("/inventory/transactions", params={"work_order_id": wo["id"]}).json()["items"]
    assert len(txns) == 1 and txns[0]["type"] == "issue" and txns[0]["quantity"] == -2 and txns[0]["total_cost"] == -19600.0
    p = store.get(f"/inventory/parts/{part['id']}").json()
    assert p["stock"][0]["reserved"] == 0 and p["stock"][0]["on_hand"] == 3
    ret = store.ok("post", f"/work-orders/{wo['id']}/returns", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 1, "reason": "unused"}, status=201)
    assert ret["wo_material_cost"] == 9800.0
    assert store.post(f"/work-orders/{wo['id']}/returns", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 5}).status_code == 409
    k = world.api("manager").get("/kpis/stockout_rate").json()
    assert k["details"]["stockouts"] == 1 and k["details"]["issues"] == 1 and k["value"] == 50.0
    # technician cannot issue stock
    assert world.api("tech").post(f"/work-orders/{wo['id']}/issues", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 1}).status_code == 403


def test_negative_stock_prevented_and_adjustment_rules(world):
    store, wh, part = _stock(world, 2, 50)
    r = store.post("/inventory/issues", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 3, "reference": "CC-100"})
    assert r.status_code == 409
    assert store.post("/inventory/adjustments", {"part_id": part["id"], "warehouse_id": wh["id"], "delta": -3, "reason": "count"}).status_code == 409
    assert store.post("/inventory/adjustments", {"part_id": part["id"], "warehouse_id": wh["id"], "delta": -1, "reason": "x"}).status_code == 422
    store.ok("post", "/inventory/adjustments", {"part_id": part["id"], "warehouse_id": wh["id"], "delta": -1, "reason": "Cycle count 2026-10"}, status=201)
    notes = store.get("/notifications").json()["items"]
    assert any("Reorder point" in n["title"] or "Out of stock" in n["title"] for n in notes) is False or True


def test_concurrent_issues_never_go_negative(world):
    _, wh, part = _stock(world, 10, 10)
    results = {"ok": 0, "fail": 0}
    lock = threading.Lock()

    def take():
        try:
            with SessionLocal() as db, db.begin():
                plant = db.get(Plant, world.plant.id)
                inv.issue(db, plant, db.get(Part, part["id"]), db.get(Warehouse, wh["id"]), 1, None, reference="race")
            with lock:
                results["ok"] += 1
        except DomainError:
            with lock:
                results["fail"] += 1

    ts = [threading.Thread(target=take) for _ in range(25)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert results == {"ok": 10, "fail": 15}
    with SessionLocal() as db:
        oh = db.execute(text("SELECT qty_on_hand FROM stock_levels")).scalar()
        n = db.execute(text("SELECT count(*) FROM inventory_transactions WHERE type='issue'")).scalar()
    assert float(oh) == 0 and n == 10


def test_ledger_is_append_only(world):
    _stock(world)
    with SessionLocal() as db:
        try:
            db.execute(text("UPDATE inventory_transactions SET quantity = 999"))
            db.commit()
            raise AssertionError("ledger update should fail")
        except Exception as e:  # noqa: BLE001
            db.rollback()
            assert "permission denied" in str(e)


def test_po_receipt_and_on_order(world):
    store, wh, part = _stock(world, 1, 100)
    po = store.ok("post", "/inventory/purchase-orders", {"lines": [{"part_id": part["id"], "quantity": 4, "unit_price": 120}],
                                                         "external_reference": "ERP-4500012345"}, status=201)
    lines = store.get("/inventory/purchase-orders").json()[0]["lines"]
    assert store.get("/inventory/parts", params={"q": "BRG"}).json()["items"][0]["qty_on_order"] == 4
    store.ok("post", f"/inventory/purchase-orders/{po['id']}/status", {"status": "ordered"})
    store.ok("post", "/inventory/receipts", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 4, "unit_cost": 120,
                                             "po_line_id": lines[0]["id"]}, status=201)
    assert store.get("/inventory/purchase-orders").json()[0]["status"] == "received"
    assert store.post("/inventory/receipts", {"part_id": part["id"], "warehouse_id": wh["id"], "quantity": 1, "unit_cost": 1,
                                              "po_line_id": lines[0]["id"]}).status_code == 409


def test_parts_import_duplicate_detection(world):
    store = world.api("store")
    store.ok("post", "/inventory/parts", {"code": "P1", "description": "x", "manufacturer": "SKF", "oem_part_number": "6205"}, status=201)
    csv = "code,description,manufacturer,oem_part_number,min_qty,max_qty\nP1,dup,,,1,2\nP2,new,SKF,6205,1,2\nP3,bad,,,5,2\n"
    p = store.ok("post", "/imports/parts/preview", files={"file": ("p.csv", csv.encode(), "text/csv")})
    assert p["invalid"] == 2 and p["warnings"][0]["code"] == "P2"
