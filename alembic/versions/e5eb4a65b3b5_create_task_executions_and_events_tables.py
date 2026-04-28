"""create_task_executions_and_events_tables

Revision ID: e5eb4a65b3b5
Revises: 1773edb33736
Create Date: 2026-04-28 21:35:00.000000

REQ-012: Create task_executions and task_execution_events tables for runner lifecycle
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'e5eb4a65b3b5'
down_revision: Union[str, None] = '1773edb33736'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create task_executions and task_execution_events tables."""
    
    # --- task_executions table ---
    op.create_table(
        "task_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("task.id"), nullable=False),
        sa.Column("runner_id", sa.String(255), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("prepared_context_version", sa.String(32), nullable=True),
        sa.Column("opencode_session_id", sa.String(128), nullable=True),
        sa.Column("opencode_message_id", sa.String(128), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="prepared",
        ),
        sa.CheckConstraint(
            "status IN ('prepared', 'queued', 'dispatching', 'in_progress', "
            "'result_inspection', 'adopting_commit', 'review', 'done', 'failed')",
            name="ck_task_execution_status_allowed",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt",
            sa.Integer,
            nullable=False,
            server_default=text("1"),
        ),
        sa.Column(
            "max_attempts",
            sa.Integer,
            nullable=False,
            server_default=text("3"),
        ),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("result_summary", sa.JSON, nullable=True),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("worktree_path", sa.String(512), nullable=True),
        sa.Column("commit_sha_before", sa.String(40), nullable=True),
        sa.Column("commit_sha_after", sa.String(40), nullable=True),
        sa.Column("new_commit_shas", sa.JSON, nullable=True),
        sa.Column("changed_files", sa.JSON, nullable=True),
        sa.Column("diff_stat", sa.Text, nullable=True),
        sa.Column("has_uncommitted_changes", sa.Boolean, nullable=True),
        sa.Column("inspection_status", sa.String(32), nullable=True),
        sa.Column("adopted_commit_sha", sa.String(40), nullable=True),
        # Felder für Retry und Stale-Erkennung (Paket 09)
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase", sa.String(32), nullable=True),
        sa.Column(
            "max_execution_duration_seconds",
            sa.Integer,
            nullable=True,
            server_default=text("3600"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    
    # Indexe für task_executions
    op.create_index("ix_task_executions_task_id", "task_executions", ["task_id"])
    op.create_index("ix_task_executions_status", "task_executions", ["status"])
    op.create_index("ix_task_executions_runner_id", "task_executions", ["runner_id"])
    op.create_index("ix_task_executions_correlation_id", "task_executions", ["correlation_id"])
    op.create_index("ix_task_executions_opencode_session_id", "task_executions", ["opencode_session_id"])
    op.create_index("ix_task_executions_updated_at", "task_executions", ["updated_at"])
    # Indexe für Stale-Erkennung (Paket 09)
    op.create_index("ix_task_executions_heartbeat_at_status", "task_executions", ["heartbeat_at", "status"])
    op.create_index("ix_task_executions_updated_at_status", "task_executions", ["updated_at", "status"])
    
    # --- task_execution_events table ---
    op.create_table(
        "task_execution_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_execution_id",
            sa.Uuid(),
            sa.ForeignKey("task_executions.id"),
            nullable=False,
        ),
        sa.Column(
            "sequence",
            sa.Integer,
            nullable=False,
            server_default=text("1"),
        ),
        sa.Column("external_event_id", sa.String(128), nullable=True),
        sa.Column(
            "direction",
            sa.String(32),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name="ck_task_execution_events_direction_allowed",
        ),
        sa.Column(
            "event_type",
            sa.String(64),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('started', 'progress', 'completed', 'error', 'status_update', "
            "'execution.claimed', 'execution.dispatched', 'execution.started', "
            "'execution.completed', 'execution.failed', 'session.created', 'session.closed', "
            "'message.sent', 'message.received', 'stream.connected', 'stream.disconnected', "
            "'stream.heartbeat', 'result.inspected', 'commit.adoption_started', "
            "'commit.adoption_success', 'commit.adoption_conflict', 'retry.scheduled', "
            "'retry.exhausted')",
            name="ck_task_execution_events_event_type_allowed",
        ),
        sa.Column("payload", sa.JSON, nullable=False, server_default=text("'{}'")),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    
    # Unique Indexe für task_execution_events (Event-Deduplizierung)
    op.create_index(
        "ix_task_execution_events_unique_sequence",
        "task_execution_events",
        ["task_execution_id", "sequence"],
        unique=True,
    )
    # Partial unique index für external_event_id (PostgreSQL-specific)
    op.execute(
        text(
            "CREATE UNIQUE INDEX ix_task_execution_events_unique_external_id "
            "ON task_execution_events (task_execution_id, external_event_id) "
            "WHERE external_event_id IS NOT NULL"
        )
    )
    
    # Weitere Indexe für task_execution_events
    op.create_index("ix_task_execution_events_task_execution_id", "task_execution_events", ["task_execution_id"])
    op.create_index("ix_task_execution_events_direction", "task_execution_events", ["direction"])
    op.create_index("ix_task_execution_events_event_type", "task_execution_events", ["event_type"])
    op.create_index("ix_task_execution_events_created_at", "task_execution_events", ["created_at"])
    op.create_index("ix_task_execution_events_sequence", "task_execution_events", ["task_execution_id", "sequence"])


def downgrade() -> None:
    """Drop task_execution_events and task_executions tables."""
    op.drop_table("task_execution_events")
    op.drop_table("task_executions")
