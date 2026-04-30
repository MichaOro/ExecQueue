"""add_unique_constraint_active_executions_per_task

Revision ID: 0dd3b00c3330
Revises: 20260428_05
Create Date: 2026-04-29 12:57:00.000000

REQ-012: Add partial unique index to ensure at most one active execution per task
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '0dd3b00c3330'
down_revision: Union[str, None] = '20260428_05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial unique index for active executions per task.
    
    This constraint ensures that for each task, there is at most one execution
    with an active status (not in 'done', 'failed', 'review').
    
    Active statuses: prepared, queued, dispatching, in_progress, 
                     result_inspection, adopting_commit
    """
    # Create partial unique index for active executions
    # Note: Using raw SQL for PostgreSQL-specific partial index syntax
    op.execute(
        text(
            "CREATE UNIQUE INDEX ix_task_executions_unique_active "
            "ON task_executions (task_id) "
            "WHERE status NOT IN ('done', 'failed', 'review')"
        )
    )


def downgrade() -> None:
    """Drop the partial unique index for active executions per task."""
    op.execute(text("DROP INDEX ix_task_executions_unique_active"))
