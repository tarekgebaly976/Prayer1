"""Admin-controlled roles & permissions, creating an empty plant, and removing / replacing imported plans."""

from datetime import date

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.permissions import ROLES
from app.models.identity import Role
from app.services.common import plant_today, role_permissions, sync_rbac
from tests.conftest import mk_asset
from tests.test_pm_import import HEADER, LUBE_HEADER, PDM_HEADER, _xlsx


def _matrix(api):
    return {r["code"]: r for r in api.ok("get", "/roles/matrix")}


# ---------- roles & permissions ----------
def test_admin_takes_approval_away_from_supervisors_and_it_applies_at_once(world):
    admin = world.api("admin")
    sup = world.api("mech_sup")
    assert "wo.approve" in _matrix(admin)["mech_supervisor"]["permissions"]
    perms = [p for p in _matrix(admin)["mech_supervisor"]["permissions"] if p != "wo.approve"]
    admin.ok("put", "/roles/mech_supervisor/permissions", {"permissions": perms})
    m = _matrix(admin)["mech_supervisor"]
    assert "wo.approve" not in m["permissions"] and m["customized"] and m["builtin"]
    me = sup.ok("get", "/auth/me")
    assert "wo.approve" not in next(p for p in me["plants"] if p["plant_code"] == "P1")["permissions"]

    # A restart (sync_rbac) keeps the administrator's edit.
    with SessionLocal() as db, db.begin():
        sync_rbac(db)
        role = db.execute(select(Role).where(Role.code == "mech_supervisor")).scalar_one()
        assert "wo.approve" not in role_permissions(db, role.id)

    # Reset puts the default matrix back.
    r = admin.ok("post", "/roles/mech_supervisor/reset")
    assert set(r["permissions"]) == ROLES["mech_supervisor"][1]
    assert not _matrix(admin)["mech_supervisor"]["customized"]


def test_only_system_admin_edits_roles_and_admin_role_is_locked(world):
    admin = world.api("admin")
    assert world.api("manager").put("/roles/technician/permissions", {"permissions": []}).status_code == 403
    assert world.api("tech").get("/roles/matrix").status_code == 403
    assert admin.put("/roles/system_admin/permissions", {"permissions": []}).status_code == 409
    assert admin.put("/roles/technician/permissions", {"permissions": ["nope.x"]}).status_code == 422
    assert admin.delete("/roles/technician").status_code == 409  # built-in roles are not deleted


def test_custom_role_copy_assign_and_delete(world):
    admin = world.api("admin")
    r = admin.ok("post", "/roles", {"name": "Area Engineer", "copy_from": "engineer"}, status=201)
    assert set(r["permissions"]) == ROLES["engineer"][1]
    code = r["code"]
    assert admin.post("/roles", {"name": "area engineer"}).status_code == 409
    admin.ok("patch", f"/roles/{code}", {"name": "Area Engineer PM"})
    assert any(x["code"] == code for x in admin.ok("get", "/roles"))
    # Give it to a user; then it cannot be deleted until the user has another role.
    tech = world.users["tech2"]
    admin.ok("patch", f"/users/{tech.id}", {"role": code})
    assert _matrix(admin)[code]["members"] == 1
    assert admin.delete(f"/roles/{code}").status_code == 409
    admin.ok("patch", f"/users/{tech.id}", {"role": "technician"})
    admin.ok("delete", f"/roles/{code}", status=204)
    assert code not in _matrix(admin)


# ---------- new, empty plant ----------
def test_system_admin_creates_an_empty_plant(world):
    admin = world.api("admin")
    p = admin.ok("post", "/plants", {"code": "mill2", "name": "New Mill", "departments": "paper"}, status=201)
    assert p["code"] == "MILL2"
    assert admin.post("/plants", {"code": "MILL2", "name": "Again"}).status_code == 409
    assert admin.post("/plants", {"code": "X3", "name": "Bad tz", "timezone": "Mars/Base"}).status_code == 422
    assert world.api("manager").post("/plants", {"code": "M3", "name": "Nope"}).status_code == 403
    me = admin.ok("get", "/auth/me")
    assert "MILL2" in {x["plant_code"] for x in me["plants"]}
    world.plant.id = p["id"]  # talk to the new plant
    new = world.api("admin")
    assert {d["code"] for d in new.ok("get", "/departments")} == {"PM", "SP", "FH", "WWTP", "EAI", "UTIL"}
    assert new.ok("get", "/assets")["total"] == 0
    assert new.ok("get", "/pm/plans")["total"] == 0
    assert len(new.ok("get", "/workflow/transitions")) > 0


