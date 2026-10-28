"""measurement point priority

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("measurement_points", sa.Column("priority", sa.SmallInteger(), server_default="3", nullable=False))
    op.create_check_constraint(op.f("ck_measurement_points_priority_range"), "measurement_points", "priority BETWEEN 1 AND 3")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_measurement_points_priority_range"), "measurement_points", type_="check")
    op.drop_column("measurement_points", "priority")
