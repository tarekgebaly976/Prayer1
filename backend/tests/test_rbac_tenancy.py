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
    assert tech.post("/assets", {"code": "X", "name": "X", "department_id": str(world.depts["PM"].id),
                                 "level": "production_line"}).status_code == 403
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
    lb = b.ok("post", "/assets", {"code": "L", "name": "L", "department_id": str(world.depts_b["PM"].id), "level": "production_line"}, status=201)
    wa = a.ok("post", "/work-orders", {"asset_id": la["id"], "type": "corrective", "title": "aaa"}, status=201)
    wb = b.ok("post", "/work-orders", {"asset_id": lb["id"], "type": "corrective", "title": "bbb"}, status=201)
    assert wa["number"] == "WO-P1-000001" and wb["number"] == "WO-P2-000001"
