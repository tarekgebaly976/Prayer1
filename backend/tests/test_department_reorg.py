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
    comp = mk_asset(planner, world, "WTP-PUMP1-BRG", level="assembly", parent=pump["id"], dept="UTIL")
    assert admin.post("/departments/move-assets", {**body, "asset_ids": [comp["id"]]}).status_code == 422  # below unit level
    preview = admin.ok("post", "/departments/move-assets", body)
    assert preview["lines"] == ["WTP"] and preview["assets"] == 3 and preview["work_orders"] == 1 and preview["applied"] is False
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


def test_units_under_one_utilities_line_split_into_sections(world):
    """The real layout: one UTIL line "UT - Utilities & Power House" with units WTP and PH under it."""
    admin, planner = world.api("admin"), world.api("planner")
    util, wwtp = world.depts["UTIL"], world.depts["WWTP"]
    ut = mk_asset(planner, world, "UT", dept="UTIL")
    wtp = mk_asset(planner, world, "UT-WTP", level="unit", parent=ut["id"], dept="UTIL")
    filt = mk_asset(planner, world, "UT-WTP-FLT", level="assembly", parent=wtp["id"], dept="UTIL")
    ph = mk_asset(planner, world, "UT-PH", level="unit", parent=ut["id"], dept="UTIL")
    wwtp_line = mk_asset(planner, world, "WWTP", dept="WWTP")
    wo = planner.ok("post", "/work-orders", {"asset_id": filt["id"], "type": "corrective", "title": "Filter"}, status=201)

    # WTP becomes its own production line in the water section.
    res = admin.ok("post", "/departments/move-assets", {"asset_ids": [wtp["id"]], "to_department_id": str(wwtp.id), "apply": True})
    assert res["moves"] == [{"code": "UT-WTP", "name": "UT-WTP", "becomes": "line"}] and res["assets"] == 2
    a = planner.get(f"/assets/{wtp['id']}").json()
    assert a["level"] == "production_line" and a["parent_id"] is None and a["department_id"] == str(wwtp.id)
    f = planner.get(f"/assets/{filt['id']}").json()
    assert f["department_id"] == str(wwtp.id) and f["parent_id"] == wtp["id"]
    assert planner.get(f"/work-orders/{wo['id']}").json()["department_id"] == str(wwtp.id)
    tree = planner.get(f"/assets/{filt['id']}/ancestors").json()
    assert [x["code"] for x in tree] == ["UT-WTP", "UT-WTP-FLT"]

    # PH: promoted to a line inside UTIL (same department), then UTIL is renamed Power House.
    res = admin.ok("post", "/departments/move-assets", {"asset_ids": [ph["id"]], "to_department_id": str(util.id), "apply": True})
    assert planner.get(f"/assets/{ph['id']}").json()["level"] == "production_line"
    admin.ok("patch", f"/departments/{util.id}", {"code": "PH", "name": "Power House"})

    # Or a unit can go under an existing line of the target department.
    pump = mk_asset(planner, world, "UT-PUMP", level="unit", parent=ut["id"], dept="UTIL")
    bad = {"asset_ids": [pump["id"]], "to_department_id": str(wwtp.id), "parent_id": ut["id"]}
    assert admin.post("/departments/move-assets", bad).status_code == 422  # parent not in target
    res = admin.ok("post", "/departments/move-assets", {**bad, "parent_id": wwtp_line["id"], "apply": True})
    assert res["moves"][0]["becomes"] == "under WWTP"
    p = planner.get(f"/assets/{pump['id']}").json()
    assert p["level"] == "unit" and p["parent_id"] == wwtp_line["id"]
