"""add_req012_runner_fields

Revision ID: 20260428_05
Revises: e5eb4a65b3b5
Create Date: 2026-04-28 21:05:00.000000

NOTE: This migration is now empty. The task_executions and task_execution_events
tables with all REQ-012 runner fields were created in migration e5eb4a65b3b5.
This migration is kept for historical reference only.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '20260428_05'
down_revision: Union[str, None] = 'e5eb4a65b3b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Empty - tables created in e5eb4a65b3b5."""
    pass


def downgrade() -> None:
    """Empty - tables created in e5eb4a65b3b5."""
    pass
