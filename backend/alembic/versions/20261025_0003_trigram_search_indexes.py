"""trigram indexes for substring search (ILIKE '%term%') on large tables

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = [
    ("ix_assets_code_trgm", "assets", "code"),
    ("ix_assets_name_trgm", "assets", "name"),
    ("ix_assets_serial_trgm", "assets", "serial_number"),
    ("ix_wo_number_trgm", "work_orders", "number"),
    ("ix_wo_title_trgm", "work_orders", "title"),
    ("ix_parts_code_trgm", "parts", "code"),
    ("ix_parts_desc_trgm", "parts", "description"),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")  # trusted extension: database owner may create it
    for name, table, col in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({col} gin_trgm_ops)")


def downgrade() -> None:
    for name, _, _ in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
