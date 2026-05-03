"""REQ-021 - Create worktree_metadata table.

Creates table for centralized worktree management with metadata persistence
as specified in REQ-021 Section 3.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260502_02_req021_wtmeta"
down_revision = "20260502_01_req021_adopttrk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worktree_metadata",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workflow_id",
            sa.Uuid(),
            sa.ForeignKey("workflow.id"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("task.id"),
            nullable=False,
        ),
        sa.Column(
            "path",
            sa.String(512),
            nullable=False,
            comment="Absolute path to the worktree directory",
        ),
        sa.Column(
            "branch",
            sa.String(255),
            nullable=False,
            comment="Git branch name for this worktree",
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="active",
            comment="Worktree lifecycle state: active, cleaned, error",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Timestamp when worktree was created",
        ),
        sa.Column(
            "cleaned_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when worktree was cleaned up",
        ),
        sa.Column(
            "error_message",
            sa.Text,
            nullable=True,
            comment="Error message if worktree entered error state",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_worktree_metadata"),
    )
    
    # Add check constraint for valid status values
    op.create_check_constraint(
        "ck_worktree_metadata_status_allowed",
        "worktree_metadata",
        "status IN ('active', 'cleaned', 'error')",
    )
    
    # Create indexes for common queries
    op.create_index(
        "ix_worktree_metadata_workflow_id",
        "worktree_metadata",
        ["workflow_id"],
        unique=False,
    )
    op.create_index(
        "ix_worktree_metadata_task_id",
        "worktree_metadata",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_worktree_metadata_status",
        "worktree_metadata",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_worktree_metadata_path",
        "worktree_metadata",
        ["path"],
        unique=True,
    )
    # Index for orphaned cleanup queries (active worktrees older than TTL)
    op.create_index(
        "ix_worktree_metadata_status_created_at",
        "worktree_metadata",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_worktree_metadata_status_created_at", table_name="worktree_metadata")
    op.drop_index("ix_worktree_metadata_path", table_name="worktree_metadata")
    op.drop_index("ix_worktree_metadata_status", table_name="worktree_metadata")
    op.drop_index("ix_worktree_metadata_task_id", table_name="worktree_metadata")
    op.drop_index("ix_worktree_metadata_workflow_id", table_name="worktree_metadata")
    op.drop_constraint(
        "ck_worktree_metadata_status_allowed",
        "worktree_metadata",
        type_="check",
    )
    op.drop_table("worktree_metadata")
