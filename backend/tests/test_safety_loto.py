from datetime import UTC, datetime, timedelta

from tests.conftest import mk_asset


def _ready_wo(world, **flags):
    planner, sup = world.api("planner"), world.api("mech_sup")
    line = mk_asset(planner, world, "PM1")
    wo = planner.ok("post", "/work-orders", {"asset_id": line["id"], "type": "inspection", "title": "Gearbox inspection"}, status=201)
    wid = wo["id"]
    planner.ok("post", f"/work-orders/{wid}/status", {"to": "awaiting_approval"})
    sup.ok("post", f"/work-orders/{wid}/status", {"to": "approved"})
    planner.ok("patch", f"/work-orders/{wid}", {**flags})
    planner.ok("post", f"/work-orders/{wid}/assign", {"user_ids": [str(world.users["tech"].id)], "lead_id": str(world.users["tech"].id)})
    return wid


def test_loto_register_controls_signoff_start_and_completion(world):
    sup, tech, prod = world.api("mech_sup"), world.api("tech"), world.api("production")
    wid = _ready_wo(world, requires_loto=True, requires_permit=True)
    assert tech.post(f"/work-orders/{wid}/status", {"to": "in_progress"}).status_code == 409  # not signed off

    assert prod.post(f"/work-orders/{wid}/loto", {"point": "MCC-3 Q12"}).status_code == 403
    assert tech.post(f"/work-orders/{wid}/loto", {"point": "MCC-3 Q12", "energy_type": "magic"}).status_code == 422
    q12 = tech.ok("post", f"/work-orders/{wid}/loto", {"point": "MCC-3 breaker Q12", "lock_number": "L-04"}, status=201)
    tech.ok(
        "post",
        f"/work-orders/{wid}/loto",
        {"point": "Steam valve HV-204", "energy_type": "steam", "lock_number": "L-05", "zero_energy_verified": True},
        status=201,
    )
    r = sup.post(f"/work-orders/{wid}/safety-signoff", {"permit_reference": "CWP-2026-0412", "permit_types": ["cold_work", "electrical"]})
    assert r.status_code == 409 and "Zero energy" in r.text  # Q12 not verified yet
    assert sup.post(f"/work-orders/{wid}/safety-signoff", {"permit_types": ["teleport"]}).status_code == 422
    tech.ok("post", f"/work-orders/{wid}/loto/{q12['id']}/verify", status=204)
    until = (datetime.now(UTC) + timedelta(hours=8)).isoformat()
    sup.ok(
        "post",
        f"/work-orders/{wid}/safety-signoff",
        {"permit_reference": "CWP-2026-0412", "permit_types": ["cold_work", "electrical"], "permit_valid_until": until},
    )
    tech.ok("post", f"/work-orders/{wid}/status", {"to": "in_progress"})

    d = tech.ok("get", f"/work-orders/{wid}/detail")
    assert d["work_order"]["permit_types"] == "cold_work,electrical"
    assert [(x["point"], x["lock_number"], x["removed_at"]) for x in d["loto"]] == [
        ("MCC-3 breaker Q12", "L-04", None),
        ("Steam valve HV-204", "L-05", None),
    ]
    tech.ok("post", f"/work-orders/{wid}/status", {"to": "awaiting_review"})
    r = sup.post(f"/work-orders/{wid}/status", {"to": "completed"})
    assert r.status_code == 409 and "LOTO locks" in r.text
    for x in d["loto"]:
        tech.ok("post", f"/work-orders/{wid}/loto/{x['id']}/remove", status=204)
    sup.ok("post", f"/work-orders/{wid}/status", {"to": "completed"})
    d = tech.ok("get", f"/work-orders/{wid}/detail")
    assert all(x["removed_by"] == "Tech" for x in d["loto"])


def test_expired_permit_blocks_signoff(world):
    sup, tech = world.api("mech_sup"), world.api("tech")
    wid = _ready_wo(world, requires_permit=True)
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    r = sup.post(
        f"/work-orders/{wid}/safety-signoff", {"permit_reference": "HWP-1", "permit_types": ["hot_work"], "permit_valid_until": past}
    )
    assert r.status_code == 409 and "expired" in r.text
    assert tech.post(f"/work-orders/{wid}/status", {"to": "in_progress"}).status_code == 409


def test_pm_import_sets_permit_and_loto_on_generated_work_orders(world):
    import io

    from openpyxl import Workbook

    planner = world.api("planner")
    mk_asset(planner, world, "PM-DRYER")
    wb = Workbook()
    ws = wb.active
    ws.append(["asset_code", "frequency", "task", "trade", "start_date", "permit", "loto"])
    today = datetime.now(UTC).date().isoformat()
    ws.append(["PM-DRYER", "monthly", "Inspect gearbox", "Mechanical", today, "cold_work", "yes"])
    ws.append(["PM-DRYER", "monthly", "Check guard", "Mechanical", today, "", ""])
    ws.append(["PM-DRYER", "yearly", "Weld repair", "Mechanical", today, "hot_work;work_at_height", "no"])
    ws.append(["PM-DRYER", "yearly", "x", "Electrical", today, "flying", ""])
    b = io.BytesIO()
    wb.save(b)
    files = {"file": ("pm.xlsx", b.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    p = planner.ok("post", "/imports/pm_plans/preview", files=files)
    assert p["invalid"] == 1 and "unknown permit type" in p["errors"][0]["errors"][0]
    ws.delete_rows(5)
    b = io.BytesIO()
    wb.save(b)
    files = {"file": ("pm.xlsx", b.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    planner.ok("post", "/imports/pm_plans/commit", files=files)
    planner.ok("post", "/pm/scheduler/run", {})
    wos = {w["title"]: w for w in planner.get("/work-orders", params={"limit": 50}).json()["items"]}
    monthly = next(w for t, w in wos.items() if "Monthly" in t)
    yearly = next(w for t, w in wos.items() if "Yearly" in t)
    assert monthly["requires_loto"] and monthly["requires_permit"] and monthly["permit_types"] == "cold_work"
    assert yearly["requires_permit"] and not yearly["requires_loto"] and yearly["permit_types"] == "hot_work,work_at_height"
