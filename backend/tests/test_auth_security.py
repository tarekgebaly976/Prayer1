from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models.identity import UserSession
from tests.conftest import PASSWORD, Api, login, make_client


def test_login_sets_httponly_secure_cookie_and_me(world):
    api = Api(make_client(), None)
    r = api.post("/auth/login", {"email": "tech@example.com", "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "cmms_session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "token" not in r.json()  # session token never exposed to JS
    api.csrf = r.json()["csrf_token"]
    me = api.get("/auth/me").json()
    assert me["email"] == "tech@example.com"
    assert me["plants"][0]["role"] == "technician"
    assert "wo.close" not in me["plants"][0]["permissions"]


def test_wrong_password_generic_error_and_lockout(world):
    api = Api(make_client(), None)
    for _ in range(5):
        r = api.post("/auth/login", {"email": "tech@example.com", "password": "wrong-password"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password"
    r = api.post("/auth/login", {"email": "tech@example.com", "password": PASSWORD})
    assert r.status_code == 429  # locked even with the right password
    r = api.post("/auth/login", {"email": "nobody@example.com", "password": "x"})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid email or password"  # no user enumeration


def test_csrf_required_for_mutations(world):
    api = world.api("planner")
    api.csrf = None
    r = api.post("/work-requests", {"asset_id": "00000000-0000-0000-0000-000000000000", "title": "x"})
    assert r.status_code == 403 and "CSRF" in r.text
    api.csrf = "forged"
    assert api.post("/notifications/read-all").status_code == 403


def test_unauthenticated_rejected(world):
    api = Api(make_client(), world.plant.id)
    assert api.get("/assets").status_code == 401
    assert api.get("/work-orders").status_code == 401


def test_logout_revokes_server_session(world):
    api = world.api("tech")
    token = api.c.cookies.get("cmms_session")
    assert api.post("/auth/logout").status_code == 204
    other = Api(make_client(), world.plant.id)
    other.c.cookies.set("cmms_session", token, domain="testserver")
    assert other.get("/auth/me").status_code == 401


def test_disabling_membership_revokes_sessions(world):
    tech = world.api("tech")
    admin = world.api("admin")
    admin.ok("patch", f"/users/{world.users['tech'].id}", {"is_active": False})
    assert tech.get("/auth/me").status_code == 401
    with SessionLocal() as db:
        s = db.execute(select(UserSession).where(UserSession.user_id == world.users["tech"].id)).scalars().all()
        assert all(x.revoked_at is not None for x in s)


def test_password_policy_on_user_create(world):
    admin = world.api("admin")
    r = admin.post("/users", {"email": "new@example.com", "full_name": "New", "password": "short", "role": "technician"})
    assert r.status_code == 422
    r = admin.post("/users", {"email": "new@example.com", "full_name": "New", "password": "Longer-Passw0rd", "role": "technician"})
    assert r.status_code == 201
    login("new@example.com", world.plant.id, "Longer-Passw0rd")


def test_manager_cannot_grant_system_admin(world):
    mgr = world.api("manager")
    r = mgr.post("/users", {"email": "x@example.com", "full_name": "X", "password": "Longer-Passw0rd", "role": "system_admin"})
    assert r.status_code == 403


def test_security_headers(world):
    api = world.api("tech")
    r = api.get("/auth/me")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" in r.headers
    assert r.headers["cache-control"] == "no-store"


def test_unknown_fields_rejected(world):
    api = world.api("planner")
    r = api.post("/work-requests", {"asset_id": "00000000-0000-0000-0000-000000000000", "title": "abc", "status": "accepted"})
    assert r.status_code == 422


def test_audit_log_append_only(world):
    world.api("tech")  # login writes an audit row
    with SessionLocal() as db:
        try:
            db.execute(text("UPDATE audit_logs SET action='tampered'"))
            db.commit()
            raise AssertionError("update should have failed")
        except Exception as e:  # noqa: BLE001
            db.rollback()
            assert "permission denied" in str(e) or "append-only" in str(e)


def test_health_endpoints(world):
    c = make_client()
    assert c.get("/api/v1/health/live").json() == {"status": "ok"}
    r = c.get("/api/v1/health/ready").json()
    assert r["checks"]["database"] == "ok" and r["checks"]["migration"] == "0002"
