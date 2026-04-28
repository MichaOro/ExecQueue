"""add_req011_execution_preparation_fields

Revision ID: 99d5a553d696
Revises: 20260426_04
Create Date: 2026-04-28

REQ-011: Add execution preparation metadata fields to task table
"""

from alembic import op
import sqlalchemy as sa


revision = '99d5a553d696'
down_revision = '20260426_04'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add execution preparation metadata fields first
    op.add_column("task", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task", sa.Column("locked_by", sa.String(255), nullable=True))
    op.add_column("task", sa.Column("preparation_attempt_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("task", sa.Column("last_preparation_error", sa.Text, nullable=True))
    op.add_column("task", sa.Column("branch_name", sa.String(255), nullable=True))
    op.add_column("task", sa.Column("worktree_path", sa.String(1024), nullable=True))
    op.add_column("task", sa.Column("commit_sha_before", sa.String(64), nullable=True))
    op.add_column("task", sa.Column("prepared_context_version", sa.String(32), nullable=True))
    op.add_column("task", sa.Column("batch_id", sa.String(255), nullable=True))
    
    # Add indexes for REQ-011 query patterns
    # Index for candidate discovery: status, priority, created_at
    op.create_index(
        "ix_task_status_created_at",
        "task",
        ["status", "created_at"]
    )
    # Index for stale recovery: status, queued_at, preparation_attempt_count
    op.create_index(
        "ix_task_queued_recovery",
        "task",
        ["status", "queued_at", "preparation_attempt_count"]
    )
    
    # Add CHECK constraint for new status values
    # Note: For SQLite, we skip the constraint as it doesn't support ALTER of constraints
    # The constraint is enforced at the application level via the TaskStatus enum
    try:
        # Try to drop existing constraint first (PostgreSQL)
        op.drop_constraint("ck_task_status_allowed", "task", type_="check")
    except Exception:
        # Constraint might not exist, continue
        pass
    
    # Create new constraint with expanded values
    try:
        op.create_check_constraint(
            "ck_task_status_allowed",
            "task",
            "status IN ('backlog', 'queued', 'prepared', 'failed')"
        )
    except Exception:
        # SQLite doesn't support adding check constraints via ALTER
        # The constraint is enforced at the application level
        pass


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_task_queued_recovery", "task")
    op.drop_index("ix_task_status_created_at", "task")
    
    # Drop columns
    op.drop_column("task", "batch_id")
    op.drop_column("task", "prepared_context_version")
    op.drop_column("task", "commit_sha_before")
    op.drop_column("task", "worktree_path")
    op.drop_column("task", "branch_name")
    op.drop_column("task", "last_preparation_error")
    op.drop_column("task", "preparation_attempt_count")
    op.drop_column("task", "locked_by")
    op.drop_column("task", "queued_at")
    
    # Restore original CHECK constraint (PostgreSQL only)
    try:
        op.drop_constraint("ck_task_status_allowed", "task", type_="check")
        op.create_check_constraint(
            "ck_task_status_allowed",
            "task",
            "status IN ('backlog')"
        )
    except Exception:
        # SQLite doesn't support this, skip
        pass
