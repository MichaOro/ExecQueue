"""REQ-015 WP01 - Add workflow_id column to task_executions.

Adds foreign key reference from task_executions to workflow for crash recovery.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_02"
down_revision = "20260430_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_executions",
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_executions_workflow_id_workflow",
        "task_executions",
        "workflow",
        ["workflow_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_task_executions_workflow_id"),
        "task_executions",
        ["workflow_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_executions_workflow_id"), table_name="task_executions")
    op.drop_constraint(
        "fk_task_executions_workflow_id_workflow",
        "task_executions",
        type_="foreignkey",
    )
    op.drop_column("task_executions", "workflow_id")
