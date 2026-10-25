import io

from openpyxl import Workbook

from tests.conftest import mk_asset


def test_hierarchy_example_and_rules(world):
    api = world.api("planner")
    pm = mk_asset(api, world, "PM1")
    wire = mk_asset(api, world, "PM1-WIRE", "unit", pm["id"])
    utw = mk_asset(api, world, "PM1-WIRE-UTW", "assembly", wire["id"])
    dr1 = mk_asset(api, world, "PM1-WIRE-UTW-DR1", "sub_assembly", utw["id"])
    brg = mk_asset(api, world, "PM1-WIRE-UTW-DR1-BRG", "component", dr1["id"])
    anc = api.get(f"/assets/{brg['id']}/ancestors").json()
    assert [a["code"] for a in anc] == ["PM1", "PM1-WIRE", "PM1-WIRE-UTW", "PM1-WIRE-UTW-DR1", "PM1-WIRE-UTW-DR1-BRG"]
    # a unit cannot be placed under a component; a non-line cannot be top-level; parent must share department
    assert api.post("/assets", {"code": "BAD", "name": "b", "department_id": str(world.depts["PM"].id), "level": "unit",
                                "parent_id": brg["id"]}).status_code == 422
    assert api.post("/assets", {"code": "BAD2", "name": "b", "department_id": str(world.depts["PM"].id),
                                "level": "unit"}).status_code == 422
    assert api.post("/assets", {"code": "BAD3", "name": "b", "department_id": str(world.depts["SP"].id), "level": "unit",
                                "parent_id": pm["id"]}).status_code == 422
    assert api.post("/assets", {"code": "PM1", "name": "dup", "department_id": str(world.depts["PM"].id),
                                "level": "production_line"}).status_code == 409
    sub = api.get("/assets", params={"under": wire["id"]}).json()
    assert sub["total"] == 3
    tree = api.get("/assets/tree", params={"parent_id": pm["id"]}).json()
    assert tree[0]["code"] == "PM1-WIRE" and tree[0]["child_count"] == 1
    assert api.get(f"/assets/by-qr/{brg['qr_token']}").json()["id"] == brg["id"]
    assert api.get(f"/assets/{brg['id']}/qr.png").headers["content-type"] == "image/png"


def test_move_subtree_updates_paths(world):
    api = world.api("planner")
    pm = mk_asset(api, world, "PM1")
    u1 = mk_asset(api, world, "U1", "unit", pm["id"])
    u2 = mk_asset(api, world, "U2", "unit", pm["id"])
    a1 = mk_asset(api, world, "A1", "assembly", u1["id"])
    c1 = mk_asset(api, world, "C1", "component", a1["id"])
    api.ok("patch", f"/assets/{a1['id']}", {"parent_id": u2["id"]})
    moved = api.get(f"/assets/{c1['id']}").json()
    assert moved["path"].startswith(api.get(f"/assets/{u2['id']}").json()["path"])
    assert api.patch(f"/assets/{u2['id']}", {"parent_id": c1["id"]}).status_code == 422  # level and cycle protection


def test_status_history(world):
    api = world.api("planner")
    pm = mk_asset(api, world, "PM1")
    api.ok("patch", f"/assets/{pm['id']}", {"status": "standby", "status_note": "Grade change"})
    h = api.get(f"/assets/{pm['id']}/history").json()
    assert h["status_history"][0]["to"] == "standby"


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_asset_import_preview_errors_duplicates_and_commit(world):
    api = world.api("planner")
    mk_asset(api, world, "EXISTING")
    header = ["code", "name", "department_code", "parent_code", "level", "criticality"]
    bad = _xlsx([header,
                 ["SP1", "Stock prep", "SP", "", "production_line", "A"],
                 ["SP1-PULP", "Pulper", "SP", "SP1", "unit", "A"],
                 ["SP1-PULP", "Pulper again", "SP", "SP1", "unit", "B"],  # duplicate in file
                 ["EXISTING", "dup", "PM", "", "production_line", "A"],   # duplicate in DB
                 ["X1", "bad level", "SP", "SP1", "rotor", "Z"],
                 ["ORPHAN", "orphan", "SP", "NOPE", "unit", "C"]])
    files = {"file": ("assets.xlsx", bad, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    p = api.ok("post", "/imports/assets/preview", files=files)
    assert p["total"] == 6 and p["invalid"] == 4
    msgs = {e["row"]: " ".join(e["errors"]) for e in p["errors"]}
    assert "duplicate code in file" in msgs[4] and "already exists" in msgs[5] and "invalid level" in msgs[6] and "not found" in msgs[7]
    r = api.post("/imports/assets/commit", files=files)
    assert r.status_code == 422
    assert api.get("/assets", params={"q": "SP1"}).json()["total"] == 0  # nothing partially imported
    err = api.post("/imports/assets/errors.csv", files=files)
    assert err.status_code == 200 and "duplicate" in err.text
    good = "code,name,department_code,parent_code,level,criticality\nSP1-PULP,Pulper,SP,SP1,unit,A\nSP1,Stock prep,SP,,production_line,A\n"
    files = {"file": ("a.csv", good.encode(), "text/csv")}
    assert api.ok("post", "/imports/assets/commit", files=files)["created"] == 2  # child listed before parent is fine
    tmpl = api.get("/imports/templates/assets.xlsx")
    assert tmpl.status_code == 200 and tmpl.content[:2] == b"PK"


def test_export_csv_formula_injection_neutralised(world):
    api = world.api("planner")
    api.ok("post", "/assets", {"code": "L1", "name": "=HYPERLINK(\"x\")", "department_id": str(world.depts["PM"].id),
                               "level": "production_line"}, status=201)
    r = api.get("/exports/assets.csv")
    assert "'=HYPERLINK" in r.text
