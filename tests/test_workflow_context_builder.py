"""Tests for workflow context builder."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from uuid import uuid4, UUID

from execqueue.db.models import Task
from execqueue.orchestrator.grouping import TaskGroup
from execqueue.orchestrator.context_builder import WorkflowContextBuilder
from execqueue.orchestrator.workflow_models import PreparedExecutionContext


def create_mock_task(
    task_id: str | None = None,
    task_number: int = 1,
    details: dict | None = None,
    branch_name: str | None = None,
    worktree_path: str | None = None,
    commit_sha: str | None = None,
) -> Task:
    """Helper to create mock Task instances."""
    task = MagicMock(spec=Task)
    task.id = uuid4() if task_id is None else UUID(task_id)
    task.task_number = task_number
    task.details = details or {}
    task.branch_name = branch_name
    task.worktree_path = worktree_path
    task.commit_sha_before = commit_sha
    return task


class TestWorkflowContextBuilder:
    """Tests for WorkflowContextBuilder."""

    def test_extract_dependencies_empty(self):
        """Test extracting dependencies from empty list."""
        builder = WorkflowContextBuilder()
        
        deps = builder.extract_dependencies([])
        
        assert deps == {}

    def test_extract_dependencies_no_dependencies(self):
        """Test extracting dependencies when none exist."""
        builder = WorkflowContextBuilder()
        task1 = create_mock_task(task_number=1, details={})
        task2 = create_mock_task(task_number=2, details={})
        
        deps = builder.extract_dependencies([task1, task2])
        
        assert len(deps) == 2
        assert deps[task1.id] == []
        assert deps[task2.id] == []

    def test_extract_dependencies_single_string(self):
        """Test extracting single dependency as string."""
        builder = WorkflowContextBuilder()
        task1_id = str(uuid4())
        task2_id = str(uuid4())
        task1 = create_mock_task(task_number=1, task_id=task1_id)
        task2 = create_mock_task(
            task_number=2,
            task_id=task2_id,
            details={"depends_on": task1_id},
        )
        
        deps = builder.extract_dependencies([task1, task2])
        
        assert len(deps) == 2
        assert deps[task1.id] == []
        assert deps[task2.id] == [UUID(task1_id)]

    def test_extract_dependencies_list(self):
        """Test extracting multiple dependencies as list."""
        builder = WorkflowContextBuilder()
        task1_id = str(uuid4())
        task2_id = str(uuid4())
        task3_id = str(uuid4())
        task1 = create_mock_task(task_number=1, task_id=task1_id)
        task2 = create_mock_task(task_number=2, task_id=task2_id)
        task3 = create_mock_task(
            task_number=3,
            task_id=task3_id,
            details={"depends_on": [task1_id, task2_id]},
        )
        
        deps = builder.extract_dependencies([task1, task2, task3])
        
        assert len(deps) == 3
        assert deps[task3.id] == [UUID(task1_id), UUID(task2_id)]

    def test_extract_dependencies_ignores_external(self):
        """Test that dependencies to external tasks are ignored."""
        builder = WorkflowContextBuilder()
        task1_id = str(uuid4())
        external_id = str(uuid4())
        task1 = create_mock_task(task_number=1, task_id=task1_id)
        task2 = create_mock_task(
            task_number=2,
            details={"depends_on": [task1_id, external_id]},
        )
        
        deps = builder.extract_dependencies([task1, task2])
        
        # Should only include task1_id, not external_id
        assert len(deps[task2.id]) == 1
        assert deps[task2.id][0] == UUID(task1_id)

    def test_detect_cycles_no_cycles(self):
        """Test cycle detection with no cycles."""
        builder = WorkflowContextBuilder()
        task1_id = uuid4()
        task2_id = uuid4()
        task3_id = uuid4()
        
        deps = {
            task1_id: [],
            task2_id: [task1_id],
            task3_id: [task1_id, task2_id],
        }
        
        result = builder.detect_cycles(deps)
        
        assert not result.has_cycles
        assert result.cycles == []
        assert result.error_messages == []

    def test_detect_cycles_simple_cycle(self):
        """Test cycle detection with simple A->B->A cycle."""
        builder = WorkflowContextBuilder()
        task1_id = uuid4()
        task2_id = uuid4()
        
        deps = {
            task1_id: [task2_id],
            task2_id: [task1_id],
        }
        
        result = builder.detect_cycles(deps)
        
        assert result.has_cycles
        assert len(result.cycles) >= 1
        assert len(result.error_messages) >= 1
        assert "Cycle detected" in result.error_messages[0]

    def test_detect_cycles_longer_cycle(self):
        """Test cycle detection with longer A->B->C->A cycle."""
        builder = WorkflowContextBuilder()
        task1_id = uuid4()
        task2_id = uuid4()
        task3_id = uuid4()
        
        deps = {
            task1_id: [task2_id],
            task2_id: [task3_id],
            task3_id: [task1_id],
        }
        
        result = builder.detect_cycles(deps)
        
        assert result.has_cycles
        assert len(result.error_messages) >= 1

    def test_validate_context_valid(self):
        """Test validation of valid context."""
        builder = WorkflowContextBuilder()
        workflow_id = uuid4()
        task1_id = uuid4()
        task2_id = uuid4()
        
        ctx = MagicMock()
        ctx.workflow_id = workflow_id
        ctx.tasks = [
            PreparedExecutionContext(task_id=task1_id, branch_name="main", worktree_path="/tmp", commit_sha=None),
            PreparedExecutionContext(task_id=task2_id, branch_name="main", worktree_path="/tmp", commit_sha=None),
        ]
        ctx.dependencies = {task2_id: [task1_id]}
        
        errors = builder.validate_context(ctx)
        
        assert errors == []

    def test_validate_context_missing_workflow_id(self):
        """Test validation fails with missing workflow_id."""
        builder = WorkflowContextBuilder()
        
        ctx = MagicMock()
        ctx.workflow_id = None
        ctx.tasks = []
        ctx.dependencies = {}
        
        errors = builder.validate_context(ctx)
        
        assert "workflow_id is required" in errors

    def test_validate_context_missing_tasks(self):
        """Test validation fails with missing tasks."""
        builder = WorkflowContextBuilder()
        
        ctx = MagicMock()
        ctx.workflow_id = uuid4()
        ctx.tasks = []
        ctx.dependencies = {}
        
        errors = builder.validate_context(ctx)
        
        assert "tasks list is required" in errors

    def test_validate_context_unknown_dependency(self):
        """Test validation fails with unknown dependency."""
        builder = WorkflowContextBuilder()
        workflow_id = uuid4()
        task1_id = uuid4()
        unknown_id = uuid4()
        
        ctx = MagicMock()
        ctx.workflow_id = workflow_id
        ctx.tasks = [
            PreparedExecutionContext(task_id=task1_id, branch_name="main", worktree_path="/tmp", commit_sha=None),
        ]
        ctx.dependencies = {task1_id: [unknown_id]}
        
        errors = builder.validate_context(ctx)
        
        assert any("depends on unknown task" in e for e in errors)

    def test_validate_context_with_cycles(self):
        """Test validation fails with cycles."""
        builder = WorkflowContextBuilder()
        workflow_id = uuid4()
        task1_id = uuid4()
        task2_id = uuid4()
        
        ctx = MagicMock()
        ctx.workflow_id = workflow_id
        ctx.tasks = [
            PreparedExecutionContext(task_id=task1_id, branch_name="main", worktree_path="/tmp", commit_sha=None),
            PreparedExecutionContext(task_id=task2_id, branch_name="main", worktree_path="/tmp", commit_sha=None),
        ]
        ctx.dependencies = {task1_id: [task2_id], task2_id: [task1_id]}
        
        errors = builder.validate_context(ctx)
        
        assert any("Cycle detected" in e for e in errors)

    def test_build_context_from_group(self):
        """Test building context from TaskGroup."""
        builder = WorkflowContextBuilder()
        group_id = uuid4()
        task1 = create_mock_task(task_number=1, branch_name="main", worktree_path="/tmp")
        task2 = create_mock_task(
            task_number=2,
            branch_name="main",
            worktree_path="/tmp",
            details={"depends_on": str(task1.id)},
        )
        
        group = TaskGroup(
            group_id=group_id,
            tasks=[task1, task2],
            group_type="requirement",
            requirement_id=group_id,
        )
        
        ctx = builder.build_context(group)
        
        assert ctx.workflow_id == group_id
        assert ctx.requirement_id == group_id
        assert len(ctx.tasks) == 2
        assert ctx.tasks[0].task_id == task1.id
        assert ctx.tasks[1].task_id == task2.id
        assert task2.id in ctx.dependencies
        assert task1.id in ctx.dependencies[task2.id]

    def test_build_context_with_prepared_tasks(self):
        """Test building context with provided prepared tasks."""
        builder = WorkflowContextBuilder()
        group_id = uuid4()
        task1 = create_mock_task(task_number=1)
        task2 = create_mock_task(task_number=2)
        
        prepared = [
            PreparedExecutionContext(task_id=task1.id, branch_name="feature", worktree_path="/work", commit_sha="abc"),
            PreparedExecutionContext(task_id=task2.id, branch_name="feature", worktree_path="/work", commit_sha="def"),
        ]
        
        group = TaskGroup(
            group_id=group_id,
            tasks=[task1, task2],
            group_type="standalone",
        )
        
        ctx = builder.build_context(group, prepared_tasks=prepared)
        
        assert len(ctx.tasks) == 2
        assert ctx.tasks[0].branch_name == "feature"
        assert ctx.tasks[0].worktree_path == "/work"
        assert ctx.tasks[0].commit_sha == "abc"
