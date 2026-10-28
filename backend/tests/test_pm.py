import threading
from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models.enums import FrequencyUnit
from app.models.pm import PMOccurrence
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services.common import plant_today
from app.services.pm import add_interval, fixed_schedule, run_scheduler
from tests.conftest import mk_asset


def test_month_arithmetic_no_drift():
    assert add_interval(date(2026, 1, 31), FrequencyUnit.MONTH, 1) == date(2026, 2, 28)
    ds = fixed_schedule(date(2026, 1, 31), FrequencyUnit.MONTH, 1, date(2026, 1, 1), date(2026, 5, 31))
    assert ds == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31)]
    assert add_interval(date(2028, 2, 29), FrequencyUnit.YEAR, 1) == date(2029, 2, 28)


def _plan(world, planner, **kw):
    line = mk_asset(planner, world, "PM1")
    jp = planner.ok(
        "post",
        "/pm/job-plans",
        {
            "code": "JP1",
            "name": "Weekly insp",
            "estimated_hours": 2,
            "requires_loto": False,
            "tasks": [
                {"seq": 10, "description": "Check noise"},
                {"seq": 20, "description": "Bearing temp", "kind": "reading", "unit": "°C", "max_value": 75},
            ],
        },
        status=201,
    )
    body = {
        "code": "PM-W",
        "name": "Weekly",
        "asset_id": line["id"],
        "job_plan_id": jp["id"],
        "frequency_unit": "week",
        "frequency_interval": 1,
        "start_date": kw.pop("start", None),
        "horizon_days": 28,
        "lead_days": 3,
    }
    body.update(kw)
    return line, jp, planner.ok("post", "/pm/plans", body, status=201)


def test_pm_generation_is_idempotent(world):
    """Acceptance B: scheduled WO generated without duplication."""
    planner = world.api("planner")
    today = plant_today(world.plant)
    _, _, plan = _plan(world, planner, start=today.isoformat())
    occ = planner.get("/pm/occurrences", params={"plan_id": plan["id"]}).json()
    assert occ["total"] == 5  # today + 4 weekly within 28-day horizon
    r1 = planner.ok("post", "/pm/scheduler/run", {})
    assert r1["work_orders_created"] == 1  # only today's occurrence is within the 3-day lead time
    for _ in range(3):
        assert planner.ok("post", "/pm/scheduler/run", {})["work_orders_created"] == 0
    wos = planner.get("/work-orders", params={"type": ["preventive"]}).json()
    assert wos["total"] == 1
    wo = planner.get(f"/work-orders/{wos['items'][0]['id']}/detail").json()
    assert wo["work_order"]["status"] == "approved" and len(wo["checklist"]) == 2 and wo["work_order"]["due_date"] == today.isoformat()
    # running "as of" a later date generates the next ones, still once each
    # as of today+8 with 3-day lead: only the today+7 occurrence is inside its lead window (today+14 opens on day 11)
    later = (today + timedelta(days=8)).isoformat()
    assert planner.ok("post", "/pm/scheduler/run", {"as_of": later})["work_orders_created"] == 1
    assert planner.ok("post", "/pm/scheduler/run", {"as_of": later})["work_orders_created"] == 0


def test_pm_scheduler_concurrent_runs_no_duplicates(world):
    planner = world.api("planner")
    today = plant_today(world.plant)
    _plan(world, planner, start=today.isoformat(), lead_days=30)
    errors = []

    def run():
        try:
            with SessionLocal() as db, db.begin():
                p = db.get(Plant, world.plant.id)
                run_scheduler(db, p, today)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=run) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors
    with SessionLocal() as db:
        n_wo = db.execute(select(func.count()).select_from(WorkOrder).where(WorkOrder.pm_occurrence_id.is_not(None))).scalar_one()
        n_occ = db.execute(select(func.count()).select_from(PMOccurrence)).scalar_one()
        dup = db.execute(
            select(WorkOrder.pm_occurrence_id, func.count())
            .group_by(WorkOrder.pm_occurrence_id)
            .having(func.count() > 1)
            .where(WorkOrder.pm_occurrence_id.is_not(None))
        ).all()
    assert n_occ == 5 and n_wo == 5 and dup == []


def _complete(world, wo_id):
    planner, tech, sup = world.api("planner"), world.api("tech"), world.api("mech_sup")
    planner.ok("post", f"/work-orders/{wo_id}/assign", {"user_ids": [str(world.users["tech"].id)]})
    tech.ok("post", f"/work-orders/{wo_id}/status", {"to": "in_progress"})
    d = tech.get(f"/work-orders/{wo_id}/detail").json()
    for c in d["checklist"]:
        body = {"is_done": True, "reading_value": 61} if c["kind"] == "reading" else {"is_done": True, "is_ok": True}
        tech.ok("patch", f"/work-orders/{wo_id}/checklist/{c['id']}", body)
    tech.ok("post", f"/work-orders/{wo_id}/status", {"to": "awaiting_review"})
    sup.ok("post", f"/work-orders/{wo_id}/status", {"to": "completed"})


