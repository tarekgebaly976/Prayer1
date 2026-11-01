"""Planning tools: bulk close of WOs / WRs, Auto vs Manual PM / PdM work orders with release, work-order plan import,
shutdown plan import."""

import io
from datetime import timedelta

from openpyxl import Workbook
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.pm import PMOccurrence
from app.models.tenancy import Plant
from app.services.common import plant_today
from app.services.pm import run_scheduler
from tests.conftest import mk_asset
from tests.test_pm import _plan


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return {"file": ("plan.xlsx", b.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def _sched(world):
    with SessionLocal() as db, db.begin():
        return run_scheduler(db, db.get(Plant, world.plant.id))


# ---------------------------------------------------------------- bulk close
def test_bulk_close_and_cancel_work_orders(world):
    planner, engineer, tech, sup = world.api("planner"), world.api("engineer"), world.api("tech"), world.api("mech_sup")
    line = mk_asset(planner, world, "PM1")
    sp = mk_asset(planner, world, "SP1", dept="SP")
    ids = [
        planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "corrective", "title": f"Job {i}"}, status=201)["id"]
        for i in range(3)
    ]
    sp_wo = planner.ok("post", "/work-orders", {"asset_id": sp["id"], "type": "corrective", "title": "SP job"}, status=201)["id"]

    body = {"work_order_ids": ids[:2], "action": "close", "comment": "done last shutdown"}
    assert tech.post("/work-orders/bulk-finish", body).status_code == 403
    assert sup.post("/work-orders/bulk-finish", body).status_code == 403  # supervisors close one by one
    assert planner.post("/work-orders/bulk-finish", {**body, "comment": ""}).status_code == 422
    res = engineer.ok("post", "/work-orders/bulk-finish", body)
    assert len(res["done"]) == 2 and res["skipped"] == []
    for i in ids[:2]:
        w = planner.get(f"/work-orders/{i}").json()
        assert w["status"] == "closed" and w["completed_at"] and w["closed_at"]

    # Already closed are skipped, the rest still go through.
    res = planner.ok("post", "/work-orders/bulk-finish", {"work_order_ids": [ids[0], ids[2]], "action": "cancel", "comment": "duplicate"})
    assert len(res["done"]) == 1 and res["skipped"][0]["reason"] == "already closed"
    assert planner.get(f"/work-orders/{ids[2]}").json()["status"] == "cancelled"
    hist = planner.get(f"/work-orders/{ids[2]}/detail").json()
    assert "Bulk cancel: duplicate" in str(hist)

    # A user limited to SP cannot touch PM work.
    admin = world.api("admin")
    admin.ok("patch", f"/users/{world.users['engineer'].id}", {"department_ids": [str(world.depts["SP"].id)]})
    pm_open = planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "corrective", "title": "PM job"}, status=201)["id"]
    res = world.api("engineer").ok(
        "post", "/work-orders/bulk-finish", {"work_order_ids": [pm_open, sp_wo], "action": "close", "comment": "cleanup"}
    )
    assert len(res["done"]) == 1 and "not in your departments" in res["skipped"][0]["reason"]


def test_bulk_close_pm_counts_as_done(world):
    planner = world.api("planner")
    today = plant_today(world.plant)
    _, _, plan = _plan(world, planner, start=today.isoformat())
    _sched(world)
    occ = planner.get("/pm/occurrences", params={"plan_id": plan["id"]}).json()["items"][0]
    planner.ok(
        "post", "/work-orders/bulk-finish", {"work_order_ids": [occ["work_order_id"]], "action": "close", "comment": "done on paper"}
    )
    occ = planner.get("/pm/occurrences", params={"plan_id": plan["id"]}).json()["items"][0]
    assert occ["status"] == "completed"


def test_bulk_close_requests(world):
    planner, prod = world.api("planner"), world.api("production")
    line = mk_asset(planner, world, "PM1")
    reqs = [prod.ok("post", "/work-requests", {"asset_id": line["id"], "title": f"Leak {i}"}, status=201)["id"] for i in range(3)]
    sup = world.api("mech_sup")
    sup.ok("post", f"/work-requests/{reqs[2]}/triage", {"accept": True, "type": "corrective"})
    assert prod.post("/work-requests/bulk-close", {"request_ids": reqs, "comment": "old"}).status_code == 403
    res = world.api("manager").ok("post", "/work-requests/bulk-close", {"request_ids": reqs, "comment": "old requests"})
    assert len(res["done"]) == 2 and res["skipped"][0]["reason"] == "already accepted"
    r = planner.get(f"/work-requests/{reqs[0]}").json()
    assert r["status"] == "rejected" and r["triage_note"] == "Bulk close: old requests"


