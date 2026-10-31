"""daily summary e-mail: plant switch, send days and time, per-member recipient flag (set by administrators)

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("plants", sa.Column("daily_summary_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("plants", sa.Column("daily_summary_time", sa.Time(), nullable=False, server_default="07:00"))
    op.add_column(
        "plants",
        sa.Column("daily_summary_days", postgresql.JSONB(), nullable=False, server_default=sa.text("'[1, 2, 3, 4, 5, 6, 7]'::jsonb")),
    )
    op.add_column("memberships", sa.Column("daily_summary", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("memberships", "daily_summary")
    op.drop_column("plants", "daily_summary_days")
    op.drop_column("plants", "daily_summary_time")
    op.drop_column("plants", "daily_summary_enabled")
