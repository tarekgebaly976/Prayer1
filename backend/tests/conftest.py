"""Test harness: real PostgreSQL (cmms_test), schema built by Alembic migrations as the owner role,
application traffic as the least-privilege app role, HTTPS test client so Secure cookies behave as in production."""

import os
import uuid
from dataclasses import dataclass
from datetime import time

os.environ.setdefault("CMMS_DATABASE_URL", "postgresql+psycopg://cmms_app:dev_app_pw@localhost:5432/cmms_test")
os.environ.setdefault("CMMS_MIGRATION_DATABASE_URL", "postgresql+psycopg://cmms_owner:dev_owner_pw@localhost:5432/cmms_test")
os.environ.setdefault("CMMS_ENVIRONMENT", "test")
os.environ.setdefault("CMMS_LOG_LEVEL", "WARNING")
os.environ.setdefault("CMMS_RATE_LIMIT_PER_MINUTE", "100000")
os.environ.setdefault("CMMS_LOGIN_RATE_LIMIT_PER_MINUTE", "100000")
os.environ.setdefault("CMMS_STORAGE_LOCAL_PATH", "/tmp/claude-0/cmms-test-storage")

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.enums import DepartmentType, ShiftKind  # noqa: E402
from app.models.identity import Membership, Role, User  # noqa: E402
from app.models.shifts import ShiftDefinition  # noqa: E402
from app.models.tenancy import Department, Organization, Plant  # noqa: E402
from app.services.common import sync_rbac  # noqa: E402
from app.services.workflow import ensure_default_transitions  # noqa: E402

OWNER_URL = os.environ["CMMS_MIGRATION_DATABASE_URL"]
PASSWORD = "Test-Passw0rd!x"
_HASH = hash_password(PASSWORD)


def alembic_cfg() -> Config:
    here = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "alembic"))
    cfg.attributes["url"] = OWNER_URL
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _schema():
    eng = create_engine(OWNER_URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION cmms_owner;"
                       "GRANT USAGE ON SCHEMA public TO cmms_app;"))
    command.upgrade(alembic_cfg(), "head")
    with SessionLocal() as db, db.begin():
        sync_rbac(db)
    yield
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean():
    yield
    eng = create_engine(OWNER_URL)
    keep = {"roles", "permissions", "role_permissions", "alembic_version"}
    tables = [t.name for t in Base.metadata.sorted_tables if t.name not in keep]
    with eng.begin() as c:
        c.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
    eng.dispose()