def test_floating_plan_next_due_from_completion(world):
    planner = world.api("planner")
    today = plant_today(world.plant)
    _, _, plan = _plan(world, planner, start=today.isoformat(), schedule_basis="floating")
    assert planner.get("/pm/occurrences", params={"plan_id": plan["id"]}).json()["total"] == 1
    planner.ok("post", "/pm/scheduler/run", {})
    wo = planner.get("/work-orders").json()["items"][0]
    tech = world.api("tech")
    planner.ok("post", f"/work-orders/{wo['id']}/assign", {"user_ids": [str(world.users["tech"].id)]})
    tech.ok("post", f"/work-orders/{wo['id']}/status", {"to": "in_progress"})
    c = tech.get(f"/work-orders/{wo['id']}/detail").json()["checklist"]
    tech.ok("patch", f"/work-orders/{wo['id']}/checklist/{c[0]['id']}", {"is_done": True})
    tech.ok("post", f"/work-orders/{wo['id']}/status", {"to": "awaiting_review"})
    r = world.api("mech_sup").post(f"/work-orders/{wo['id']}/status", {"to": "completed"})
    assert r.status_code == 409 and "checklist" in r.text  # required reading missing
    out = tech.patch(f"/work-orders/{wo['id']}/checklist/{c[1]['id']}", {"is_done": True, "reading_value": 82})
    assert out.status_code == 409  # not in progress any more → rework needed
    world.api("mech_sup").ok("post", f"/work-orders/{wo['id']}/status", {"to": "in_progress", "comment": "rework"})
    assert tech.ok("patch", f"/work-orders/{wo['id']}/checklist/{c[1]['id']}", {"is_done": True, "reading_value": 82})["out_of_range"]
    tech.ok("post", f"/work-orders/{wo['id']}/status", {"to": "awaiting_review"})
    world.api("mech_sup").ok("post", f"/work-orders/{wo['id']}/status", {"to": "completed"})
    p = planner.get("/pm/plans").json()["items"][0]
    assert p["last_completed_date"] == today.isoformat()
    assert p["next_due_date"] == (today + timedelta(days=7)).isoformat()


def test_deferral_needs_supervisor_and_four_eyes(world):
    planner, sup = world.api("planner"), world.api("mech_sup")
    today = plant_today(world.plant)
    _, _, plan = _plan(world, planner, start=today.isoformat())
    planner.ok("post", "/pm/scheduler/run", {})
    occ = planner.get("/pm/occurrences", params={"plan_id": plan["id"], "status": ["generated"]}).json()["items"][0]
    new = (today + timedelta(days=3)).isoformat()
    assert planner.post(f"/pm/occurrences/{occ['id']}/request", {"kind": "defer", "reason": "x"}).status_code == 422
    planner.ok(
        "post", f"/pm/occurrences/{occ['id']}/request", {"kind": "defer", "reason": "Machine running, waiting for wash-up", "new_date": new}
    )
    assert planner.post(f"/pm/occurrences/{occ['id']}/decide", {"approve": True}).status_code == 403
    r = sup.ok("post", f"/pm/occurrences/{occ['id']}/decide", {"approve": True})
    assert r["status"] == "deferred" and r["due_date"] == new
    wo = planner.get(f"/work-orders/{occ['work_order_id']}").json()
    assert wo["due_date"] == new
    # cancelling a PM work order directly requires PM approval permission
    assert planner.post(f"/work-orders/{wo['id']}/status", {"to": "cancelled", "comment": "no"}).status_code == 403


def test_meter_based_pm_triggers_on_reading(world):
    planner, eng = world.api("planner"), world.api("engineer")
    line = mk_asset(planner, world, "PM1")
    m = planner.ok("post", f"/assets/{line['id']}/meters", {"name": "Running hours", "current_value": 7000}, status=201)
    jp = planner.ok("post", "/pm/job-plans", {"code": "OIL", "name": "Oil change", "estimated_hours": 4}, status=201)
    planner.ok(
        "post",
        "/pm/plans",
        {
            "code": "PM-OIL",
            "name": "Oil 8000h",
            "asset_id": line["id"],
            "job_plan_id": jp["id"],
            "trigger": "meter",
            "meter_id": m["id"],
            "meter_interval": 8000,
            "last_meter_value": 0,
        },
        status=201,
    )
    eng.ok("post", f"/assets/meters/{m['id']}/readings", {"value": 7900})
    assert planner.get("/work-orders").json()["total"] == 0
    assert eng.post(f"/assets/meters/{m['id']}/readings", {"value": 7800}).status_code == 422  # meter cannot go backwards
    eng.ok("post", f"/assets/meters/{m['id']}/readings", {"value": 8010})
    eng.ok("post", f"/assets/meters/{m['id']}/readings", {"value": 8050})
    wos = planner.get("/work-orders").json()
    assert wos["total"] == 1 and "PM-OIL" in wos["items"][0]["title"]
    assert planner.get(f"/assets/{line['id']}").json()["operating_hours"] == 8050


def test_lists_filter_by_status_and_show_plan_and_asset(world):
    """Status filters reach the API (they were once read from the request body and silently ignored)."""
    planner = world.api("planner")
    today = plant_today(world.plant)
    line, _, plan = _plan(world, planner, start=today.isoformat())
    planner.ok("post", "/pm/scheduler/run", {})
    occ = planner.get("/pm/occurrences", params={"status": ["generated"]}).json()
    assert occ["total"] == 1 and occ["items"][0]["plan_code"] == "PM-W" and occ["items"][0]["asset_id"] == line["id"]
    assert planner.get("/pm/occurrences", params={"status": ["deferral_requested", "cancellation_requested"]}).json()["total"] == 0
    assert planner.get("/pm/occurrences").json()["total"] == 5
    assert planner.get("/work-orders", params={"status": ["closed"]}).json()["total"] == 0
    assert planner.get("/work-orders", params={"type": ["corrective"]}).json()["total"] == 0
    assert planner.get("/pm/plans", params={"q": "weekl"}).json()["total"] == 1
    assert planner.get("/pm/plans", params={"q": "nothing"}).json()["total"] == 0
    codes = planner.ok("post", "/assets/codes", {"ids": [line["id"], str(plan["id"])]})
    assert codes == {line["id"]: "PM1"}  # unknown ids are skipped
