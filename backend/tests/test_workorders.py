from datetime import UTC, datetime, timedelta

from tests.conftest import mk_asset


def _codes(api):
    fc = api.get("/failure-codes").json()
    return {f["kind"]: f["id"] for f in fc}


def _setup_codes(admin):
    for kind, code in (("problem", "VIB"), ("cause", "WEAR"), ("remedy", "REPL")):
        admin.ok("post", "/failure-codes", {"kind": kind, "code": code, "description": code}, status=201)


def test_full_lifecycle_request_to_technical_closure(world):
    """Acceptance C: request → triage → approval → planning → scheduling → execution → testing → completion → closure."""
    admin, planner, sup, tech = world.api("admin"), world.api("planner"), world.api("mech_sup"), world.api("tech")
    prod = world.api("production")
    _setup_codes(admin)
    codes = _codes(admin)
    line = mk_asset(planner, world, "PM1")
    req = prod.ok("post", "/work-requests", {"asset_id": line["id"], "title": "Bearing noise DS", "symptoms": "grinding"}, status=201)
    assert tech.post(f"/work-requests/{req['id']}/triage", {"accept": True}).status_code == 403
    tri = sup.ok("post", f"/work-requests/{req['id']}/triage", {"accept": True, "type": "corrective", "priority": "P2"})
    wo_id = tri["work_order_id"]
    wo = planner.get(f"/work-orders/{wo_id}").json()
    assert wo["status"] == "triage" and wo["priority"] == "P2"
    planner.ok("post", f"/work-orders/{wo_id}/status", {"to": "awaiting_approval"})
    assert planner.post(f"/work-orders/{wo_id}/status", {"to": "approved"}).status_code == 403  # planner can't approve
    sup.ok("post", f"/work-orders/{wo_id}/status", {"to": "approved", "comment": "ok"})
    start = datetime.now(UTC) + timedelta(hours=1)
    assert planner.post(f"/work-orders/{wo_id}/status", {"to": "scheduled"}).status_code == 409  # needs planned_start
    planner.ok("patch", f"/work-orders/{wo_id}", {"planned_start": start.isoformat(), "planned_end": (start + timedelta(hours=4)).isoformat(),
                                                   "estimated_hours": 4, "requires_loto": True, "requires_testing": True,
                                                   "supervisor_id": str(world.users["mech_sup"].id)})
    planner.ok("post", f"/work-orders/{wo_id}/status", {"to": "scheduled"})
    planner.ok("post", f"/work-orders/{wo_id}/assign", {"user_ids": [str(world.users["tech"].id)], "lead_id": str(world.users["tech"].id)})
    tech2 = world.api("tech2")
    assert tech2.post(f"/work-orders/{wo_id}/status", {"to": "in_progress"}).status_code == 403  # not assigned
    r = tech.post(f"/work-orders/{wo_id}/status", {"to": "in_progress"})
    assert r.status_code == 409 and "LOTO" in r.text
    assert sup.post(f"/work-orders/{wo_id}/safety-signoff", {}).status_code == 409  # no isolation point recorded yet
    lock = tech.ok("post", f"/work-orders/{wo_id}/loto", {"point": "MCC-12 breaker Q3", "lock_number": "L-17",
                                                          "zero_energy_verified": True}, status=201)
    sup.ok("post", f"/work-orders/{wo_id}/safety-signoff", {"note": "LOTO applied at MCC-12"})
    tech.ok("post", f"/work-orders/{wo_id}/status", {"to": "in_progress"})
    tech.ok("post", f"/work-orders/{wo_id}/labor", {"work_date": datetime.now(UTC).date().isoformat(), "hours": 3})
    tech.ok("patch", f"/work-orders/{wo_id}", {"findings": "Outer race spalled", "root_cause": "Grease starvation",
                                                "problem_code_id": codes["problem"], "cause_code_id": codes["cause"],
                                                "remedy_code_id": codes["remedy"]})
    assert tech.patch(f"/work-orders/{wo_id}", {"priority": "P1"}).status_code == 403  # planning field
    tech.ok("post", f"/work-orders/{wo_id}/status", {"to": "awaiting_review"})
    r = sup.post(f"/work-orders/{wo_id}/status", {"to": "completed"})
    assert r.status_code == 409 and "test" in r.text.lower() and "LOTO locks" in r.text
    tech.ok("post", f"/work-orders/{wo_id}/loto/{lock['id']}/remove", status=204)
    sup.ok("post", f"/work-orders/{wo_id}/test-result", {"test_result": "Run 30 min, 2.1 mm/s, 58 °C", "test_passed": True})
    sup.ok("post", f"/work-orders/{wo_id}/status", {"to": "completed"})
    assert tech.post(f"/work-orders/{wo_id}/status", {"to": "closed"}).status_code == 403
    sup.ok("post", f"/work-orders/{wo_id}/status", {"to": "closed"})
    d = planner.get(f"/work-orders/{wo_id}/detail").json()
    assert d["work_order"]["status"] == "closed"
    assert float(d["work_order"]["actual_labor_cost"]) == 240.0  # 3 h × 80/h technician rate
    assert [h["to"] for h in d["history"]] == ["triage", "awaiting_approval", "approved", "scheduled", "in_progress",
                                               "awaiting_review", "completed", "closed"]
    assert planner.patch(f"/work-orders/{wo_id}", {"title": "changed"}).status_code == 409  # closed is read-only
    pdf = planner.get(f"/reports/work-orders/{wo_id}.pdf")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"