# ---------- remove / replace plans ----------
def test_unused_pm_plan_is_deleted_and_used_one_deactivated(world):
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM-LINE")
    mk_asset(planner, world, "PM-DRYER", level="unit", parent=line["id"])
    today = plant_today(world.plant).isoformat()
    rows = [
        HEADER,
        ["PM-DRYER", "weekly", "Check coupling", "Mechanical", 30, 1, "online", today, ""],
        ["PM-DRYER", "yearly", "Overhaul", "Mechanical", 60, 1, "", "2030-01-01", ""],
    ]
    planner.ok("post", "/imports/pm_plans/commit", files=_xlsx(rows))
    plans = {p["code"]: p for p in planner.ok("get", "/pm/plans")["items"]}
    weekly, yearly = plans["PM-DRYER-W-MECH"], plans["PM-DRYER-Y-MECH"]
    assert planner.ok("post", "/pm/scheduler/run", {})["work_orders_created"] >= 1  # the weekly plan has a work order

    assert world.api("tech").post("/pm/plans/remove", {"ids": [weekly["id"]]}).status_code == 403
    r = planner.ok("post", "/pm/plans/remove", {"ids": [weekly["id"], yearly["id"]]})
    assert r["deleted"] == 1 and r["deactivated"] == 1 and r["open_work_orders"] == 1
    left = {p["code"]: p for p in planner.ok("get", "/pm/plans")["items"]}
    assert set(left) == {"PM-DRYER-W-MECH~OFF"} and not left["PM-DRYER-W-MECH~OFF"]["is_active"]
    occ = planner.ok("get", "/pm/occurrences", params={"plan_id": weekly["id"]})["items"]
    assert all(o["status"] in ("generated", "cancelled") for o in occ)
    # The same file imports again: the codes are free.
    assert planner.ok("post", "/imports/pm_plans/commit", files=_xlsx(rows))["created"] == 2
    assert planner.delete(f"/pm/plans/{yearly['id']}").status_code == 404


def test_replace_existing_plans_on_import(world):
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM-LINE")
    mk_asset(planner, world, "PM-DRYER", level="unit", parent=line["id"])
    mk_asset(planner, world, "PM-PRESS", level="unit", parent=line["id"])
    first = [
        HEADER,
        ["PM-DRYER", "monthly", "Old task", "Mechanical", 30, 1, "", "", ""],
        ["PM-PRESS", "monthly", "Keep", "Mechanical", 30, 1, "", "", ""],
    ]
    planner.ok("post", "/imports/pm_plans/commit", files=_xlsx(first))
    second = [
        HEADER,
        ["PM-DRYER", "monthly", "New task", "Mechanical", 30, 1, "", "", ""],
        ["PM-DRYER", "weekly", "Grease", "Mechanical", 10, 1, "", "", ""],
    ]
    # Without replace the monthly plan clashes; the replace preview validates against the result and changes nothing.
    assert planner.ok("post", "/imports/pm_plans/preview", files=_xlsx(second))["invalid"] == 1
    p = planner.ok("post", "/imports/pm_plans/preview", files=_xlsx(second), data={"replace": "true"})
    assert p["invalid"] == 0 and p["replaced"]["deleted"] == 1
    assert planner.ok("get", "/pm/plans")["total"] == 2
    r = planner.ok("post", "/imports/pm_plans/commit", files=_xlsx(second), data={"replace": "true"})
    assert r["created"] == 2 and r["replaced"] == {"assets": 1, "deleted": 1, "deactivated": 0, "open_work_orders": 0}
    codes = {p["code"] for p in planner.ok("get", "/pm/plans")["items"]}
    assert codes == {"PM-DRYER-M-MECH", "PM-DRYER-W-MECH", "PM-PRESS-M-MECH"}  # PM-PRESS is not in the file: kept
    assert planner.post("/imports/work_orders/preview", files=_xlsx([["asset_code"], ["X"]]), data={"replace": "true"}).status_code == 422


def test_pdm_and_lube_points_removed(world):
    rel = world.api("reliability")
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM-LINE")
    mk_asset(planner, world, "PM-PRESS", level="unit", parent=line["id"])
    rows = [
        PDM_HEADER,
        ["PM-PRESS", "DE vibration", "vibration", "mm/s", "monthly", 4.5, 7.1, "", "", "", "", "", ""],
        ["PM-PRESS", "NDE vibration", "vibration", "mm/s", "monthly", 4.5, 7.1, "", "", "", "", "", ""],
    ]
    rel.ok("post", "/imports/pdm_plans/commit", files=_xlsx(rows))
    pts = {p["code"]: p for p in rel.ok("get", "/pdm/points")}
    world.api("tech").ok("post", f"/pdm/points/{pts['PM-PRESS-CM01']['id']}/readings", {"value": 2.0}, status=201)
    r = rel.ok("post", "/pdm/points/remove", {"ids": [p["id"] for p in pts.values()]})
    assert r["deleted"] == 1 and r["deactivated"] == 1
    assert rel.ok("get", "/pdm/points") == []
    assert [p["code"] for p in rel.ok("get", "/pdm/points", params={"include_inactive": True})] == ["PM-PRESS-CM01~OFF"]
    # Replace the whole PdM plan of the press: the round goes too, and the file imports cleanly.
    rp = rel.ok("post", "/imports/pdm_plans/commit", files=_xlsx(rows), data={"replace": "true"})
    assert rp["created"] == 2 and rp["replaced"]["deleted"] == 1  # the unused PdM round
    assert {p["code"] for p in rel.ok("get", "/pdm/points")} == {"PM-PRESS-CM01", "PM-PRESS-CM02"}

    lube = [
        LUBE_HEADER,
        [
            "PM-PRESS",
            "DE bearing",
            "GR-EP2",
            "Mobilux EP 2",
            "grease",
            "NLGI 2",
            20,
            "g",
            "Grease gun",
            "weekly",
            "",
            date.today().isoformat(),
            "",
        ],
    ]
    planner.ok("post", "/imports/lube_plans/commit", files=_xlsx(lube))
    lp = planner.ok("get", "/lubrication/points")[0]
    assert planner.ok("delete", f"/lubrication/points/{lp['id']}")["deleted"] == 1
    assert planner.ok("get", "/lubrication/points") == []
