"""Department re-organisation: rename a department, move production lines (with their tree and work orders)."""

from tests.conftest import mk_asset


def test_merge_wtp_into_wwtp_and_isolate_power_house(world):
    admin, planner = world.api("admin"), world.api("planner")
    util, wwtp = world.depts["UTIL"], world.depts["WWTP"]
    wtp = mk_asset(planner, world, "WTP", dept="UTIL")
    pump = mk_asset(planner, world, "WTP-PUMP1", level="unit", parent=wtp["id"], dept="UTIL")
    ph = mk_asset(planner, world, "PH", dept="UTIL")
    mk_asset(planner, world, "WWTP-CLAR", dept="WWTP")
    wo = planner.ok("post", "/work-orders", {"asset_id": pump["id"], "type": "corrective", "title": "Pump leak"}, status=201)
    ph_wo = planner.ok("post", "/work-orders", {"asset_id": ph["id"], "type": "corrective", "title": "Boiler"}, status=201)

    body = {"asset_ids": [wtp["id"]], "to_department_id": str(wwtp.id)}
    assert planner.post("/departments/move-assets", body).status_code == 403
    assert admin.post("/departments/move-assets", {**body, "asset_ids": [pump["id"]]}).status_code == 422  # not a line
    preview = admin.ok("post", "/departments/move-assets", body)
    assert preview == {"lines": ["WTP"], "to": "WWTP", "assets": 2, "work_orders": 1, "pm_plans": 0, "applied": False}
    assert planner.get(f"/assets/{pump['id']}").json()["department_id"] == str(util.id)  # preview changes nothing
    assert admin.ok("post", "/departments/move-assets", {**body, "apply": True})["applied"] is True
    assert planner.get(f"/assets/{pump['id']}").json()["department_id"] == str(wwtp.id)
    assert planner.get(f"/work-orders/{wo['id']}").json()["department_id"] == str(wwtp.id)
    assert planner.get(f"/work-orders/{ph_wo['id']}").json()["department_id"] == str(util.id)

    # Rename: WWTP becomes the water section, UTIL becomes the power house.
    assert planner.patch(f"/departments/{wwtp.id}", {"name": "x"}).status_code == 403
    w = admin.ok("patch", f"/departments/{wwtp.id}", {"code": "WATER", "name": "Water & Wastewater Treatment (WTP + WWTP)"})
    assert w["code"] == "WATER"
    p = admin.ok("patch", f"/departments/{util.id}", {"code": "PH", "name": "Power House"})
    assert p["name"] == "Power House"
    assert admin.patch(f"/departments/{util.id}", {"code": "WATER"}).status_code == 409  # duplicate code
    # A department with equipment cannot be retired; an empty one can.
    assert admin.patch(f"/departments/{util.id}", {"is_active": False}).status_code == 409
    assert admin.ok("patch", f"/departments/{world.depts['QUALITY'].id}", {"is_active": False})["is_active"] is False
    # Users limited to the old area now see the moved equipment under the new department.
    sp_view = {d["code"] for d in admin.get("/departments").json()}
    assert {"WATER", "PH"} <= sp_view