def test_emergency_fast_track_and_closure_controls(world):
    admin, sup, tech, planner = world.api("admin"), world.api("mech_sup"), world.api("tech"), world.api("planner")
    _setup_codes(admin)
    codes = _codes(admin)
    line = mk_asset(planner, world, "PM1")
    corr = planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "corrective", "title": "Minor leak"}, status=201)
    assert sup.post(f"/work-orders/{corr['id']}/status", {"to": "in_progress"}).status_code == 409  # only emergencies bypass approval
    em = planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "emergency", "title": "Wire drive trip"}, status=201)
    assert em["priority"] == "P1"
    notes = sup.get("/notifications").json()
    assert any("Emergency breakdown" in n["title"] for n in notes["items"])
    sup.ok("post", f"/work-orders/{em['id']}/assign", {"user_ids": [str(world.users["tech"].id)]})
    tech.ok("post", f"/work-orders/{em['id']}/status", {"to": "in_progress"})
    assert planner.get(f"/assets/{line['id']}").json()["status"] == "under_maintenance"
    tech.ok("post", f"/work-orders/{em['id']}/status", {"to": "awaiting_review"})
    r = sup.post(f"/work-orders/{em['id']}/status", {"to": "completed"})
    assert r.status_code == 409 and "Root cause" in r.text and "codes" in r.text
    sup.ok("patch", f"/work-orders/{em['id']}", {"root_cause": "Encoder cable", "problem_code_id": codes["problem"],
                                                  "cause_code_id": codes["cause"], "remedy_code_id": codes["remedy"]})
    sup.ok("post", f"/work-orders/{em['id']}/status", {"to": "completed"})
    assert planner.get(f"/assets/{line['id']}").json()["status"] == "in_service"
    # Make wo.close insufficient: a role with wo.close but not wo.close_emergency (configure planner transition perm)
    assert planner.post(f"/work-orders/{em['id']}/status", {"to": "closed"}).status_code == 403
    sup.ok("post", f"/work-orders/{em['id']}/status", {"to": "closed"})


def test_cancel_requires_reason_and_configurable_transition(world):
    admin, planner = world.api("admin"), world.api("planner")
    line = mk_asset(planner, world, "PM1")
    wo = planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "improvement", "title": "Add guard"}, status=201)
    assert planner.post(f"/work-orders/{wo['id']}/status", {"to": "cancelled"}).status_code == 422
    trs = admin.get("/workflow/transitions").json()
    t = next(x for x in trs if x["from_status"] == "triage" and x["to_status"] == "cancelled")
    admin.ok("patch", f"/workflow/transitions/{t['id']}", {"is_active": False})
    assert planner.post(f"/work-orders/{wo['id']}/status", {"to": "cancelled", "comment": "dup"}).status_code == 409
    admin.ok("patch", f"/workflow/transitions/{t['id']}", {"is_active": True})
    planner.ok("post", f"/work-orders/{wo['id']}/status", {"to": "cancelled", "comment": "duplicate"})


def test_optimistic_concurrency(world):
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM1")
    wo = planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "corrective", "title": "abc"}, status=201)
    planner.ok("patch", f"/work-orders/{wo['id']}", {"title": "first", "version": wo["version"]})
    r = planner.patch(f"/work-orders/{wo['id']}", {"title": "second", "version": wo["version"]})
    assert r.status_code == 409


def test_bulk_assign_and_search(world):
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM1")
    ids = [planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "inspection", "title": f"Insp {i}"}, status=201)["id"] for i in range(3)]
    r = planner.ok("post", "/work-orders/bulk-assign", {"work_order_ids": ids, "user_ids": [str(world.users["tech"].id)]})
    assert r["assigned"] == 3
    mine = world.api("tech").get("/work-orders", params={"assigned_to_me": True}).json()
    assert mine["total"] == 3
    assert planner.get("/work-orders", params={"q": "Insp 1"}).json()["total"] == 1
    assert world.api("tech").post("/work-orders/bulk-assign", {"work_order_ids": ids, "user_ids": [str(world.users["tech"].id)]}).status_code == 403


def test_assignment_conflict_detection(world):
    planner, mgr = world.api("planner"), world.api("manager")
    line = mk_asset(planner, world, "PM1")
    start = datetime.now(UTC) + timedelta(days=2)
    body = {"asset_id": line["id"], "type": "inspection", "title": "Window", "planned_start": start.isoformat(),
            "planned_end": (start + timedelta(hours=3)).isoformat()}
    a = planner.ok("post", "/work-orders", body, status=201)
    b = planner.ok("post", "/work-orders", body, status=201)
    tech_id = str(world.users["tech"].id)
    planner.ok("post", f"/work-orders/{a['id']}/assign", {"user_ids": [tech_id]})
    r = planner.post(f"/work-orders/{b['id']}/assign", {"user_ids": [tech_id]})
    assert r.status_code == 409 and "overlapping" in r.text
    assert planner.ok("post", f"/work-orders/{b['id']}/assign", {"user_ids": [tech_id], "force": True})["warnings"]
    # Leave blocks assignment outright
    from zoneinfo import ZoneInfo
    day = start.astimezone(ZoneInfo("Asia/Riyadh")).date().isoformat()
    mgr.ok("put", "/shifts/roster", {"user_id": str(world.users["tech2"].id), "work_date": day, "kind": "leave", "hours": 0})
    r = planner.post(f"/work-orders/{a['id']}/assign", {"user_ids": [str(world.users["tech2"].id)]})
    assert r.status_code == 409 and "leave" in r.text
