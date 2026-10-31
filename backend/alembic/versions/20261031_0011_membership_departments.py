"""several departments per member

Revision ID: 0011
Revises: 0010
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "membership_departments",
        sa.Column("membership_id", sa.UUID(), nullable=False),
        sa.Column("department_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name=op.f("fk_membership_departments_department_id_departments"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["memberships.id"], name=op.f("fk_membership_departments_membership_id_memberships"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("membership_id", "department_id", name=op.f("pk_membership_departments")),
    )
    app_role = os.environ.get("CMMS_APP_DB_ROLE", "cmms_app")
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{app_role}') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON membership_departments TO {app_role}; END IF; END $$;"
    )


def downgrade() -> None:
    op.drop_table("membership_departments")
