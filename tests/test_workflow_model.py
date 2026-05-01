"""Tests for workflow model and migrations.

Validates REQ-015 WP01: Workflow Data Model & Migration
"""

from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime

from execqueue.orchestrator.workflow_models import (
    WorkflowStatus,
    WorkflowContext,
    PreparedExecutionContext,
    Workflow,
)


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum."""

    def test_workflow_status_values(self):
        """Verify WorkflowStatus has correct values."""
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.DONE.value == "done"
        assert WorkflowStatus.FAILED.value == "failed"

    def test_workflow_status_from_string(self):
        """Verify WorkflowStatus can be created from string."""
        assert WorkflowStatus("running") == WorkflowStatus.RUNNING
        assert WorkflowStatus("done") == WorkflowStatus.DONE
        assert WorkflowStatus("failed") == WorkflowStatus.FAILED


class TestPreparedExecutionContext:
    """Tests for PreparedExecutionContext dataclass."""

    def test_prepared_execution_context_creation(self):
        """Verify PreparedExecutionContext can be created."""
        task_id = uuid4()
        ctx = PreparedExecutionContext(
            task_id=task_id,
            branch_name="feature/test",
            worktree_path="/tmp/worktree",
            commit_sha="abc123",
        )
        assert ctx.task_id == task_id
        assert ctx.branch_name == "feature/test"
        assert ctx.worktree_path == "/tmp/worktree"
        assert ctx.commit_sha == "abc123"

    def test_prepared_execution_context_optional_commit_sha(self):
        """Verify PreparedExecutionContext works without commit_sha."""
        task_id = uuid4()
        ctx = PreparedExecutionContext(
            task_id=task_id,
            branch_name="feature/test",
            worktree_path="/tmp/worktree",
            commit_sha=None,
        )
        assert ctx.commit_sha is None


class TestWorkflowContext:
    """Tests for WorkflowContext dataclass."""

    def test_workflow_context_creation_minimal(self):
        """Verify WorkflowContext can be created with minimal fields."""
        workflow_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=workflow_id,
            epic_id=None,
            requirement_id=None,
        )
        assert ctx.workflow_id == workflow_id
        assert ctx.epic_id is None
        assert ctx.requirement_id is None
        assert ctx.tasks == []
        assert ctx.dependencies == {}
        assert isinstance(ctx.created_at, datetime)

    def test_workflow_context_with_epic_and_requirement(self):
        """Verify WorkflowContext with epic_id and requirement_id."""
        workflow_id = uuid4()
        epic_id = uuid4()
        requirement_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=workflow_id,
            epic_id=epic_id,
            requirement_id=requirement_id,
        )
        assert ctx.epic_id == epic_id
        assert ctx.requirement_id == requirement_id

    def test_workflow_context_with_tasks_and_dependencies(self):
        """Verify WorkflowContext with tasks and dependencies."""
        workflow_id = uuid4()
        task_id = uuid4()
        task_ctx = PreparedExecutionContext(
            task_id=task_id,
            branch_name="main",
            worktree_path="/tmp",
            commit_sha=None,
        )
        dependencies = {task_id: []}
        ctx = WorkflowContext(
            workflow_id=workflow_id,
            epic_id=None,
            requirement_id=None,
            tasks=[task_ctx],
            dependencies=dependencies,
        )
        assert len(ctx.tasks) == 1
        assert ctx.tasks[0].task_id == task_id
        assert ctx.dependencies == dependencies


class TestWorkflowORM:
    """Tests for Workflow ORM model."""

    def test_workflow_table_name(self):
        """Verify Workflow has correct table name."""
        assert Workflow.__tablename__ == "workflow"

    def test_workflow_status_constraint(self):
        """Verify Workflow has status check constraint."""
        constraints = [c for c in Workflow.__table_args__ if hasattr(c, "sqltext")]
        assert len(constraints) == 1
        constraint = constraints[0]
        # Naming convention in base.py adds ck_%(table_name)s_ prefix
        assert constraint.name.startswith("ck_workflow_")
        assert "status_allowed" in constraint.name

    def test_workflow_columns(self):
        """Verify Workflow has all required columns."""
        columns = Workflow.__table__.columns
        assert "id" in columns
        assert "epic_id" in columns
        assert "requirement_id" in columns
        assert "status" in columns
        assert "runner_uuid" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_workflow_column_nullable_settings(self):
        """Verify nullable settings for workflow columns."""
        columns = Workflow.__table__.columns
        assert columns["id"].nullable is False
        assert columns["epic_id"].nullable is True
        assert columns["requirement_id"].nullable is True
        assert columns["status"].nullable is False
        assert columns["runner_uuid"].nullable is True

    def test_workflow_default_status(self):
        """Verify Workflow has default status."""
        status_col = Workflow.__table__.columns["status"]
        assert status_col.default.arg == WorkflowStatus.RUNNING.value
        assert status_col.server_default.arg == "running"


class TestWorkflowModelIntegration:
    """Integration tests for workflow model."""

    def test_workflow_status_enum_matches_constraint(self):
        """Verify WorkflowStatus enum values match DB constraint."""
        # The constraint is: status IN ('running', 'done', 'failed')
        constraint_values = {"running", "done", "failed"}
        enum_values = {s.value for s in WorkflowStatus}
        assert enum_values == constraint_values
