"""Runs last (file name): full downgrade to base and re-upgrade, then checks models match the migrated schema."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.db import SessionLocal
from app.models.base import Base
from app.services.common import sync_rbac
from tests.conftest import OWNER_URL, alembic_cfg


def test_downgrade_upgrade_and_no_drift():
    cfg = alembic_cfg()
    command.downgrade(cfg, "base")
    eng = create_engine(OWNER_URL)
    assert set(inspect(eng).get_table_names()) <= {"alembic_version"}
    command.upgrade(cfg, "head")
    with eng.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata)
    assert diff == [], diff
    with SessionLocal() as db, db.begin():
        sync_rbac(db)
    eng.dispose()
