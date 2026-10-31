from tests.conftest import login, mk_asset


def test_cross_plant_header_rejected(world):
    pb = login("planner_b@example.com", world.plant.id)  # member of plant B only, asks for plant A
    assert pb.get("/assets").status_code == 403
    assert pb.get("/work-orders").status_code == 403


def test_cross_plant_object_ids_not_found(world):
    a = world.api("planner")
    asset = mk_asset(a, world, "A-LINE")
    req = a.ok("post", "/work-requests", {"asset_id": asset["id"], "title": "Noise on line"}, status=201)
    b = login("planner_b@example.com", world.plant_b.id)
    assert b.get(f"/assets/{asset['id']}").status_code == 404
    # Creating a request in plant B for a plant A asset is rejected
    assert b.post("/work-requests", {"asset_id": asset["id"], "title": "sneaky"}).status_code == 422
    listing = b.get("/work-requests").json()
    assert all(r["id"] != req["id"] for r in listing["items"])


def test_backend_enforces_permissions(world):
    tech = world.api("tech")
    planner = world.api("planner")
    asset = mk_asset(planner, world, "LINE1")
    assert (
        tech.post("/assets", {"code": "X", "name": "X", "department_id": str(world.depts["PM"].id), "level": "production_line"}).status_code
        == 403
    )
    assert tech.post("/pm/job-plans", {"code": "J", "name": "J"}).status_code == 403
    prod = world.api("production")
    assert prod.post("/work-requests", {"asset_id": asset["id"], "title": "Felt hole"}).status_code == 201
    assert prod.post("/work-orders", {"asset_id": asset["id"], "type": "corrective", "title": "x x x"}).status_code == 403
    viewer = world.api("viewer")
    assert viewer.get("/kpis").status_code == 200
    assert viewer.post("/inventory/parts", {"code": "P", "description": "p"}).status_code == 403
    store = world.api("store")
    assert store.get("/kpis").status_code == 403
    assert tech.get("/audit-logs").status_code == 403


def test_department_restricted_membership(world):
    planner = world.api("planner")
    pm_line = mk_asset(planner, world, "PM-LINE", dept="PM")
    sp_line = mk_asset(planner, world, "SP-LINE", dept="SP")
    planner.ok("post", "/work-orders", {"asset_id": pm_line["id"], "type": "corrective", "title": "PM job"}, status=201)
    wo_sp = planner.ok("post", "/work-orders", {"asset_id": sp_line["id"], "type": "corrective", "title": "SP job"}, status=201)
    sp = login("sp_sup@example.com", world.plant.id)
    items = sp.get("/work-orders").json()["items"]
    assert [w["id"] for w in items] == [wo_sp["id"]]
    assets = sp.get("/assets").json()["items"]
    assert {a["code"] for a in assets} == {"SP-LINE"}
    assert sp.post("/work-orders", {"asset_id": pm_line["id"], "type": "corrective", "title": "not mine"}).status_code == 403


def test_two_plants_independent_numbering(world):
    a = world.api("planner")
    b = login("planner_b@example.com", world.plant_b.id)
    la = mk_asset(a, world, "L")
    lb = b.ok(
        "post", "/assets", {"code": "L", "name": "L", "department_id": str(world.depts_b["PM"].id), "level": "production_line"}, status=201
    )
    wa = a.ok("post", "/work-orders", {"asset_id": la["id"], "type": "corrective", "title": "aaa"}, status=201)
    wb = b.ok("post", "/work-orders", {"asset_id": lb["id"], "type": "corrective", "title": "bbb"}, status=201)
    assert wa["number"] == "WO-P1-000001" and wb["number"] == "WO-P2-000001"


