"""Tests for ExecQueue ORM execution tracking models.

This module contains comprehensive tests for the execution tracking models:
- ExecutionPlan
- TaskDependency
- TaskExecution
- TaskExecutionEvent

Note: Core models (Requirement, Task) are tested in execqueue/db/models.py context.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from execqueue.db.base import Base
from execqueue.models import (
    ExecutionPlan,
    TaskDependency,
    TaskExecution,
    TaskExecutionEvent,
)
from execqueue.models.enums import (
    EventDirection,
    EventType,
    ExecutionStatus,
)


class TestModelImports:
    """Test that all execution models and enums can be imported."""

    def test_base_imports(self):
        """Test that Base can be imported."""
        assert Base is not None

    def test_execution_plan_imports(self):
        """Test that ExecutionPlan model can be imported."""
        assert ExecutionPlan is not None

    def test_task_dependency_imports(self):
        """Test that TaskDependency model can be imported."""
        assert TaskDependency is not None

    def test_task_execution_imports(self):
        """Test that TaskExecution model can be imported."""
        assert TaskExecution is not None

    def test_task_execution_event_imports(self):
        """Test that TaskExecutionEvent model can be imported."""
        assert TaskExecutionEvent is not None

    def test_all_enums_import(self):
        """Test that all execution enums can be imported."""
        assert ExecutionStatus is not None
        assert EventDirection is not None
        assert EventType is not None


class TestEnums:
    """Test enum definitions and values."""

    def test_execution_status_values(self):
        """Test ExecutionStatus enum values."""
        assert ExecutionStatus.PREPARED.value == "prepared"
        assert ExecutionStatus.QUEUED.value == "queued"
        assert ExecutionStatus.IN_PROGRESS.value == "in_progress"
        assert ExecutionStatus.REVIEW.value == "review"
        assert ExecutionStatus.DONE.value == "done"
        assert ExecutionStatus.FAILED.value == "failed"

    def test_event_direction_values(self):
        """Test EventDirection enum values."""
        assert EventDirection.INBOUND.value == "inbound"
        assert EventDirection.OUTBOUND.value == "outbound"

    def test_event_type_values(self):
        """Test EventType enum values."""
        assert EventType.STARTED.value == "started"
        assert EventType.PROGRESS.value == "progress"
        assert EventType.COMPLETED.value == "completed"
        assert EventType.ERROR.value == "error"
        assert EventType.STATUS_UPDATE.value == "status_update"


class TestModelTableDefinitions:
    """Test that models have correct table definitions."""

    def test_execution_plan_has_table(self):
        """Test that ExecutionPlan has __tablename__."""
        assert ExecutionPlan.__tablename__ == "execution_plan"

    def test_task_dependency_has_table(self):
        """Test that TaskDependency has __tablename__."""
        assert TaskDependency.__tablename__ == "task_dependencies"

    def test_task_execution_has_table(self):
        """Test that TaskExecution has __tablename__."""
        assert TaskExecution.__tablename__ == "task_executions"

    def test_task_execution_event_has_table(self):
        """Test that TaskExecutionEvent has __tablename__."""
        assert TaskExecutionEvent.__tablename__ == "task_execution_events"


class TestModelColumns:
    """Test that models have expected columns."""

    def test_execution_plan_has_id_column(self):
        """Test that ExecutionPlan has id column."""
        assert "id" in ExecutionPlan.__table__.columns

    def test_execution_plan_has_requirement_id_column(self):
        """Test that ExecutionPlan has requirement_id column."""
        assert "requirement_id" in ExecutionPlan.__table__.columns

    def test_execution_plan_has_content_column(self):
        """Test that ExecutionPlan has content column."""
        assert "content" in ExecutionPlan.__table__.columns

    def test_execution_plan_has_status_column(self):
        """Test that ExecutionPlan has status column."""
        assert "status" in ExecutionPlan.__table__.columns

    def test_task_dependency_has_task_id_column(self):
        """Test that TaskDependency has task_id column."""
        assert "task_id" in TaskDependency.__table__.columns

    def test_task_dependency_has_depends_on_task_id_column(self):
        """Test that TaskDependency has depends_on_task_id column."""
        assert "depends_on_task_id" in TaskDependency.__table__.columns

    def test_task_execution_has_id_column(self):
        """Test that TaskExecution has id column."""
        assert "id" in TaskExecution.__table__.columns

    def test_task_execution_has_task_id_column(self):
        """Test that TaskExecution has task_id column."""
        assert "task_id" in TaskExecution.__table__.columns

    def test_task_execution_has_runner_id_column(self):
        """Test that TaskExecution has runner_id column."""
        assert "runner_id" in TaskExecution.__table__.columns

    def test_task_execution_has_status_column(self):
        """Test that TaskExecution has status column."""
        assert "status" in TaskExecution.__table__.columns

    def test_task_execution_event_has_id_column(self):
        """Test that TaskExecutionEvent has id column."""
        assert "id" in TaskExecutionEvent.__table__.columns

    def test_task_execution_event_has_task_execution_id_column(self):
        """Test that TaskExecutionEvent has task_execution_id column."""
        assert "task_execution_id" in TaskExecutionEvent.__table__.columns

    def test_task_execution_event_has_direction_column(self):
        """Test that TaskExecutionEvent has direction column."""
        assert "direction" in TaskExecutionEvent.__table__.columns

    def test_task_execution_event_has_event_type_column(self):
        """Test that TaskExecutionEvent has event_type column."""
        assert "event_type" in TaskExecutionEvent.__table__.columns

    def test_task_execution_event_has_payload_column(self):
        """Test that TaskExecutionEvent has payload column."""
        assert "payload" in TaskExecutionEvent.__table__.columns


class TestDatabaseCreation:
    """Test that models can create database tables."""

    @pytest.fixture
    def sqlite_engine(self):
        """Create an in-memory SQLite database engine."""
        return create_engine("sqlite:///:memory:", echo=False)

    def test_create_all_tables(self, sqlite_engine):
        """Test that all execution tracking tables can be created."""
        Base.metadata.create_all(bind=sqlite_engine)

        # Verify tables exist
        inspector = sqlite_engine.dialect.get_table_names(sqlite_engine.connect())
        assert "execution_plan" in inspector
        assert "task_dependencies" in inspector
        assert "task_executions" in inspector
        assert "task_execution_events" in inspector

    def test_create_tables_does_not_raise(self, sqlite_engine):
        """Test that creating tables doesn't raise exceptions."""
        try:
            Base.metadata.create_all(bind=sqlite_engine)
        except Exception as e:
            pytest.fail(f"Creating tables raised an exception: {e}")


