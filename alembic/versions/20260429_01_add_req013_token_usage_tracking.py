"""add_req013_token_usage_tracking

Revision ID: 20260429_01
Revises: 0dd3b00c3330
Create Date: 2026-04-29 00:00:00.000000

Adds token usage tracking to task_executions table for REQ-013.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import BigInteger

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260429_01"
down_revision: Union[str, None] = "0dd3b00c3330"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add total_tokens column and composite index for token tracking."""
    # Add total_tokens column (nullable, BigInteger for robustness)
    op.add_column(
        "task_executions",
        sa.Column("total_tokens", BigInteger, nullable=True),
    )

    # Create composite index for time-based token aggregations
    op.create_index(
        "ix_task_executions_created_at_total_tokens",
        "task_executions",
        ["created_at", "total_tokens"],
    )


def downgrade() -> None:
    """Remove token tracking column and index."""
    # Drop index first
    op.drop_index("ix_task_executions_created_at_total_tokens", table_name="task_executions")

    # Drop column
    op.drop_column("task_executions", "total_tokens")