# ---------------------------------------------------------------- Auto / Manual
def test_manual_pm_holds_work_orders_until_released(world):
    planner, tech = world.api("planner"), world.api("tech")
    today = plant_today(world.plant)
    _, _, plan = _plan(world, planner, start=today.isoformat())
    modes = {m["code"]: m for m in planner.ok("get", "/pm/generation-modes")}
    assert modes["PM"]["pm_auto_wo"] is True and modes["PM"]["pdm_auto_wo"] is True
    assert tech.put(f"/pm/generation-modes/{world.depts['PM'].id}", {"pm_auto_wo": False}).status_code == 403
    planner.ok("put", f"/pm/generation-modes/{world.depts['PM'].id}", {"pm_auto_wo": False})

    res = _sched(world)
    assert res["work_orders_created"] == 0  # the PM due today is held
    waiting = planner.ok("get", "/pm/occurrences", params={"plan_id": plan["id"], "waiting": True})["items"]
    assert waiting and all(o["work_order_id"] is None for o in waiting)

    # Release two (one is weeks ahead: release ignores the lead window).
    pick = [waiting[0]["id"], waiting[-1]["id"]]
    assert tech.post("/pm/occurrences/release", {"occurrence_ids": pick}).status_code == 403
    rel = planner.ok("post", "/pm/occurrences/release", {"occurrence_ids": pick})
    assert len(rel["work_orders"]) == 2 and rel["skipped"] == []
    again = planner.ok("post", "/pm/occurrences/release", {"occurrence_ids": pick})
    assert again["work_orders"] == [] and len(again["skipped"]) == 2

    # Back to Auto: the scheduler catches up the ones inside the lead window.
    planner.ok("put", f"/pm/generation-modes/{world.depts['PM'].id}", {"pm_auto_wo": True})
    assert _sched(world)["work_orders_created"] >= 0
    with SessionLocal() as db:
        due = db.execute(select(PMOccurrence).where(PMOccurrence.due_date <= today + timedelta(days=3))).scalars().all()
        assert all(o.work_order_id for o in due)


def test_manual_pdm_holds_alert_work_orders(world):
    rel = world.api("reliability")
    line = mk_asset(rel, world, "PM1")
    body = {"code": "VIB1", "name": "Vib", "asset_id": line["id"], "technique": "vibration", "unit": "mm/s"}
    p = rel.ok("post", "/pdm/points", {**body, "warning_high": 4.5, "alarm_high": 7.1, "auto_create_wo": True}, status=201)
    rel.ok("put", f"/pm/generation-modes/{world.depts['PM'].id}", {"pdm_auto_wo": False})
    r = world.api("tech").ok("post", f"/pdm/points/{p['id']}/readings", {"value": 9.0}, status=201)
    assert r["status"] == "critical" and r["alert_id"] and r["work_order_id"] is None
    # Manual: the alert still offers "create work order".
    wo = rel.ok("post", f"/pdm/alerts/{r['alert_id']}/work-order")
    assert wo


# ---------------------------------------------------------------- work-order plan import
WO_HEADER = [
    "asset_code",
    "title",
    "type",
    "priority",
    "due_date",
    "planned_start",
    "estimated_hours",
    "assign_to",
    "pm_plan_code",
    "description",
]


def test_work_order_plan_import(world):
    planner = world.api("planner")
    today = plant_today(world.plant)
    _, _, plan = _plan(world, planner, start=today.isoformat())
    mk_asset(planner, world, "SP1", dept="SP")
    planner.ok("put", f"/pm/generation-modes/{world.depts['PM'].id}", {"pm_auto_wo": False})
    _sched(world)
    d = (today + timedelta(days=2)).isoformat()
    rows = [
        WO_HEADER,
        ["PM1", "Replace felt", "corrective", "P2", d, d, 6, "tech@example.com, tech2@example.com", None, "Wet end"],
        [None, None, None, None, d, None, None, "tech@example.com", "PM-W", None],
        ["SP1", "Check gearbox", "inspection", "low", d, None, 2, None, None, None],
    ]
    bad = [WO_HEADER, ["NOPE", "x", "weird", "P9", "31-12-2026", None, None, "ghost@example.com", "NO-PLAN", None]]
    p = planner.ok("post", "/imports/work_orders/preview", files=_xlsx(bad))
    errs = p["errors"][0]["errors"]
    assert p["invalid"] == 1 and any("NO-PLAN" in e for e in errs) and any("ghost" in e for e in errs)
    assert planner.post("/imports/work_orders/commit", files=_xlsx(bad)).status_code == 422

    p = planner.ok("post", "/imports/work_orders/preview", files=_xlsx(rows))
    assert p["invalid"] == 0 and p["plans"] == 1
    assert planner.ok("post", "/imports/work_orders/commit", files=_xlsx(rows))["created"] == 3
    wos = {w["title"]: w for w in planner.get("/work-orders", params={"limit": 50}).json()["items"]}
    felt = wos["Replace felt"]
    assert felt["priority"] == "P2" and felt["due_date"] == d and felt["planned_start"]
    assert wos["Check gearbox"]["priority"] == "P4" and wos["Check gearbox"]["type"] == "inspection"
    pm = wos["PM-W Weekly"]
    assert pm["pm_occurrence_id"] and pm["due_date"] == d
    detail = planner.get(f"/work-orders/{felt['id']}/detail").json()
    assert len(detail["work_order"]["assignments"] if "work_order" in detail else felt["assignments"]) == 2

    # Department limits: an SP supervisor cannot import PM work; a technician cannot import at all.
    sp_rows = [WO_HEADER, ["PM1", "Not mine", "corrective", "P3", d, None, None, None, None, None]]
    p = world.api("sp_sup").ok("post", "/imports/work_orders/preview", files=_xlsx(sp_rows))
    assert "not in your departments" in p["errors"][0]["errors"][0]
    assert world.api("tech").post("/imports/work_orders/preview", files=_xlsx(sp_rows)).status_code == 403
    # Engineers may create but not assign.
    p = world.api("engineer").ok("post", "/imports/work_orders/preview", files=_xlsx(rows[:2]))
    assert any("assign" in e for e in p["errors"][0]["errors"])


