"""REQ-015 WP01 - Create workflow table.

Migration for workflow data model to support orchestrator crash recovery.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_01"
down_revision = "20260429_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow",
        sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("epic_id", sa.Uuid(), nullable=True),
        sa.Column("requirement_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="running",
        ),
        sa.Column("runner_uuid", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ck_workflow_status_allowed",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow"),
    )
    op.create_index(op.f("ix_workflow_epic_id"), "workflow", ["epic_id"], unique=False)
    op.create_index(op.f("ix_workflow_requirement_id"), "workflow", ["requirement_id"], unique=False)
    op.create_index(op.f("ix_workflow_status"), "workflow", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_requirement_id"), table_name="workflow")
    op.drop_index(op.f("ix_workflow_epic_id"), table_name="workflow")
    op.drop_index(op.f("ix_workflow_status"), table_name="workflow")
    op.drop_table("workflow")
