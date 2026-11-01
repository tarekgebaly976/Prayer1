"""Roles the administrator can edit: `customized` keeps an edited built-in role from being reset at start-up,
`organization_id` scopes custom roles to the organization that created them (built-in roles have none).

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("roles", sa.Column("customized", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("roles", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_roles_organization_id_organizations"), "roles", "organizations", ["organization_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_roles_organization_id_organizations"), "roles", type_="foreignkey")
    op.drop_column("roles", "organization_id")
    op.drop_column("roles", "customized")
