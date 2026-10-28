"""failure mode catalogue: equipment type on assets and failure codes, symptom codes on requests and work orders

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'symptom', 'problem', 'cause', 'remedy'"


def upgrade() -> None:
    op.add_column("assets", sa.Column("equipment_type", sa.String(length=60), nullable=True))
    op.add_column("failure_codes", sa.Column("equipment_type", sa.String(length=60), nullable=True))
    op.add_column("failure_codes", sa.Column("category", sa.String(length=30), nullable=True))
    op.drop_constraint(op.f("ck_failure_codes_failurecodekind"), "failure_codes", type_="check")
    op.create_check_constraint(op.f("ck_failure_codes_failurecodekind"), "failure_codes", f"kind IN ({KINDS})")
    for table in ("work_requests", "work_orders"):
        op.add_column(table, sa.Column("symptom_code_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_symptom_code_id_failure_codes"), table, "failure_codes", ["symptom_code_id"], ["id"], ondelete="RESTRICT"
        )
    op.add_column("work_requests", sa.Column("problem_code_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_work_requests_problem_code_id_failure_codes"),
        "work_requests",
        "failure_codes",
        ["problem_code_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_work_requests_problem_code_id_failure_codes"), "work_requests", type_="foreignkey")
    op.drop_column("work_requests", "problem_code_id")
    for table in ("work_orders", "work_requests"):
        op.drop_constraint(op.f(f"fk_{table}_symptom_code_id_failure_codes"), table, type_="foreignkey")
        op.drop_column(table, "symptom_code_id")
    op.execute("DELETE FROM failure_codes WHERE kind = 'symptom'")
    op.drop_constraint(op.f("ck_failure_codes_failurecodekind"), "failure_codes", type_="check")
    op.create_check_constraint(op.f("ck_failure_codes_failurecodekind"), "failure_codes", "kind IN ('problem', 'cause', 'remedy')")
    op.drop_column("failure_codes", "category")
    op.drop_column("failure_codes", "equipment_type")
    op.drop_column("assets", "equipment_type")
