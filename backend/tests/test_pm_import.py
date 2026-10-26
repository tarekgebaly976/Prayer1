import io

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

    again = api.ok("post", "/imports/pm_plans/preview", files=_xlsx(rows))
    assert again["invalid"] == 4 and "already exists" in again["errors"][0]["errors"][0]


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
