"""general department types (any industry)

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "ck_departments_departmenttype"
OLD = "'PM', 'SP', 'FH', 'WWTP', 'EAI', 'UTIL'"
NEW = "'PRODUCTION', 'MAINTENANCE', 'UTILITIES', 'FACILITIES', 'QUALITY', 'WAREHOUSE', 'OTHER', " + OLD


def upgrade() -> None:
    op.drop_constraint(op.f(NAME), "departments", type_="check")
    op.create_check_constraint(op.f(NAME), "departments", f"type IN ({NEW})")


def downgrade() -> None:
    op.execute("UPDATE departments SET type = 'UTIL' WHERE type NOT IN (" + OLD + ")")
    op.drop_constraint(op.f(NAME), "departments", type_="check")
    op.create_check_constraint(op.f(NAME), "departments", f"type IN ({OLD})")
