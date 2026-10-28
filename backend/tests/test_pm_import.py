import io
from datetime import date

from openpyxl import Workbook

from app.models.enums import FrequencyUnit
from app.services.pm_import import parse_frequency, split_steps
from tests.conftest import mk_asset

HEADER = ["asset_code", "frequency", "task", "trade", "duration_min", "crew", "shutdown_required", "start_date", "priority"]


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return {"file": ("pm.xlsx", b.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def test_frequency_and_step_parsing():
    assert parse_frequency("Monthly")[:2] == (FrequencyUnit.MONTH, 1)
    assert parse_frequency(90)[:2] == (FrequencyUnit.MONTH, 3)
    assert parse_frequency("365")[:2] == (FrequencyUnit.YEAR, 1)
    assert parse_frequency("half-yearly")[:2] == (FrequencyUnit.MONTH, 6)
    assert parse_frequency(45)[:2] == (FrequencyUnit.DAY, 45)
    assert parse_frequency("sometimes") is None and parse_frequency(0) is None
    assert split_steps("Secure permit: 1. Clean motor 2. Check base 3.Carry tools") == [
        "Secure permit: Clean motor",
        "Check base",
        "Carry tools",
    ]
    assert split_steps("Inspect hose for leakage") == ["Inspect hose for leakage"]
    assert len(split_steps("x" * 900)[0]) == 400


def test_pm_import_groups_tasks_into_plans_and_is_all_or_nothing(world):
    api = world.api("planner")
    line = mk_asset(api, world, "PM-LINE")
    mk_asset(api, world, "PM-DRYER", level="unit", parent=line["id"])
    rows = [
        HEADER,
        ["PM-DRYER", "monthly", "1. Clean motor 2. Check base", "Mechanical", 60, 2, "offline", "2026-11-02", ""],
        ["PM-DRYER", 30, "Inspect coupling", "mechanical", 30, 1, "online", "", "P2"],
        ["PM-DRYER", "monthly", "Check panel", "Electrical", 20, 1, "", "", ""],
        ["PM-DRYER", "yearly", "Overhaul gearbox", "Mechanical", 480, 3, "yes", "2027-01-10", ""],
    ]
    bad = rows + [["NOPE", "monthly", "x", "", "", "", "", "", ""], ["PM-DRYER", "sometimes", "y", "", "", "", "", "", ""]]
    p = api.ok("post", "/imports/pm_plans/preview", files=_xlsx(bad))
    assert p["total"] == 6 and p["invalid"] == 2 and p["plans"] == 3
    msgs = {e["row"]: " ".join(e["errors"]) for e in p["errors"]}
    assert "not found" in msgs[6] and "frequency" in msgs[7]
    assert api.post("/imports/pm_plans/commit", files=_xlsx(bad)).status_code == 422
    assert api.get("/pm/plans").json()["total"] == 0

    assert api.ok("post", "/imports/pm_plans/commit", files=_xlsx(rows))["created"] == 3
    plans = {pl["code"]: pl for pl in api.get("/pm/plans").json()["items"]}
    assert set(plans) == {"PM-DRYER-M-MECH", "PM-DRYER-M-ELEC", "PM-DRYER-Y-MECH"}
    mech = plans["PM-DRYER-M-MECH"]
    assert (mech["frequency_unit"], mech["frequency_interval"]) == ("month", 1)
    assert mech["start_date"] == "2026-11-02" and mech["priority"] == "P2"
    assert mech["name"].startswith("Monthly Mechanical PM")
    jp = api.ok("get", f"/pm/job-plans/{mech['job_plan_id']}")
    assert [t["description"] for t in jp["tasks"]] == ["Clean motor", "Check base", "Inspect coupling"]
    assert jp["estimated_hours"] == 1.5 and jp["crew_size"] == 2 and "shutdown" in jp["safety_precautions"].lower()

    elec = plans["PM-DRYER-M-ELEC"]  # no start_date: first due spread inside the first month, never in the past
    assert -1 <= (date.fromisoformat(elec["start_date"]) - date.today()).days < 31  # -1: plant (Riyadh) vs UTC date

    again = api.ok("post", "/imports/pm_plans/preview", files=_xlsx(rows))
    assert again["invalid"] == 4 and "already exists" in again["errors"][0]["errors"][0]


def test_large_round_lists_one_line_per_task(world):
    api = world.api("planner")
    mk_asset(api, world, "PM-COATER")
    tasks = [f"Task {i}: 1. Clean part {i} 2. Inspect part {i}" for i in range(40)]  # 80 steps > MAX_STEPS
    rows = [HEADER] + [["PM-COATER", "quarterly", t, "Instrumentation", 10, 1, "", "", ""] for t in tasks]
    assert api.ok("post", "/imports/pm_plans/commit", files=_xlsx(rows))["created"] == 1
    plan = api.get("/pm/plans").json()["items"][0]
    jp = api.ok("get", f"/pm/job-plans/{plan['job_plan_id']}")
    assert len(jp["tasks"]) == 40 and jp["tasks"][0]["description"].startswith("Task 0: 1. Clean part 0")
    assert "40. Task 39" in jp["description"]


def test_pm_import_requires_pm_manage(world):
    files = _xlsx([HEADER, ["X", "monthly", "t", "", "", "", "", "", ""]])
    assert world.api("tech").post("/imports/pm_plans/preview", files=files).status_code == 403


LUBE_HEADER = [
    "asset_code",
    "component",
    "lubricant_code",
    "lubricant_name",
    "lubricant_type",
    "viscosity_grade",
    "quantity",
    "unit",
    "method",
    "frequency",
    "route_code",
    "start_date",
    "point_code",
]


def test_lube_import_creates_lubricants_routes_and_points(world):
    api = world.api("planner")
    line = mk_asset(api, world, "PM-LINE")
    mk_asset(api, world, "PM-DRYER", level="unit", parent=line["id"])
    mk_asset(api, world, "SP-LINE", dept="SP")
    rows = [
        LUBE_HEADER,
        ["PM-DRYER", "DE bearing", "GR-EP2", "Mobilux EP 2", "grease", "NLGI 2", 20, "g", "Grease gun", "weekly", "", "2026-11-03", ""],
        ["PM-DRYER", "NDE bearing", "GR-EP2", "", "", "", 15, "g", "Grease gun", 7, "", "", ""],
        ["PM-DRYER", "Gearbox", "OIL-220", "Mobilgear 600 XP 220", "oil", "ISO VG 220", 5, "L", "Oil change", "yearly", "", "", ""],
        ["SP-LINE", "Pump bearing", "GR-EP2", "", "", "", 10, "", "", "weekly", "", "", ""],
    ]
    bad = rows + [
        ["PM-DRYER", "x", "NEW-1", "", "", "", 5, "g", "", "weekly", "", "", ""],
        ["PM-DRYER", "x", "GR-EP2", "", "", "", 0, "g", "", "weekly", "", "", ""],
    ]
    p = api.ok("post", "/imports/lube_plans/preview", files=_xlsx(bad))
    assert p["invalid"] == 2 and p["new_lubricants"] == 2 and p["plans"] == 3
    msgs = {e["row"]: " ".join(e["errors"]) for e in p["errors"]}
    assert "lubricant_name is required" in msgs[6] and "quantity" in msgs[7]
    assert api.post("/imports/lube_plans/commit", files=_xlsx(bad)).status_code == 422

    assert api.ok("post", "/imports/lube_plans/commit", files=_xlsx(rows))["created"] == 4
    routes = {r["code"]: r for r in api.get("/lubrication/routes").json()}
    assert set(routes) == {"LR-PM-W", "LR-PM-Y", "LR-SP-W"}
    weekly = api.get("/lubrication/points", params={"route_id": routes["LR-PM-W"]["id"]}).json()
    assert [(pt["code"], pt["frequency_days"]) for pt in weekly] == [("PM-DRYER-L01", 7), ("PM-DRYER-L02", 7)]
    assert weekly[0]["next_due_date"] == "2026-11-03"
    yearly = api.get("/lubrication/points", params={"route_id": routes["LR-PM-Y"]["id"]}).json()[0]
    assert 0 <= (date.fromisoformat(yearly["next_due_date"]) - date.today()).days < 366  # no start date: spread over the first year
    assert {lb["code"] for lb in api.get("/lubrication/lubricants").json()} == {"GR-EP2", "OIL-220"}
    again = api.ok("post", "/imports/lube_plans/preview", files=_xlsx([LUBE_HEADER, rows[1][:12] + ["PM-DRYER-L01"]]))
    assert again["invalid"] == 1 and "already exists" in again["errors"][0]["errors"][0]


PDM_HEADER = [
    "asset_code",
    "point_name",
    "technique",
    "unit",
    "frequency",
    "warning_high",
    "alarm_high",
    "warning_low",
    "alarm_low",
    "baseline",
    "trade",
    "start_date",
    "point_code",
]


def test_pdm_import_creates_points_and_predictive_rounds(world):
    api = world.api("reliability")
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM-LINE")
    mk_asset(planner, world, "PM-PRESS", level="unit", parent=line["id"])
    rows = [
        PDM_HEADER,
        ["PM-PRESS", "Motor DE vibration", "vibration", "mm/s", "monthly", 4.5, 7.1, "", "", 1.2, "", "2026-11-05", ""],
        ["PM-PRESS", "Motor NDE vibration", "Vibration", "mm/s", 30, 4.5, 7.1, "", "", "", "", "", ""],
        ["PM-PRESS", "Gearbox temperature", "temperature", "°C", "monthly", 80, 95, "", "", "", "", "", ""],
        ["PM-PRESS", "Panel hotspots", "thermography", "°C", "quarterly", 60, 80, "", "", "", "Electrical", "", ""],
    ]
    bad = rows + [
        ["PM-PRESS", "x", "laser", "mm", "monthly", "", "", "", "", "", "", "", ""],
        ["PM-PRESS", "y", "vibration", "mm/s", "monthly", 9, 5, "", "", "", "", "", ""],
    ]
    p = api.ok("post", "/imports/pdm_plans/preview", files=_xlsx(bad))
    assert p["invalid"] == 2 and p["plans"] == 2
    msgs = {e["row"]: " ".join(e["errors"]) for e in p["errors"]}
    assert "technique" in msgs[6] and "Alarm high" in msgs[7]

    assert api.ok("post", "/imports/pdm_plans/commit", files=_xlsx(rows))["created"] == 4
    points = {pt["code"]: pt for pt in api.get("/pdm/points").json()}
    assert set(points) == {"PM-PRESS-CM01", "PM-PRESS-CM02", "PM-PRESS-CM03", "PM-PRESS-CM04"}
    assert float(points["PM-PRESS-CM01"]["alarm_high"]) == 7.1
    assert points["PM-PRESS-CM01"]["priority"] == 3  # no priority column: normal
    plans = {pl["code"]: pl for pl in api.get("/pm/plans").json()["items"]}
    assert set(plans) == {"PM-PRESS-CMM-RELI", "PM-PRESS-CMQ-ELEC"}
    rnd = plans["PM-PRESS-CMM-RELI"]
    assert rnd["wo_type"] == "predictive" and rnd["start_date"] == "2026-11-05"
    jp = api.ok("get", f"/pm/job-plans/{rnd['job_plan_id']}")
    assert [t["kind"] for t in jp["tasks"]] == ["reading"] * 3 and float(jp["tasks"][0]["max_value"]) == 7.1


def test_plan_imports_check_each_permission(world):
    tech = world.api("tech")
    for kind in ("pm_plans", "lube_plans", "pdm_plans"):
        assert tech.post(f"/imports/{kind}/preview", files=_xlsx([["asset_code"], ["X"]])).status_code == 403
    assert world.api("planner").post("/imports/nope/preview", files=_xlsx([["a"], ["b"]])).status_code == 404


def test_spread_lube_reschedules_points_imported_due_today(world):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.enums import WOStatus
    from app.models.lubrication import LubeRoute, LubricationPoint
    from app.models.tenancy import Plant
    from app.models.workorders import WorkOrder
    from app.services.common import plant_today
    from app.services.lubrication import run_routes, spread_due_dates

    api = world.api("planner")
    today = plant_today(world.plant)
    for c in ("M1", "M2", "M3"):
        mk_asset(api, world, c)
    rows = [LUBE_HEADER] + [
        [c, "Bearing", "GR-EP2", "Mobilux EP 2", "grease", "", 10, "g", "", f, "", today.isoformat(), ""]
        for c in ("M1", "M2", "M3")
        for f in ("monthly", "yearly")
    ]  # an explicit start date of today = how the first imports scheduled every point
    api.ok("post", "/imports/lube_plans/commit", files=_xlsx(rows))
    with SessionLocal() as db, db.begin():
        plant = db.get(Plant, world.plant.id)
        assert len(run_routes(db, plant, today)) == 2  # monthly and yearly route work orders, 3 points each
        yearly = db.execute(select(LubeRoute).where(LubeRoute.plant_id == plant.id, LubeRoute.code == "LR-PM-Y")).scalar_one()
        wo = db.execute(select(WorkOrder).where(WorkOrder.title.like("%LR-PM-Y%"))).scalar_one()
        wo.status = WOStatus.IN_PROGRESS  # someone already started the yearly route

    with SessionLocal() as db, db.begin():
        plant = db.get(Plant, world.plant.id)
        dry = spread_due_dates(db, plant, today)
        assert (dry["points_rescheduled"], dry["points_skipped_in_progress"], dry["work_orders_cancelled"]) == (3, 3, 1)
        assert (
            db.execute(select(LubricationPoint.next_due_date).where(LubricationPoint.plant_id == plant.id)).scalars().all() == [today] * 6
        )
    with SessionLocal() as db, db.begin():
        plant = db.get(Plant, world.plant.id)
        assert spread_due_dates(db, plant, today, apply=True)["work_orders_cancelled"] == 1
    with SessionLocal() as db:
        monthly = db.execute(select(WorkOrder).where(WorkOrder.title.like("%LR-PM-M %"))).scalar_one()
        assert monthly.status == WOStatus.CANCELLED
        pts = db.execute(select(LubricationPoint).where(LubricationPoint.plant_id == world.plant.id)).scalars().all()
        for p in pts:
            if p.route_id == yearly.id:
                assert p.next_due_date == today  # in progress: untouched
            else:
                assert 0 <= (p.next_due_date - today).days < 30
        assert len({p.next_due_date for p in pts if p.route_id != yearly.id}) > 1  # spread, not one day
        assert spread_due_dates(db, db.get(Plant, world.plant.id), today)["points_rescheduled"] <= 3  # idempotent-ish


def _pages(pdf: bytes) -> int:
    import re

    return len(re.findall(rb"/Type /Page[^s]", pdf))


def test_qr_label_sheets_for_assets_and_lubrication_points(world):
    api = world.api("planner")
    line = mk_asset(api, world, "LBL-LINE")
    for i in range(30):
        mk_asset(api, world, f"LBL-U{i:02d}", level="unit", parent=line["id"])
    mk_asset(api, world, "OTHER-LINE")
    r = api.get("/assets/labels.pdf", params={"under": line["id"]})
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and r.headers["content-type"] == "application/pdf"
    assert _pages(r.content) == 2  # 31 labels: 24 + 7
    assert _pages(api.get("/assets/labels.pdf", params={"under": line["id"], "levels": "production_line"}).content) == 1
    assert _pages(api.get("/assets/labels.pdf", params={"under": line["id"], "skip": 17}).content) == 2  # 7 + 24 exactly
    assert _pages(api.get("/assets/labels.pdf", params={"under": line["id"], "skip": 18}).content) == 3
    assert api.get("/assets/labels.pdf", params={"skip": 24}).status_code == 422
    assert api.get("/assets/labels.pdf", params={"levels": "nope"}).status_code == 422

    rows = [LUBE_HEADER] + [
        [f"LBL-U{i:02d}", "DE bearing", "GR-EP2", "Mobilux EP 2", "grease", "", 20, "g", "", "weekly", "", "", ""] for i in range(3)
    ]
    api.ok("post", "/imports/lube_plans/commit", files=_xlsx(rows))
    route = api.get("/lubrication/routes").json()[0]
    r = api.get("/lubrication/points/labels.pdf", params={"route_id": route["id"]})
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and _pages(r.content) == 1
    assert world.api("tech").get("/lubrication/points/labels.pdf", params={"under": line["id"]}).status_code == 200


def test_repair_asset_paths_restores_subtrees(world):
    import uuid as _uuid

    from sqlalchemy import update

    from app.core.db import SessionLocal
    from app.models.assets import Asset
    from app.services.assets import repair_paths

    api = world.api("planner")
    line = mk_asset(api, world, "RP-LINE")
    unit = mk_asset(api, world, "RP-UNIT", level="unit", parent=line["id"])
    mk_asset(api, world, "RP-ASM", level="assembly", parent=unit["id"])
    with SessionLocal() as db, db.begin():  # a path left behind by an old import
        db.execute(update(Asset).where(Asset.code == "RP-ASM").values(path=f"/{_uuid.uuid4()}/"))
    r = api.get("/assets/labels.pdf", params={"under": line["id"]})
    assert r.status_code == 200 and _pages(r.content) == 1
    with SessionLocal() as db, db.begin():
        dry = repair_paths(db, world.plant.id)
        assert dry["paths_wrong"] == 1 and dry["applied"] is False
        assert repair_paths(db, world.plant.id, apply=True)["paths_wrong"] == 1
    with SessionLocal() as db:
        assert repair_paths(db, world.plant.id)["paths_wrong"] == 0
        asm = db.query(Asset).filter(Asset.code == "RP-ASM").one()
        assert asm.path.endswith(f"{unit['id']}/{asm.id}/") and asm.path.startswith(f"/{line['id']}/")
