"""PM / PdM work-order generation per department: automatic (default) or held for manual release

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("pm_auto_wo", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("departments", sa.Column("pdm_auto_wo", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("departments", "pdm_auto_wo")
    op.drop_column("departments", "pm_auto_wo")