def test_department_user_sees_only_own_department_in_pm_lube_pdm_requests(world):
    planner, rel = world.api("planner"), world.api("reliability")
    lines = {d: mk_asset(planner, world, f"{d}-L", dept=d) for d in ("PM", "SP")}
    jp = planner.ok("post", "/pm/job-plans", {"code": "JP-D", "name": "Inspect", "estimated_hours": 1}, status=201)
    plans = {
        d: planner.ok(
            "post",
            "/pm/plans",
            {
                "code": f"PM-{d}",
                "name": d,
                "asset_id": a["id"],
                "job_plan_id": jp["id"],
                "trigger": "calendar",
                "frequency_unit": "week",
                "start_date": "2026-11-02",
                "frequency_interval": 1,
            },
            status=201,
        )
        for d, a in lines.items()
    }
    pts = {
        d: rel.ok("post", "/pdm/points", {"asset_id": a["id"], "technique": "vibration", "unit": "mm/s", "warning_high": 1}, status=201)
        for d, a in lines.items()
    }
    lub = rel.ok("post", "/lubrication/lubricants", {"code": "G2", "manufacturer": "X", "product": "Grease", "kind": "grease"}, status=201)
    routes = {
        d: rel.ok(
            "post",
            "/lubrication/routes",
            {"code": f"R-{d}", "name": d, "department_id": str(world.depts[d].id), "lead_days": 1},
            status=201,
        )
        for d in lines
    }
    lps = {
        d: rel.ok(
            "post",
            "/lubrication/points",
            {
                "code": f"LP-{d}",
                "asset_id": a["id"],
                "lubricant_id": lub["id"],
                "quantity": 10,
                "unit": "g",
                "frequency_days": 7,
                "route_id": routes[d]["id"],
            },
            status=201,
        )
        for d, a in lines.items()
    }
    for p in pts.values():
        world.api("tech").ok("post", f"/pdm/points/{p['id']}/readings", {"value": 5}, status=201)  # warning alert on both
    reqs = {
        d: world.api("tech").ok("post", "/work-requests", {"asset_id": a["id"], "title": f"Leak {d}"}, status=201) for d, a in lines.items()
    }

    sp = login("sp_sup@example.com", world.plant.id)  # restricted to SP
    assert [p["code"] for p in sp.get("/pm/plans").json()["items"]] == ["PM-SP"]
    occ_plans = {o["pm_plan_id"] for o in sp.get("/pm/occurrences").json()["items"]}
    assert occ_plans == {plans["SP"]["id"]}
    assert [p["id"] for p in sp.get("/pdm/points").json()] == [pts["SP"]["id"]]
    assert {a["point_id"] for a in sp.get("/pdm/alerts").json()["items"]} == {pts["SP"]["id"]}
    assert sp.post(f"/pdm/points/{pts['PM']['id']}/readings", {"value": 1}).status_code == 404
    assert [r["code"] for r in sp.get("/lubrication/routes").json()] == ["R-SP"]
    assert [p["code"] for p in sp.get("/lubrication/points").json()] == ["LP-SP"]
    assert sp.get(f"/lubrication/points/by-qr/{lps['PM']['qr_token']}").status_code == 404
    assert [r["id"] for r in sp.get("/work-requests").json()["items"]] == [reqs["SP"]["id"]]
    assert sp.get(f"/work-requests/{reqs['PM']['id']}").status_code == 404
    assert sp.post("/work-requests", {"asset_id": lines["PM"]["id"], "title": "Not mine"}).status_code == 403
    notes = [n["link"] for n in sp.get("/notifications").json()["items"] if n["kind"] in ("condition_alert", "work_request")]
    sp_alert = sp.get("/pdm/alerts").json()["items"][0]["id"]
    assert f"/pdm/alerts/{sp_alert}" in notes and f"/requests/{reqs['SP']['id']}" in notes
    assert all(reqs["PM"]["id"] not in n for n in notes) and len(notes) == 2  # nothing about PM equipment
    # whole-plant users (no department) still see both
    assert len(rel.ok("get", "/pdm/points")) == 2 and len(planner.ok("get", "/pm/plans")["items"]) == 2


def test_general_department_types_for_any_industry(world):
    admin = world.api("admin")
    d = admin.ok("post", "/departments", {"code": "PACK", "name": "Packaging line", "type": "PRODUCTION"}, status=201)
    assert d["type"] == "PRODUCTION"
    assert admin.post("/departments", {"code": "X1", "name": "Bad", "type": "NOPE"}).status_code == 422
