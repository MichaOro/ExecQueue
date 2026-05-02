"""REQ-021 - Add adoption tracking fields to task_executions.

Adds adoption_status and adoption_error columns to track commit adoption
lifecycle as specified in REQ-021 Section 5.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260502_01_req021_adoption_tracking"
down_revision = "20260430_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add adoption_status column for tracking adoption lifecycle
    op.add_column(
        "task_executions",
        sa.Column(
            "adoption_status",
            sa.String(32),
            nullable=True,
            comment="Adoption state: pending, in_progress, success, failed, review"
        ),
    )
    
    # Add adoption_error column for error details
    op.add_column(
        "task_executions",
        sa.Column(
            "adoption_error",
            sa.Text,
            nullable=True,
            comment="Error message if adoption failed"
        ),
    )
    
    # Add check constraint for valid adoption_status values
    op.create_check_constraint(
        "ck_task_execution_adoption_status_allowed",
        "task_executions",
        "adoption_status IN ('pending', 'in_progress', 'success', 'failed', 'review')",
    )
    
    # Add index for querying by adoption status
    op.create_index(
        "ix_task_executions_adoption_status",
        "task_executions",
        ["adoption_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_task_executions_adoption_status", table_name="task_executions")
    op.drop_constraint(
        "ck_task_execution_adoption_status_allowed",
        "task_executions",
        type_="check",
    )
    op.drop_column("task_executions", "adoption_error")
    op.drop_column("task_executions", "adoption_status")