class Api:
    """Authenticated client bound to one plant; attaches the CSRF header like the SPA does."""

    def __init__(self, client: TestClient, plant_id: uuid.UUID | None):
        self.c = client
        self.plant_id = plant_id
        self.csrf: str | None = None

    def _h(self, extra: dict | None = None) -> dict:
        h = {}
        if self.plant_id:
            h["X-Plant-Id"] = str(self.plant_id)
        if self.csrf:
            h["X-CSRF-Token"] = self.csrf
        h.update(extra or {})
        return h

    def get(self, url, **kw):
        return self.c.get("/api/v1" + url, headers=self._h(kw.pop("headers", None)), **kw)

    def post(self, url, json=None, **kw):
        return self.c.post("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def put(self, url, json=None, **kw):
        return self.c.put("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def delete(self, url, json=None, **kw):
        return self.c.delete("/api/v1" + url, headers=self._h(kw.pop("headers", None)), **kw)

    def ok(self, method: str, url: str, json=None, status: int | tuple = (200, 201, 204), **kw):
        r = getattr(self, method)(url, json=json, **kw) if method != "get" else self.get(url, **kw)
        expected = status if isinstance(status, tuple) else (status,)
        assert r.status_code in expected, f"{method.upper()} {url} -> {r.status_code}: {r.text}"
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else r


def make_client() -> TestClient:
    from app.main import app
    return TestClient(app, base_url="https://testserver")


def login(email: str, plant_id: uuid.UUID | None, password: str = PASSWORD) -> Api:
    api = Api(make_client(), plant_id)
    r = api.post("/auth/login", {"email": email, "password": password})
    assert r.status_code == 200, r.text
    api.csrf = r.json()["csrf_token"]
    return api


@dataclass
class World:
    org: Organization
    plant: Plant
    plant_b: Plant
    depts: dict
    depts_b: dict
    users: dict
    shifts: dict

    def api(self, key: str, plant: Plant | None = None) -> Api:
        return login(self.users[key].email, (plant or self.plant).id)


ROLE_USERS = {
    "admin": "system_admin", "manager": "maintenance_manager", "planner": "planner", "mech_sup": "mech_supervisor",
    "elec_sup": "elec_supervisor", "reliability": "reliability_engineer", "engineer": "engineer", "tech": "technician",
    "tech2": "technician", "store": "storekeeper", "production": "production_user", "viewer": "management_viewer",
}


@pytest.fixture
def world() -> World:
    with SessionLocal() as db, db.begin():
        org = Organization(code="T", name="Test Org")
        db.add(org)
        db.flush()
        plant = Plant(organization_id=org.id, code="P1", name="Plant One", timezone="Asia/Riyadh", currency="SAR",
                      settings={"default_labor_rate": 100, "overtime_multiplier": 1.5})
        plant_b = Plant(organization_id=org.id, code="P2", name="Plant Two", timezone="Asia/Riyadh", currency="SAR", settings={})
        db.add_all([plant, plant_b])
        db.flush()
        depts, depts_b = {}, {}
        for p, store in ((plant, depts), (plant_b, depts_b)):
            ensure_default_transitions(db, p.id)
            for t in DepartmentType:
                d = Department(plant_id=p.id, code=t.value, name=t.value, type=t)
                db.add(d)
                store[t.value] = d
        db.flush()
        roles = {r.code: r for r in db.query(Role).all()}
        users = {}
        for key, role in ROLE_USERS.items():
            u = User(organization_id=org.id, email=f"{key}@example.com", full_name=key.title(), password_hash=_HASH,
                     is_system_admin=role == "system_admin", hourly_rate=80 if role == "technician" else None,
                     trade="mechanical" if role == "technician" else None)
            db.add(u)
            db.flush()
            db.add(Membership(user_id=u.id, plant_id=plant.id, role_id=roles[role].id))
            users[key] = u
        # A plant-B-only planner and a department-restricted (SP) supervisor in plant A.
        ub = User(organization_id=org.id, email="planner_b@example.com", full_name="Planner B", password_hash=_HASH)
        usp = User(organization_id=org.id, email="sp_sup@example.com", full_name="SP Supervisor", password_hash=_HASH)
        db.add_all([ub, usp])
        db.flush()
        db.add(Membership(user_id=ub.id, plant_id=plant_b.id, role_id=roles["planner"].id))
        db.add(Membership(user_id=usp.id, plant_id=plant.id, role_id=roles["mech_supervisor"].id, department_id=depts["SP"].id))
        users["planner_b"], users["sp_sup"] = ub, usp
        shifts = {}
        for code, kind, s, e in (("D", ShiftKind.DAY, time(6), time(14)), ("N", ShiftKind.NIGHT, time(22), time(6))):
            sd = ShiftDefinition(plant_id=plant.id, code=code, name=code, kind=kind, start_time=s, end_time=e, paid_hours=8)
            db.add(sd)
            shifts[code] = sd
        db.flush()
        for o in [org, plant, plant_b, *depts.values(), *depts_b.values(), *users.values(), *shifts.values()]:
            db.expunge(o)
    return World(org, plant, plant_b, depts, depts_b, users, shifts)


def mk_asset(api: Api, world: World, code: str, level: str = "production_line", parent: str | None = None,
             dept: str = "PM", crit: str = "A") -> dict:
    return api.ok("post", "/assets", {"code": code, "name": code, "department_id": str(world.depts[dept].id),
                                      "parent_id": parent, "level": level, "criticality": crit}, status=201)
