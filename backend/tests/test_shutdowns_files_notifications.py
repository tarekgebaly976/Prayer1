from app.core.config import get_settings
from tests.conftest import login, mk_asset

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_shutdown_cpm_and_readiness(world):
    mgr = world.api("manager")
    sd = mgr.ok("post", "/shutdowns", {"code": "SD-2026-11", "name": "PM1 annual", "planned_start": "2026-11-10T06:00:00+03:00",
                                       "planned_end": "2026-11-11T06:00:00+03:00"}, status=201)
    sid = sd["id"]
    a = mgr.ok("post", f"/shutdowns/{sid}/packages", {"code": "A", "name": "LOTO & drain", "duration_hours": 10, "material_status": "not_required",
                                                      "permit_status": "ready", "loto_status": "ready"}, status=201)
    b = mgr.ok("post", f"/shutdowns/{sid}/packages", {"code": "B", "name": "Felt change", "duration_hours": 5, "predecessor_ids": [a["id"]]}, status=201)
    c = mgr.ok("post", f"/shutdowns/{sid}/packages", {"code": "C", "name": "Roll change", "duration_hours": 8, "predecessor_ids": [a["id"]]}, status=201)
    d = mgr.ok("post", f"/shutdowns/{sid}/packages", {"code": "D", "name": "Restart checks", "duration_hours": 2,
                                                      "predecessor_ids": [b["id"], c["id"]]}, status=201)
    det = mgr.get(f"/shutdowns/{sid}").json()
    assert det["cpm"]["duration_hours"] == 20 and det["cpm"]["critical_path"] == ["A", "C", "D"] and det["cpm"]["fits_window"]
    pk = {p["code"]: p for p in det["packages"]}
    assert pk["B"]["total_float_hours"] == 3 and not pk["B"]["is_critical"]
    from datetime import datetime
    assert datetime.fromisoformat(pk["D"]["planned_start"]) == datetime.fromisoformat("2026-11-11T00:00:00+03:00")  # start + 18 h
    r = mgr.post(f"/shutdowns/{sid}/packages/{a['id']}/dependencies", {"predecessor_id": d["id"]})
    assert r.status_code == 422 and "cycle" in r.text
    assert det["readiness"]["permits_ready_pct"] == 25.0
    mgr.ok("post", f"/shutdowns/{sid}/packages/{a['id']}/progress", {"progress_pct": 100}, status=201)
    mgr.ok("post", f"/shutdowns/{sid}/packages/{c['id']}/progress", {"progress_pct": 50, "delay_reason": "Crane breakdown"}, status=201)
    det = mgr.get(f"/shutdowns/{sid}").json()
    assert det["readiness"]["weighted_progress_pct"] == round((10 * 100 + 8 * 50) / 25, 1)
    assert det["readiness"]["delayed"][0]["code"] == "C"
    chk = mgr.ok("post", f"/shutdowns/{sid}/checks", {"category": "pre_startup", "description": "Guards reinstalled"}, status=201)
    mgr.ok("patch", f"/shutdowns/{sid}", {"status": "in_progress"})
    assert mgr.patch(f"/shutdowns/{sid}", {"status": "completed"}).status_code == 409
    mgr.ok("post", f"/shutdowns/{sid}/checks/{chk['id']}/complete", {"result": "All guards fitted, signed"})
    mgr.ok("patch", f"/shutdowns/{sid}", {"status": "completed", "lessons_learned": "Pre-stage crane"})
    k = mgr.get("/kpis/shutdown_progress", params={"start": "2026-11-01", "end": "2026-11-30"}).json()
    assert k["value"] == 56.0


def _upload(api, entity_type, entity_id, name, data, category="document"):
    return api.post("/attachments", files={"file": (name, data, "application/octet-stream")},
                    data={"entity_type": entity_type, "entity_id": entity_id, "category": category})


def test_file_upload_validation_and_authorization(world):
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM1")
    r = _upload(planner, "asset", line["id"], "manual.pdf", PDF, "manual")
    assert r.status_code == 201
    att = r.json()
    assert _upload(planner, "asset", line["id"], "evil.exe", b"MZ\x90\x00").status_code == 415
    assert _upload(planner, "asset", line["id"], "fake.pdf", PNG).status_code == 415  # content/extension mismatch
    assert _upload(planner, "asset", line["id"], "x.svg", b"<svg onload=alert(1)>").status_code == 415
    assert _upload(planner, "asset", line["id"], "notes.txt", b"<html><script>alert(1)</script>").status_code == 415
    assert _upload(planner, "asset", line["id"], "photo.png", PNG, "photo").status_code == 201
    s = get_settings()
    old = s.max_upload_mb
    s.max_upload_mb = 0
    try:
        assert _upload(planner, "asset", line["id"], "big.pdf", PDF).status_code == 413
    finally:
        s.max_upload_mb = old
    dl = world.api("tech").get(f"/attachments/{att['id']}/download")
    assert dl.status_code == 200 and dl.content == PDF and "attachment" in dl.headers["content-disposition"]
    assert dl.headers["x-content-type-options"] == "nosniff"
    other = login("planner_b@example.com", world.plant_b.id)
    assert other.get(f"/attachments/{att['id']}/download").status_code == 404
    assert world.api("store").post("/attachments", files={"file": ("m.pdf", PDF)},
                                   data={"entity_type": "asset", "entity_id": line["id"]}).status_code == 403
    assert _upload(other, "asset", line["id"], "m.pdf", PDF).status_code == 404  # cannot attach to another plant's asset
    lst = planner.get("/attachments", params={"entity_type": "asset", "entity_id": line["id"]}).json()
    assert len(lst) == 2
    assert world.api("tech").delete(f"/attachments/{att['id']}").status_code == 403  # not uploader
    planner.ok("delete", f"/attachments/{att['id']}")
    assert planner.get(f"/attachments/{att['id']}/download").status_code == 404


def test_notifications_dedupe_read_and_outbox(world):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.enums import DeliveryStatus
    from app.models.system import EmailOutbox
    from app.services.notifications import notify
    with SessionLocal() as db, db.begin():
        n1 = notify(db, world.plant.id, [world.users["tech"].id], kind="t", title="Hello", dedupe_key="k1", email=True)
        n2 = notify(db, world.plant.id, [world.users["tech"].id], kind="t", title="Hello", dedupe_key="k1", email=True)
    assert (n1, n2) == (1, 0)
    with SessionLocal() as db:
        rows = db.execute(select(EmailOutbox)).scalars().all()
    assert len(rows) == 1 and rows[0].status == DeliveryStatus.DISABLED  # no SMTP configured → never silently "sent"
    tech = world.api("tech")
    n = tech.get("/notifications").json()
    assert n["unread"] == 1
    tech.ok("post", f"/notifications/{n['items'][0]['id']}/read")
    assert tech.get("/notifications").json()["unread"] == 0
    assert world.api("tech2").post(f"/notifications/{n['items'][0]['id']}/read").status_code == 404


def test_new_request_notifies_triagers(world):
    prod, sup = world.api("production"), world.api("mech_sup")
    line = mk_asset(world.api("planner"), world, "PM1")
    prod.ok("post", "/work-requests", {"asset_id": line["id"], "title": "Sheet break repeatedly", "is_breakdown": True}, status=201)
    items = sup.get("/notifications").json()["items"]
    assert any(i["kind"] == "work_request" and i["severity"] == "critical" for i in items)
    assert sup.get("/dashboard/summary").json()["new_requests"] == 1