# ---------------------------------------------------------------- shutdown plan import
SD_HEADER = [
    "shutdown_code", "shutdown_name", "shutdown_start", "shutdown_end", "package_code", "package_name", "asset_code",
    "duration_hours", "planned_manpower", "contractor_manpower", "owner", "predecessors", "material_status", "permit_status",
    "loto_status", "create_wo",
]  # fmt: skip


def test_shutdown_plan_import(world):
    eng = world.api("engineer")
    mk_asset(world.api("planner"), world, "PM1")
    start = (plant_today(world.plant) + timedelta(days=30)).isoformat()
    end = (plant_today(world.plant) + timedelta(days=33)).isoformat()
    rows = [
        SD_HEADER,
        ["SD-26", "Annual shutdown", f"{start} 06:00", f"{end} 18:00", "P01", "Isolate and drain", "PM1", 8, 4, 0, "planner@example.com", None, "ready", "ready", "ready", "yes"],
        ["SD-26", None, None, None, "P02", "Replace bearings", "PM1", 24, 3, 6, None, "P01", "partial", "not ready", "n/a", None],
        ["SD-26", None, None, None, "P03", "Hydro test", None, 6, 2, 0, None, "P02", None, None, None, None],
    ]  # fmt: skip
    assert world.api("tech").post("/imports/shutdown_plan/preview", files=_xlsx(rows)).status_code == 403
    p = eng.ok("post", "/imports/shutdown_plan/preview", files=_xlsx(rows))
    assert p["invalid"] == 0 and p["plans"] == 1
    assert eng.ok("post", "/imports/shutdown_plan/commit", files=_xlsx(rows))["created"] == 3
    sd = next(s for s in eng.get("/shutdowns").json() if s["code"] == "SD-26")
    detail = eng.get(f"/shutdowns/{sd['id']}").json()
    pk = {p["code"]: p for p in detail["packages"]}
    assert set(pk) == {"P01", "P02", "P03"}
    assert (
        pk["P02"]["contractor_manpower"] == 6 and pk["P02"]["permit_status"] == "not_ready" and pk["P02"]["loto_status"] == "not_required"
    )
    assert all(pk[c]["is_critical"] for c in pk)  # a chain: everything is on the critical path
    wos = eng.get("/work-orders", params={"type": "shutdown"}).json()["items"]
    assert len(wos) == 1 and "P01" in wos[0]["title"]

    # Re-import updates packages (no duplicate WO) and rejects loops and unknown shutdowns.
    upd = [SD_HEADER, ["SD-26", None, None, None, "P03", "Hydro test 2", None, 10, 2, 0, None, "P01", None, None, None, None]]
    assert eng.ok("post", "/imports/shutdown_plan/commit", files=_xlsx(upd + [rows[1]]))["created"] == 2
    detail = eng.get(f"/shutdowns/{sd['id']}").json()
    p3 = next(p for p in detail["packages"] if p["code"] == "P03")
    assert p3["name"] == "Hydro test 2" and float(p3["duration_hours"]) == 10
    assert len(eng.get("/work-orders", params={"type": "shutdown"}).json()["items"]) == 1
    loop = [SD_HEADER, ["SD-26", None, None, None, "P01", "Isolate", None, 8, None, None, None, "P02", None, None, None, None]]
    p = eng.ok("post", "/imports/shutdown_plan/preview", files=_xlsx(loop))
    assert "loop" in p["errors"][0]["errors"][0]
    unknown = [SD_HEADER, ["SD-99", None, None, None, "P01", "x", None, 1, None, None, None, None, None, None, None, None]]
    p = eng.ok("post", "/imports/shutdown_plan/preview", files=_xlsx(unknown))
    assert "does not exist" in p["errors"][0]["errors"][0]