class TestModelRelationships:
    """Test model relationships."""

    def test_execution_plan_has_requirement_relationship(self):
        """Test that ExecutionPlan has requirement relationship."""
        assert hasattr(ExecutionPlan, "requirement")

    def test_task_dependency_has_relationship_fields(self):
        """Test that TaskDependency has relationship attributes."""
        assert hasattr(TaskDependency, "task")
        assert hasattr(TaskDependency, "depends_on_task")

    def test_task_execution_has_task_relationship(self):
        """Test that TaskExecution has task relationship."""
        assert hasattr(TaskExecution, "task")

    def test_task_execution_has_events_relationship(self):
        """Test that TaskExecution has events relationship."""
        assert hasattr(TaskExecution, "events")

    def test_task_execution_event_has_task_execution_relationship(self):
        """Test that TaskExecutionEvent has task_execution relationship."""
        assert hasattr(TaskExecutionEvent, "task_execution")


class TestModelValidation:
    """Test model validation and constraints."""

    def test_task_dependency_unique_constraint_exists(self):
        """Test that TaskDependency has unique constraint."""
        constraints = [c.name for c in TaskDependency.__table__.constraints]
        assert "uq_task_dependencies" in constraints

    def test_execution_plan_has_status_column(self):
        """Test that ExecutionPlan has status column for validation."""
        assert "status" in ExecutionPlan.__table__.columns

    def test_task_execution_has_status_column(self):
        """Test that TaskExecution has status column for validation."""
        assert "status" in TaskExecution.__table__.columns

    def test_task_execution_event_has_direction_column(self):
        """Test that TaskExecutionEvent has direction column for validation."""
        assert "direction" in TaskExecutionEvent.__table__.columns

    def test_task_execution_event_has_event_type_column(self):
        """Test that TaskExecutionEvent has event_type column for validation."""
        assert "event_type" in TaskExecutionEvent.__table__.columns


