"""Synchronize runtime ORM models with Alembic schema history.

Adds missing tables and constraints that are already referenced by the code:
- execution_plan
- task_dependencies
- orchestrator_lock
- task_executions.input_hash and related indexes
- updated task/task_execution_events check constraints
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "20260503_01_schema_sync"
down_revision = "20260502_02_req021_wtmeta"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("execution_plan"):
        op.create_table(
            "execution_plan",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("requirement_id", sa.Uuid(), nullable=False),
            sa.Column("created_by_task_id", sa.Uuid(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("content", sa.JSON(), server_default=text("'{}'"), nullable=False),
            sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
            sa.CheckConstraint(
                "status IN ('pending', 'running', 'succeeded', 'failed')",
                name="ck_execution_plan_status_allowed",
            ),
            sa.ForeignKeyConstraint(
                ["created_by_task_id"],
                ["task.id"],
                name=op.f("fk_execution_plan_created_by_task_id_task"),
            ),
            sa.ForeignKeyConstraint(
                ["requirement_id"],
                ["requirement.id"],
                name=op.f("fk_execution_plan_requirement_id_requirement"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_plan")),
        )
    if _table_exists("execution_plan") and not _index_exists("execution_plan", "ix_execution_plan_requirement_id"):
        op.create_index(
            "ix_execution_plan_requirement_id",
            "execution_plan",
            ["requirement_id"],
            unique=False,
        )
    if _table_exists("execution_plan") and not _index_exists("execution_plan", "ix_execution_plan_created_by_task_id"):
        op.create_index(
            "ix_execution_plan_created_by_task_id",
            "execution_plan",
            ["created_by_task_id"],
            unique=False,
        )
    if _table_exists("execution_plan") and not _index_exists("execution_plan", "ix_execution_plan_status"):
        op.create_index(
            "ix_execution_plan_status",
            "execution_plan",
            ["status"],
            unique=False,
        )

    if not _table_exists("task_dependencies"):
        op.create_table(
            "task_dependencies",
            sa.Column("task_id", sa.Uuid(), nullable=False),
            sa.Column("depends_on_task_id", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["depends_on_task_id"],
                ["task.id"],
                name=op.f("fk_task_dependencies_depends_on_task_id_task"),
            ),
            sa.ForeignKeyConstraint(
                ["task_id"],
                ["task.id"],
                name=op.f("fk_task_dependencies_task_id_task"),
            ),
            sa.PrimaryKeyConstraint("task_id", "depends_on_task_id", name=op.f("pk_task_dependencies")),
            sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies"),
        )
    if _table_exists("task_dependencies") and not _index_exists("task_dependencies", "ix_task_dependencies_task_id"):
        op.create_index(
            "ix_task_dependencies_task_id",
            "task_dependencies",
            ["task_id"],
            unique=False,
        )
    if _table_exists("task_dependencies") and not _index_exists("task_dependencies", "ix_task_dependencies_depends_on_task_id"):
        op.create_index(
            "ix_task_dependencies_depends_on_task_id",
            "task_dependencies",
            ["depends_on_task_id"],
            unique=False,
        )

    if not _table_exists("orchestrator_lock"):
        op.create_table(
            "orchestrator_lock",
            sa.Column("lock_id", sa.String(length=255), nullable=False),
            sa.Column("lock_key", sa.String(length=255), nullable=False),
            sa.Column("worker_id", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("lock_id", name=op.f("pk_orchestrator_lock")),
        )
    if _table_exists("orchestrator_lock") and not _index_exists("orchestrator_lock", op.f("ix_orchestrator_lock_lock_key")):
        op.create_index(
            op.f("ix_orchestrator_lock_lock_key"),
            "orchestrator_lock",
            ["lock_key"],
            unique=False,
        )

    if not _column_exists("task_executions", "input_hash"):
        op.add_column("task_executions", sa.Column("input_hash", sa.String(length=64), nullable=True))
    if not _index_exists("task_executions", op.f("ix_task_executions_input_hash")):
        op.create_index(
            op.f("ix_task_executions_input_hash"),
            "task_executions",
            ["input_hash"],
            unique=False,
        )
    if not _index_exists("task_executions", "ix_task_executions_wf_task"):
        op.create_index(
            "ix_task_executions_wf_task",
            "task_executions",
            ["workflow_id", "task_id"],
            unique=False,
        )
    if not _index_exists("task_executions", "ix_task_executions_unique_idempotent"):
        op.execute(
            text(
                "CREATE UNIQUE INDEX ix_task_executions_unique_idempotent "
                "ON task_executions (task_id, input_hash) "
                "WHERE status = 'done' AND input_hash IS NOT NULL"
            )
        )

    op.execute("ALTER TABLE task DROP CONSTRAINT IF EXISTS ck_task_status_allowed")
    op.execute(
        "ALTER TABLE task ADD CONSTRAINT ck_task_status_allowed "
        "CHECK (status IN ('backlog', 'queued', 'prepared', 'in_progress', 'completed', 'failed'))"
    )

    op.execute("ALTER TABLE task_execution_events DROP CONSTRAINT IF EXISTS ck_task_execution_events_event_type_allowed")
    op.execute(
        "ALTER TABLE task_execution_events ADD CONSTRAINT ck_task_execution_events_event_type_allowed "
        "CHECK (event_type IN ("
        "'started', 'progress', 'completed', 'error', 'status_update', "
        "'execution.claimed', 'execution.dispatched', 'execution.started', "
        "'execution.completed', 'execution.failed', 'session.created', 'session.closed', "
        "'session.initialized', 'message.sent', 'message.received', 'stream.connected', "
        "'stream.disconnected', 'stream.heartbeat', 'result.inspected', "
        "'commit.adoption_started', 'commit.adoption_success', 'commit.adoption_conflict', "
        "'retry.scheduled', 'retry.exhausted'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE task_execution_events DROP CONSTRAINT IF EXISTS ck_task_execution_events_event_type_allowed")
    op.execute(
        "ALTER TABLE task_execution_events ADD CONSTRAINT ck_task_execution_events_event_type_allowed "
        "CHECK (event_type IN ("
        "'started', 'progress', 'completed', 'error', 'status_update', "
        "'execution.claimed', 'execution.dispatched', 'execution.started', "
        "'execution.completed', 'execution.failed', 'session.created', 'session.closed', "
        "'message.sent', 'message.received', 'stream.connected', 'stream.disconnected', "
        "'stream.heartbeat', 'result.inspected', 'commit.adoption_started', "
        "'commit.adoption_success', 'commit.adoption_conflict', 'retry.scheduled', "
        "'retry.exhausted'))"
    )

    op.execute("ALTER TABLE task DROP CONSTRAINT IF EXISTS ck_task_status_allowed")
    op.execute(
        "ALTER TABLE task ADD CONSTRAINT ck_task_status_allowed "
        "CHECK (status IN ('backlog', 'queued', 'prepared', 'failed'))"
    )

    if _index_exists("task_executions", "ix_task_executions_unique_idempotent"):
        op.execute(text("DROP INDEX ix_task_executions_unique_idempotent"))
    if _index_exists("task_executions", "ix_task_executions_wf_task"):
        op.drop_index("ix_task_executions_wf_task", table_name="task_executions")
    if _index_exists("task_executions", op.f("ix_task_executions_input_hash")):
        op.drop_index(op.f("ix_task_executions_input_hash"), table_name="task_executions")
    if _column_exists("task_executions", "input_hash"):
        op.drop_column("task_executions", "input_hash")

    if _table_exists("orchestrator_lock") and _index_exists("orchestrator_lock", op.f("ix_orchestrator_lock_lock_key")):
        op.drop_index(op.f("ix_orchestrator_lock_lock_key"), table_name="orchestrator_lock")
    if _table_exists("orchestrator_lock"):
        op.drop_table("orchestrator_lock")

    if _table_exists("task_dependencies") and _index_exists("task_dependencies", "ix_task_dependencies_depends_on_task_id"):
        op.drop_index("ix_task_dependencies_depends_on_task_id", table_name="task_dependencies")
    if _table_exists("task_dependencies") and _index_exists("task_dependencies", "ix_task_dependencies_task_id"):
        op.drop_index("ix_task_dependencies_task_id", table_name="task_dependencies")
    if _table_exists("task_dependencies"):
        op.drop_table("task_dependencies")

    if _table_exists("execution_plan") and _index_exists("execution_plan", "ix_execution_plan_status"):
        op.drop_index("ix_execution_plan_status", table_name="execution_plan")
    if _table_exists("execution_plan") and _index_exists("execution_plan", "ix_execution_plan_created_by_task_id"):
        op.drop_index("ix_execution_plan_created_by_task_id", table_name="execution_plan")
    if _table_exists("execution_plan") and _index_exists("execution_plan", "ix_execution_plan_requirement_id"):
        op.drop_index("ix_execution_plan_requirement_id", table_name="execution_plan")
    if _table_exists("execution_plan"):
        op.drop_table("execution_plan")
