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


def test_pdm_alert_action_work_order_request_or_nothing(world):
    from app.models.workorders import WorkRequest

    rel, tech = world.api("reliability"), world.api("tech")
    line = mk_asset(rel, world, "PM1")
    body = {"name": "Vib", "asset_id": line["id"], "technique": "vibration", "unit": "mm/s", "warning_high": 4.5, "alarm_high": 7.1}
    pts = [rel.ok("post", "/pdm/points", {**body, "code": f"VIB{i}", "auto_create_wo": True}, status=201) for i in range(3)]
    dept = f"/pm/generation-modes/{world.depts['PM'].id}"
    assert rel.ok("get", "/pm/generation-modes")[2]["pdm_alert_action"] == "wo"  # default
    assert rel.put(dept, {"pdm_alert_action": "maybe"}).status_code == 422
    assert tech.put(dept, {"pdm_alert_action": "wr"}).status_code == 403

    # "none": alert only; the alert still offers "create work order".
    rel.ok("put", dept, {"pdm_alert_action": "none"})
    r = tech.ok("post", f"/pdm/points/{pts[0]['id']}/readings", {"value": 9.0}, status=201)
    assert r["status"] == "critical" and r["alert_id"] and r["work_order_id"] is None
    assert rel.ok("post", f"/pdm/alerts/{r['alert_id']}/work-order")

    # "wr": a work request for supervisors to triage, once per alert.
    rel.ok("put", dept, {"pdm_alert_action": "wr"})
    r = tech.ok("post", f"/pdm/points/{pts[1]['id']}/readings", {"value": 9.5}, status=201)
    assert r["work_order_id"] is None
    tech.ok("post", f"/pdm/points/{pts[1]['id']}/readings", {"value": 9.9}, status=201)
    with SessionLocal() as db:
        wrs = list(db.execute(select(WorkRequest).where(WorkRequest.title == "Condition alert: Vib")).scalars())
        assert len(wrs) == 1 and wrs[0].suggested_priority.value == "P2"
    reqs = world.api("mech_sup").ok("get", "/work-requests", params={"status": "submitted"})["items"]
    assert any(x["title"] == "Condition alert: Vib" for x in reqs)

    # "wo": work order as before.
    rel.ok("put", dept, {"pdm_alert_action": "wo"})
    r = tech.ok("post", f"/pdm/points/{pts[2]['id']}/readings", {"value": 9.0}, status=201)
    assert r["work_order_id"]


def test_manual_lubrication_routes(world):
    from app.services.lubrication import run_routes
    from tests.test_lube_shifts import _lube_setup

    _, _, _, _, route, _, _ = _lube_setup(world)
    rel = world.api("reliability")
    assert world.api("tech").put(f"/pm/generation-modes/{world.depts['PM'].id}", {"lube_auto_wo": False}).status_code == 403
    m = rel.ok("put", f"/pm/generation-modes/{world.depts['PM'].id}", {"lube_auto_wo": False})
    assert m["lube_auto_wo"] is False
    with SessionLocal() as db, db.begin():
        assert run_routes(db, db.get(Plant, world.plant.id)) == []  # held
    g = rel.ok("post", f"/lubrication/routes/{route['id']}/generate", {})  # the team generates it itself
    assert g["work_order_id"]
    rel.ok("put", f"/pm/generation-modes/{world.depts['PM'].id}", {"lube_auto_wo": True})
    with SessionLocal() as db, db.begin():
        assert run_routes(db, db.get(Plant, world.plant.id)) == []  # nothing more due: no duplicate


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


def test_export_plans_and_reimport_work_plan(world):
    from openpyxl import load_workbook

    planner = world.api("planner")
    today = plant_today(world.plant)
    _, _, plan = _plan(world, planner, start=today.isoformat())
    planner.ok("put", f"/pm/generation-modes/{world.depts['PM'].id}", {"pm_auto_wo": False})
    _sched(world)
    r = planner.get("/pm/plans/export.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["work_plan", "pm_plans", "instructions"]
    plans = list(wb["pm_plans"].values)
    assert plans[0][0] == "code" and plans[1][0] == "PM-W" and plans[1][3] == "PM1" and plans[1][11] > 0
    wp = list(wb["work_plan"].values)
    assert wp[0][:2] == ("asset_code", "title") and all(row[8] == "PM-W" for row in wp[1:])
    n = len(wp) - 1
    assert n > 0
    # The same file imports straight back: every waiting occurrence becomes a work order.
    files = {"file": ("pm_plans.xlsx", r.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    assert planner.ok("post", "/imports/work_orders/commit", files=files)["created"] == n
    assert planner.ok("get", "/pm/occurrences", params={"plan_id": plan["id"], "waiting": True})["total"] == 0
    # Department scope: an SP-only user sees no PM plans.
    r = world.api("sp_sup").get("/pm/plans/export.xlsx")
    assert len(list(load_workbook(io.BytesIO(r.content))["pm_plans"].values)) == 1


def test_bulk_close_lubrication_work_orders_finish_their_points(world):
    from app.models.lubrication import LubeTask, LubricationPoint
    from tests.test_lube_shifts import _lube_setup

    _, _, _, _, route, pts, today = _lube_setup(world)
    rel, planner = world.api("reliability"), world.api("planner")
    wo = rel.ok("post", f"/lubrication/routes/{route['id']}/generate", {})["work_order_id"]
    res = planner.ok("post", "/work-orders/bulk-finish", {"work_order_ids": [wo], "action": "close", "comment": "done on paper"})
    assert len(res["done"]) == 1
    with SessionLocal() as db:
        assert {t.status.value for t in db.execute(select(LubeTask)).scalars()} == {"done"}
        nxt = {p.next_due_date for p in db.execute(select(LubricationPoint)).scalars()}
        assert nxt == {today + timedelta(days=14)}
    # Cancel: the points are skipped and move to their next cycle.
    with SessionLocal() as db, db.begin():
        for p in db.execute(select(LubricationPoint)).scalars():
            p.next_due_date = today + timedelta(days=1)  # a new due date (inside the route lead time)
    wo2 = rel.ok("post", f"/lubrication/routes/{route['id']}/generate", {})["work_order_id"]
    planner.ok("post", "/work-orders/bulk-finish", {"work_order_ids": [wo2], "action": "cancel", "comment": "route merged"})
    with SessionLocal() as db:
        tasks = list(db.execute(select(LubeTask).where(LubeTask.work_order_id == wo2)).scalars())
        assert {t.status.value for t in tasks} == {"skipped"}
        assert {p.next_due_date for p in db.execute(select(LubricationPoint)).scalars()} == {today + timedelta(days=15)}
