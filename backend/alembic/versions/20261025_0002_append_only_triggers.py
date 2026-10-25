"""append-only protection for audit-critical tables

Revision ID: 0002
Revises: 0001
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = os.environ.get("CMMS_APP_DB_ROLE", "cmms_app")
APPEND_ONLY = ["audit_logs", "inventory_transactions", "wo_status_history", "condition_readings"]


def upgrade() -> None:
    # Least privilege: the runtime role gets DML only (no DDL, no ownership).
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{APP_ROLE}') THEN "
        f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}; "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}; "
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}; "
        f"REVOKE ALL ON alembic_version FROM {APP_ROLE}; GRANT SELECT ON alembic_version TO {APP_ROLE}; END IF; END $$;"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cmms_forbid_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'table % is append-only (% not permitted)', TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for t in APPEND_ONLY:
        op.execute(f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION cmms_forbid_mutation();")
        # Defence in depth: the runtime role cannot UPDATE/DELETE these tables at all.
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{APP_ROLE}') THEN "
            f"REVOKE UPDATE, DELETE, TRUNCATE ON {t} FROM {APP_ROLE}; END IF; END $$;"  # noqa: S608 - static table names
        )


def downgrade() -> None:
    for t in APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS {t}_append_only ON {t};")
    op.execute("DROP FUNCTION IF EXISTS cmms_forbid_mutation();")
