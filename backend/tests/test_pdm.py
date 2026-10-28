from datetime import UTC, datetime, timedelta

from tests.conftest import Api, make_client, mk_asset


def _point(world, **kw):
    rel = world.api("reliability")
    line = mk_asset(rel, world, "PM1")
    body = {
        "code": "VIB-DR1",
        "name": "DR1 DS velocity",
        "asset_id": line["id"],
        "technique": "vibration",
        "unit": "mm/s",
        "warning_high": 4.5,
        "alarm_high": 7.1,
        "external_tag": "ns=2;s=PM1.DR1.VIB",
        **kw,
    }
    return rel, line, rel.ok("post", "/pdm/points", body, status=201)


def test_reading_warning_alert_and_followup_wo(world):
    """Acceptance G."""
    rel, line, p = _point(world)
    tech, sup = world.api("tech"), world.api("mech_sup")
    assert tech.ok("post", f"/pdm/points/{p['id']}/readings", {"value": 2.1}, status=201)["status"] == "normal"
    r = tech.ok("post", f"/pdm/points/{p['id']}/readings", {"value": 5.2}, status=201)
    assert r["status"] == "warning" and r["alert_id"]
    notes = sup.get("/notifications").json()["items"]
    assert any(n["kind"] == "condition_alert" and n["severity"] == "warning" for n in notes)
    r2 = tech.ok("post", f"/pdm/points/{p['id']}/readings", {"value": 7.6}, status=201)
    assert r2["status"] == "critical" and r2["alert_id"] == r["alert_id"]  # escalated, not duplicated
    alerts = rel.get("/pdm/alerts", params={"open_only": True}).json()
    assert alerts["total"] == 1 and alerts["items"][0]["severity"] == "critical"
    sup.ok("post", f"/pdm/alerts/{r['alert_id']}/acknowledge", {"defect_description": "Inner race defect frequency visible"})
    wo = sup.ok("post", f"/pdm/alerts/{r['alert_id']}/work-order")
    w = sup.get(f"/work-orders/{wo['work_order_id']}").json()
    assert w["type"] == "predictive" and w["condition_alert_id"] == r["alert_id"]
    assert sup.post(f"/pdm/alerts/{r['alert_id']}/work-order").status_code == 409
    sup.ok("post", f"/pdm/alerts/{r['alert_id']}/resolve", {"resolution": "Bearing replaced under WO"})
    trend = rel.get(f"/pdm/points/{p['id']}/readings").json()
    assert [x["value"] for x in trend["readings"]] == [2.1, 5.2, 7.6]
    k = world.api("manager").get("/kpis/pdm_alerts").json()
    assert k["details"]["by_severity"]["critical"] == 1


def test_auto_wo_on_critical_and_limit_validation(world):
    rel, line, p = _point(world, auto_create_wo=True)
    r = world.api("tech").ok("post", f"/pdm/points/{p['id']}/readings", {"value": 9.0}, status=201)
    assert r["work_order_id"]
    assert (
        rel.post(
            "/pdm/points",
            {
                "code": "BAD",
                "name": "b",
                "asset_id": line["id"],
                "technique": "temperature",
                "unit": "C",
                "warning_high": 80,
                "alarm_high": 70,
            },
        ).status_code
        == 422
    )
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    assert world.api("tech").post(f"/pdm/points/{p['id']}/readings", {"value": 1, "measured_at": future}).status_code == 422


def test_unknown_status_without_limits(world):
    rel, line, p = _point(world, warning_high=None, alarm_high=None)
    assert world.api("tech").ok("post", f"/pdm/points/{p['id']}/readings", {"value": 3}, status=201)["status"] == "unknown"


def test_gateway_ingestion_token_and_dedup(world):
    rel, line, p = _point(world)
    admin = world.api("admin")
    tok = admin.ok("post", "/integration-tokens", {"name": "OPC UA gateway"}, status=201)
    gw = make_client()
    t = datetime.now(UTC).replace(microsecond=0).isoformat()
    body = {
        "readings": [{"tag": "ns=2;s=PM1.DR1.VIB", "value": 3.3, "measured_at": t}, {"tag": "unknown/tag", "value": 1, "measured_at": t}]
    }
    assert gw.post("/api/v1/integrations/readings", json=body).status_code == 401
    assert gw.post("/api/v1/integrations/readings", json=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    h = {"Authorization": f"Bearer {tok['token']}"}
    r = gw.post("/api/v1/integrations/readings", json=body, headers=h).json()
    assert r == {"accepted": 1, "duplicates": 0, "unknown_tags": ["unknown/tag"]}
    r = gw.post("/api/v1/integrations/readings", json=body, headers=h).json()
    assert r["accepted"] == 0 and r["duplicates"] == 1
    # gateway token is not a user session: cannot read the CMMS API
    api = Api(gw, world.plant.id)
    assert api.get("/assets", headers=h).status_code == 401
    admin.ok("delete", f"/integration-tokens/{tok['id']}")
    assert gw.post("/api/v1/integrations/readings", json=body, headers=h).status_code == 401


def test_point_code_is_automatic_and_list_searches_the_asset_tree(world):
    rel, line, p = _point(world)
    unit = mk_asset(rel, world, "PM1-CAL12", level="unit", parent=line["id"])
    a = rel.ok("post", "/pdm/points", {"asset_id": unit["id"], "technique": "temperature", "unit": "°C"}, status=201)
    b = rel.ok("post", "/pdm/points", {"asset_id": unit["id"], "technique": "vibration", "unit": "mm/s"}, status=201)
    assert (a["code"], b["code"], a["name"]) == ("PM1-CAL12-CM01", "PM1-CAL12-CM02", "PM1-CAL12 – temperature")
    codes = lambda **q: [x["code"] for x in rel.ok("get", "/pdm/points", params=q)]  # noqa: E731
    assert codes(under=line["id"]) == ["PM1-CAL12-CM01", "PM1-CAL12-CM02", "VIB-DR1"]
    assert codes(under=unit["id"]) == ["PM1-CAL12-CM01", "PM1-CAL12-CM02"]
    assert codes(q="dr1") == ["VIB-DR1"] and codes(q="cal12") == ["PM1-CAL12-CM01", "PM1-CAL12-CM02"]


def test_priority_puts_critical_points_first_and_only_planning_roles_set_it(world):
    rel, line, p = _point(world)
    other = rel.ok("post", "/pdm/points", {"asset_id": line["id"], "technique": "temperature", "unit": "°C"}, status=201)
    assert other["priority"] == 3
    assert world.api("tech").put(f"/pdm/points/{other['id']}/priority", json={"priority": 1}).status_code == 403
    for who in ("planner", "engineer", "reliability", "manager", "admin"):
        assert world.api(who).ok("put", f"/pdm/points/{other['id']}/priority", {"priority": 1})["priority"] == 1
    assert rel.put(f"/pdm/points/{other['id']}/priority", json={"priority": 4}).status_code == 422
    world.api("tech").ok("post", f"/pdm/points/{p['id']}/readings", {"value": 9.0}, status=201)  # critical reading
    third = rel.ok("post", "/pdm/points", {"asset_id": line["id"], "technique": "ultrasound", "unit": "dB"}, status=201)
    order = [x["code"] for x in world.api("tech").ok("get", "/pdm/points")]
    assert order[:3] == [other["code"], p["code"], third["code"]]  # set priority, then critical status, then the rest
