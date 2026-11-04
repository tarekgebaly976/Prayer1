"""password reset links ("forgot password"): single use, short-lived, token stored only as a SHA-256 digest

Revision ID: 0016
Revises: 0015
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_password_resets_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_resets")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_resets_token_hash")),
    )
    op.create_index(op.f("ix_password_resets_created_at"), "password_resets", ["created_at"], unique=False)
    op.create_index(op.f("ix_password_resets_user_id"), "password_resets", ["user_id"], unique=False)
    app_role = os.environ.get("CMMS_APP_DB_ROLE", "cmms_app")  # same least-privilege grant as 0002, for the new table
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{app_role}') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON password_resets TO {app_role}; END IF; END $$;"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_password_resets_user_id"), table_name="password_resets")
    op.drop_index(op.f("ix_password_resets_created_at"), table_name="password_resets")
    op.drop_table("password_resets")
