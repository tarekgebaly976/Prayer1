"""Lubrication work orders Auto / Manual per department; what a critical PdM alert creates (WO, WR or nothing)

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("lube_auto_wo", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("departments", sa.Column("pdm_alert_action", sa.String(8), nullable=False, server_default="wo"))
    op.create_check_constraint(op.f("ck_departments_pdm_alert_action"), "departments", "pdm_alert_action IN ('wo', 'wr', 'none')")
    # Departments already set to Manual PdM keep holding alert work orders.
    op.execute("UPDATE departments SET pdm_alert_action = 'none' WHERE pdm_auto_wo = false")
    op.add_column("condition_alerts", sa.Column("work_request_id", sa.UUID(), nullable=True))


def downgrade() -> None:
    op.drop_column("condition_alerts", "work_request_id")
    op.drop_constraint(op.f("ck_departments_pdm_alert_action"), "departments", type_="check")
    op.drop_column("departments", "pdm_alert_action")
    op.drop_column("departments", "lube_auto_wo")