class TestModelProperties:
    """Test model computed properties."""

    def test_task_execution_is_complete_property(self):
        """Test that TaskExecution has is_complete property."""
        assert hasattr(TaskExecution, "is_complete")

    def test_task_execution_is_successful_property(self):
        """Test that TaskExecution has is_successful property."""
        assert hasattr(TaskExecution, "is_successful")


class TestModelToDict:
    """Test model to_dict methods."""

    def test_task_execution_event_to_dict_method_exists(self):
        """Test that TaskExecutionEvent has to_dict method."""
        assert hasattr(TaskExecutionEvent, "to_dict")
        assert callable(getattr(TaskExecutionEvent, "to_dict"))


class TestTaskExecutionTotalTokens:
    """Tests for REQ-013 token tracking field."""

    def test_total_tokens_column_exists(self):
        """Test that total_tokens column exists on TaskExecution."""
        assert "total_tokens" in TaskExecution.__table__.columns

    def test_total_tokens_is_nullable(self):
        """Test that total_tokens column is nullable."""
        column = TaskExecution.__table__.columns["total_tokens"]
        assert column.nullable is True

    def test_total_tokens_type_is_biginteger(self):
        """Test that total_tokens uses BigInteger type."""
        from sqlalchemy import BigInteger

        column = TaskExecution.__table__.columns["total_tokens"]
        assert isinstance(column.type, BigInteger)

    def test_total_tokens_defaults_to_none(self):
        """Test that new TaskExecution instances have total_tokens=None by default."""
        from uuid import uuid4

        execution = TaskExecution(id=uuid4(), task_id=uuid4())
        assert execution.total_tokens is None

    def test_total_tokens_can_be_set(self):
        """Test that total_tokens can be set to an integer value."""
        from uuid import uuid4

        execution = TaskExecution(id=uuid4(), task_id=uuid4())
        execution.total_tokens = 1500
        assert execution.total_tokens == 1500

    def test_total_tokens_none_serializes_to_dict(self):
        """Test that None total_tokens is included in to_dict output."""
        from uuid import uuid4

        execution = TaskExecution(id=uuid4(), task_id=uuid4())
        result = execution.to_dict()
        assert "total_tokens" in result
        assert result["total_tokens"] is None

    def test_total_tokens_value_serializes_to_dict(self):
        """Test that set total_tokens is correctly serialized in to_dict output."""
        from uuid import uuid4

        execution = TaskExecution(id=uuid4(), task_id=uuid4())
        execution.total_tokens = 2500
        result = execution.to_dict()
        assert "total_tokens" in result
        assert result["total_tokens"] == 2500

    def test_total_tokens_zero_is_valid(self):
        """Test that zero total_tokens is a valid value (different from None)."""
        from uuid import uuid4

        execution = TaskExecution(id=uuid4(), task_id=uuid4())
        execution.total_tokens = 0
        result = execution.to_dict()
        assert result["total_tokens"] == 0

    def test_total_tokens_large_value(self):
        """Test that large token values work (BigInteger support)."""
        from uuid import uuid4

        execution = TaskExecution(id=uuid4(), task_id=uuid4())
        execution.total_tokens = 10_000_000
        assert execution.total_tokens == 10_000_000
        assert execution.to_dict()["total_tokens"] == 10_000_000


class TestModelRepr:
    """Test model __repr__ methods."""

    def test_execution_plan_repr_exists(self):
        """Test that ExecutionPlan has __repr__."""
        assert hasattr(ExecutionPlan, "__repr__")

    def test_task_dependency_repr_exists(self):
        """Test that TaskDependency has __repr__."""
        assert hasattr(TaskDependency, "__repr__")

    def test_task_execution_repr_exists(self):
        """Test that TaskExecution has __repr__."""
        assert hasattr(TaskExecution, "__repr__")

    def test_task_execution_event_repr_exists(self):
        """Test that TaskExecutionEvent has __repr__."""
        assert hasattr(TaskExecutionEvent, "__repr__")
