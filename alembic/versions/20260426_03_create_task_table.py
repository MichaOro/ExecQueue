"""Create task table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_03"
down_revision = "20260426_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_number", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("title", sa.String(length=255), server_default="", nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="backlog", nullable=False),
        sa.Column("execution_order", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("created_by_type", sa.String(length=32), nullable=False),
        sa.Column("created_by_ref", sa.String(length=255), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
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
            "created_by_type IN ('user', 'agent')",
            name=op.f("ck_task_task_created_by_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_task_project_id_project"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task")),
        sa.UniqueConstraint("task_number", name=op.f("uq_task_task_number")),
    )
    op.create_index(op.f("ix_task_status"), "task", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_task_status"), table_name="task")
    op.drop_table("task")
