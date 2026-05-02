"""Comprehensive tests for orchestrator core logic.

This test suite covers:
- Candidate discovery with priority ordering
- Task grouping by requirement/epic/standalone
- Cycle detection with various scenarios (self-cycles, simple cycles, complex cycles)
- Dependency extraction with malformed data
- Validation with structured errors
- Exception hierarchy
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4, UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task, TaskStatus, TaskType
from execqueue.orchestrator.candidate_discovery import CandidateDiscovery
from execqueue.orchestrator.grouping import TaskGroup, TaskGroupingEngine
from execqueue.orchestrator.context_builder import WorkflowContextBuilder
from execqueue.orchestrator.exceptions import (
    OrchestratorError,
    DependencyError,
    CycleError,
    ValidationError,
)
from execqueue.orchestrator.workflow_models import WorkflowContext, PreparedExecutionContext


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", future=True, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_task(
    task_id: str | None = None,
    task_number: int = 1,
    status: TaskStatus = TaskStatus.BACKLOG,
    task_type: TaskType = TaskType.EXECUTION,
    details: dict | None = None,
    requirement_id: UUID | None = None,
    execution_order: int | None = None,
    created_at: datetime | None = None,
    prompt: str = "Test prompt for task",
    title: str = "Test Task",
    max_retries: int = 3,
    created_by_type: str = "user",
    created_by_ref: str = "test",
) -> Task:
    """Helper to create Task instances for testing.
    
    Note: The Task model has NOT NULL constraints on several fields.
    """
    task = Task(
        id=uuid4() if task_id is None else UUID(task_id),
        task_number=task_number,
        title=title,
        prompt=prompt,
        status=status.value,
        type=task_type,
        details=details or {},
        requirement_id=requirement_id,
        execution_order=execution_order,
        created_at=created_at or datetime.now(timezone.utc),
        max_retries=max_retries,
        retry_count=0,
        preparation_attempt_count=0,
        created_by_type=created_by_type,
        created_by_ref=created_by_ref,
    )
    return task


# ============================================================================
# Candidate Discovery Tests
# ============================================================================

class TestCandidateDiscovery:
    """Tests for CandidateDiscovery."""

    def test_find_candidates_empty(self, db_session):
        """Test finding candidates when no tasks exist."""
        discovery = CandidateDiscovery(max_batch_size=10)
        candidates = discovery.find_candidates(db_session)
        
        assert candidates == []

    def test_find_candidates_filters_backlog_only(self, db_session):
        """Test that only backlog tasks are returned."""
        discovery = CandidateDiscovery(max_batch_size=10)
        
        # Create tasks with different statuses
        backlog_task = create_task(task_number=1, status=TaskStatus.BACKLOG)
        queued_task = create_task(task_number=2, status=TaskStatus.QUEUED)
        completed_task = create_task(task_number=3, status=TaskStatus.COMPLETED)
        
        db_session.add_all([backlog_task, queued_task, completed_task])
        db_session.commit()
        
        candidates = discovery.find_candidates(db_session)
        
        assert len(candidates) == 1
        assert candidates[0].id == backlog_task.id

    def test_find_candidates_filters_by_type(self, db_session):
        """Test that only supported task types are returned."""
        discovery = CandidateDiscovery(
            max_batch_size=10,
            supported_types=(TaskType.EXECUTION,),
        )
        
        execution_task = create_task(task_number=4, task_type=TaskType.EXECUTION)
        planning_task = create_task(task_number=5, task_type=TaskType.PLANNING)
        
        db_session.add_all([execution_task, planning_task])
        db_session.commit()
        
        candidates = discovery.find_candidates(db_session)
        
        assert len(candidates) == 1
        assert candidates[0].id == execution_task.id

    def test_find_candidates_priority_ordering(self, db_session):
        """Test that tasks are ordered by priority (DESC)."""
        discovery = CandidateDiscovery(max_batch_size=10)
        
        # Create tasks with same execution_order but different priorities
        low_priority = create_task(
            task_number=1,
            execution_order=1,
            details={"priority": 1},
        )
        high_priority = create_task(
            task_number=2,
            execution_order=1,
            details={"priority": 10},
        )
        medium_priority = create_task(
            task_number=3,
            execution_order=1,
            details={"priority": 5},
        )
        
        db_session.add_all([low_priority, high_priority, medium_priority])
        db_session.commit()
        
        candidates = discovery.find_candidates(db_session)
        
        # Should be ordered: high (10), medium (5), low (1)
        assert len(candidates) == 3
        assert candidates[0].id == high_priority.id
        assert candidates[1].id == medium_priority.id
        assert candidates[2].id == low_priority.id

    def test_find_candidates_execution_order_takes_precedence(self, db_session):
        """Test that execution_order takes precedence over priority."""
        discovery = CandidateDiscovery(max_batch_size=10)
        
        # Task with lower execution_order but higher priority
        task1 = create_task(
            task_number=1,
            execution_order=1,
            details={"priority": 1},
        )
        # Task with higher execution_order but lower priority
        task2 = create_task(
            task_number=2,
            execution_order=2,
            details={"priority": 100},
        )
        
        db_session.add_all([task1, task2])
        db_session.commit()
        
        candidates = discovery.find_candidates(db_session)
        
        # task1 should come first due to lower execution_order
        assert candidates[0].id == task1.id
        assert candidates[1].id == task2.id

    def test_find_candidates_max_batch_size(self, db_session):
        """Test that max_batch_size limits results."""
        discovery = CandidateDiscovery(max_batch_size=3)
        
        # Create 10 tasks
        tasks = [create_task(task_number=i) for i in range(10)]
        db_session.add_all(tasks)
        db_session.commit()
        
        candidates = discovery.find_candidates(db_session)
        
        assert len(candidates) == 3

    def test_find_candidates_excludes_task_ids(self, db_session):
        """Test that exclude_task_ids filters out specified tasks."""
        discovery = CandidateDiscovery(max_batch_size=10)
        
        task1 = create_task(task_number=1)
        task2 = create_task(task_number=2)
        task3 = create_task(task_number=3)
        
        db_session.add_all([task1, task2, task3])
        db_session.commit()
        
        candidates = discovery.find_candidates(
            db_session,
            exclude_task_ids=[task1.id, task2.id],
        )
        
        assert len(candidates) == 1
        assert candidates[0].id == task3.id

    def test_find_candidates_handles_missing_priority(self, db_session):
        """Test that tasks without priority are handled correctly."""
        discovery = CandidateDiscovery(max_batch_size=10)
        
        task_no_priority = create_task(task_number=1, details={})
        task_with_priority = create_task(task_number=2, details={"priority": 5})
        
        db_session.add_all([task_no_priority, task_with_priority])
        db_session.commit()
        
        candidates = discovery.find_candidates(db_session)
        
        # Task with priority should come first
        assert candidates[0].id == task_with_priority.id
        assert candidates[1].id == task_no_priority.id


# ============================================================================
# Task Grouping Tests
# ============================================================================

class TestTaskGroupingEngine:
    """Tests for TaskGroupingEngine."""

    def test_group_by_requirement(self, db_session):
        """Test grouping tasks by requirement_id."""
        engine = TaskGroupingEngine()
        
        req_id = uuid4()
        task1 = create_task(requirement_id=req_id, task_number=1)
        task2 = create_task(requirement_id=req_id, task_number=2)
        task3 = create_task(requirement_id=uuid4(), task_number=3)  # Different req
        
        candidates = [task1, task2, task3]
        groups = engine.create_groups(db_session, candidates)
        
        # Should have 2 groups: one for each requirement_id
        requirement_groups = [g for g in groups if g.group_type == "requirement"]
        assert len(requirement_groups) == 2
        
        # Find the group with our req_id
        target_group = next(g for g in requirement_groups if g.requirement_id == req_id)
        assert len(target_group.tasks) == 2
        assert task1.id in [t.id for t in target_group.tasks]
        assert task2.id in [t.id for t in target_group.tasks]

    def test_group_by_epic(self, db_session):
        """Test grouping tasks by epic_id from details."""
        engine = TaskGroupingEngine()
        
        epic_id = str(uuid4())
        task1 = create_task(task_number=1, details={"epic_id": epic_id})
        task2 = create_task(task_number=2, details={"epic_id": epic_id})
        task3 = create_task(task_number=3, details={"epic_id": str(uuid4())})  # Different epic
        
        # These are standalone (no requirement_id)
        candidates = [task1, task2, task3]
        groups = engine.create_groups(db_session, candidates)
        
        epic_groups = [g for g in groups if g.group_type == "epic"]
        assert len(epic_groups) == 2
        
        target_group = next(g for g in epic_groups if g.epic_id == UUID(epic_id))
        assert len(target_group.tasks) == 2

    def test_group_standalone(self, db_session):
        """Test grouping standalone tasks."""
        engine = TaskGroupingEngine()
        
        task1 = create_task(task_number=1, details={})
        task2 = create_task(task_number=2, details={})
        
        candidates = [task1, task2]
        groups = engine.create_groups(db_session, candidates)
        
        standalone_groups = [g for g in groups if g.group_type == "standalone"]
        assert len(standalone_groups) == 2
        
        # Each standalone task should have its own group
        for group in standalone_groups:
            assert len(group.tasks) == 1

    def test_grouping_priority_requirement_over_epic(self, db_session):
        """Test that requirement_id takes priority over epic_id."""
        engine = TaskGroupingEngine()
        
        req_id = uuid4()
        epic_id = str(uuid4())
        
        # Task has both requirement_id and epic_id
        task = create_task(
            task_number=1,
            requirement_id=req_id,
            details={"epic_id": epic_id},
        )
        
        candidates = [task]
        groups = engine.create_groups(db_session, candidates)
        
        # Should be grouped as requirement, not epic
        requirement_groups = [g for g in groups if g.group_type == "requirement"]
        epic_groups = [g for g in groups if g.group_type == "epic"]
        
        assert len(requirement_groups) == 1
        assert len(epic_groups) == 0


# ============================================================================
# Cycle Detection Tests
# ============================================================================

class TestCycleDetection:
    """Tests for cycle detection in dependencies."""

    def test_detect_no_cycles(self):
        """Test detection with no cycles."""
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

    def test_detect_self_cycle(self):
        """Test detection of self-cycle (task depends on itself)."""
        builder = WorkflowContextBuilder()
        
        task1_id = uuid4()
        
        deps = {
            task1_id: [task1_id],  # Self-cycle
        }
        
        result = builder.detect_cycles(deps)
        
        assert result.has_cycles
        assert len(result.error_messages) >= 1
        assert "Cycle detected" in result.error_messages[0]

    def test_detect_simple_cycle(self):
        """Test detection of simple A->B->A cycle."""
        builder = WorkflowContextBuilder()
        
        task1_id = uuid4()
        task2_id = uuid4()
        
        deps = {
            task1_id: [task2_id],
            task2_id: [task1_id],
        }
        
        result = builder.detect_cycles(deps)
        
        assert result.has_cycles
        assert len(result.error_messages) >= 1

    def test_detect_longer_cycle(self):
        """Test detection of longer A->B->C->A cycle."""
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

    def test_detect_complex_cycle(self):
        """Test detection of complex cycle with multiple branches."""
        builder = WorkflowContextBuilder()
        
        task1_id = uuid4()
        task2_id = uuid4()
        task3_id = uuid4()
        task4_id = uuid4()
        
        deps = {
            task1_id: [task2_id, task3_id],
            task2_id: [task4_id],
            task3_id: [task4_id],
            task4_id: [task1_id],  # Creates cycle back to task1
        }
        
        result = builder.detect_cycles(deps)
        
        assert result.has_cycles
        assert len(result.error_messages) >= 1

    def test_detect_cycles_ignores_external_deps(self):
        """Test that external dependencies don't cause false positives."""
        builder = WorkflowContextBuilder()
        
        task1_id = uuid4()
        task2_id = uuid4()
        external_id = uuid4()  # Not in deps keys
        
        deps = {
            task1_id: [task2_id],
            task2_id: [external_id],  # External, should be ignored
        }
        
        result = builder.detect_cycles(deps)
        
        # Should not detect a cycle since external_id is not in the graph
        assert not result.has_cycles

    def test_detect_cycles_with_raise(self):
        """Test that raise_on_cycle raises CycleError."""
        builder = WorkflowContextBuilder()
        
        task1_id = uuid4()
        task2_id = uuid4()
        
        deps = {
            task1_id: [task2_id],
            task2_id: [task1_id],
        }
        
        with pytest.raises(CycleError) as exc_info:
            builder.detect_cycles(deps, raise_on_cycle=True)
        
        assert "cycle" in str(exc_info.value).lower()


# ============================================================================
# Dependency Extraction Tests
# ============================================================================

class TestDependencyExtraction:
    """Tests for dependency extraction with malformed data."""

    def test_extract_no_malformed_data(self):
        """Test extraction when all data is valid."""
        builder = WorkflowContextBuilder()
        
        task1 = create_task(task_number=1)
        task2 = create_task(
            task_number=2,
            details={"depends_on": str(task1.id)},
        )
        
        deps = builder.extract_dependencies([task1, task2])
        
        assert len(deps) == 2
        assert deps[task2.id] == [task1.id]

    def test_extract_ignores_malformed_strings(self):
        """Test that malformed dependency strings are ignored."""
        builder = WorkflowContextBuilder()
        
        task1 = create_task(task_number=1)
        task2 = create_task(
            task_number=2,
            details={"depends_on": "not-a-uuid"},
        )
        
        deps = builder.extract_dependencies([task1, task2])
        
        # Should not include the malformed dependency
        assert deps[task2.id] == []

    def test_extract_ignores_malformed_list_items(self):
        """Test that malformed items in dependency list are ignored."""
        builder = WorkflowContextBuilder()
        
        task1 = create_task(task_number=1)
        task2 = create_task(
            task_number=2,
            details={"depends_on": [str(task1.id), "invalid", "also-invalid"]},
        )
        
        deps = builder.extract_dependencies([task1, task2])
        
        # Should only include valid dependency
        assert deps[task2.id] == [task1.id]

    def test_extract_raises_on_malformed_with_flag(self):
        """Test that raise_on_error raises DependencyError."""
        builder = WorkflowContextBuilder()
        
        task1 = create_task(task_number=1)
        task2 = create_task(
            task_number=2,
            details={"depends_on": "not-a-uuid"},
        )
        
        with pytest.raises(DependencyError) as exc_info:
            builder.extract_dependencies([task1, task2], raise_on_error=True)
        
        assert "malformed" in str(exc_info.value).lower()

    def test_extract_tracks_unknown_dependencies(self):
        """Test that unknown dependencies are tracked."""
        builder = WorkflowContextBuilder()
        
        task1 = create_task(task_number=1)
        unknown_id = str(uuid4())
        task2 = create_task(
            task_number=2,
            details={"depends_on": unknown_id},  # Unknown task
        )
        
        # Should silently ignore unknown deps by default
        deps = builder.extract_dependencies([task1, task2])
        assert deps[task2.id] == []

    def test_extract_handles_none_depends_on(self):
        """Test handling of None depends_on value."""
        builder = WorkflowContextBuilder()
        
        task1 = create_task(task_number=1, details={"depends_on": None})
        task2 = create_task(task_number=2, details={})
        
        deps = builder.extract_dependencies([task1, task2])
        
        assert deps[task1.id] == []
        assert deps[task2.id] == []


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidation:
    """Tests for workflow context validation."""

    def test_validate_complete_dependency_map(self):
        """Test that validation ensures complete dependency map."""
        builder = WorkflowContextBuilder()
        
        workflow_id = uuid4()
        task1_id = uuid4()
        task2_id = uuid4()
        
        # Missing task2_id in dependencies
        ctx = MagicMock()
        ctx.workflow_id = workflow_id
        ctx.tasks = [
            PreparedExecutionContext(task_id=task1_id, branch_name="main", worktree_path="/tmp", commit_sha=None),
            PreparedExecutionContext(task_id=task2_id, branch_name="main", worktree_path="/tmp", commit_sha=None),
        ]
        ctx.dependencies = {task1_id: []}  # task2_id missing
        
        errors = builder.validate_context(ctx)
        
        assert any("missing from dependencies map" in e for e in errors)

    def test_validate_with_raise(self):
        """Test that raise_on_error raises ValidationError."""
        builder = WorkflowContextBuilder()
        
        ctx = MagicMock()
        ctx.workflow_id = None  # Invalid
        ctx.tasks = []  # Invalid
        ctx.dependencies = {}
        
        with pytest.raises(ValidationError) as exc_info:
            builder.validate_context(ctx, raise_on_error=True)
        
        assert "validation" in str(exc_info.value).lower()


# ============================================================================
# Exception Hierarchy Tests
# ============================================================================

class TestExceptionHierarchy:
    """Tests for the orchestrator exception hierarchy."""

    def test_orchestrator_error_base(self):
        """Test base OrchestratorError."""
        error = OrchestratorError("Test error", task_id="task-123")
        
        assert str(error) == "Test error (task=task-123)"
        assert error.task_id == "task-123"
        assert error.workflow_id is None

    def test_dependency_error(self):
        """Test DependencyError with details."""
        error = DependencyError(
            message="Invalid dependency",
            unknown_dependencies=["dep-1", "dep-2"],
            malformed_entries=["bad-entry"],
        )
        
        assert error.unknown_dependencies == ["dep-1", "dep-2"]
        assert error.malformed_entries == ["bad-entry"]

    def test_cycle_error_format_cycles(self):
        """Test CycleError.format_cycles()."""
        cycle1 = [str(uuid4()), str(uuid4()), str(uuid4())]
        error = CycleError(
            message="Cycle detected",
            cycles=[cycle1],
        )
        
        formatted = error.format_cycles()
        assert "Cycle 1:" in formatted
        assert "->" in formatted

    def test_validation_error_format_errors(self):
        """Test ValidationError.format_errors()."""
        error = ValidationError(
            message="Validation failed",
            errors=["Error 1", "Error 2", "Error 3"],
        )
        
        formatted = error.format_errors()
        assert "Error 1" in formatted
        assert "Error 2" in formatted
        assert "Error 3" in formatted

    def test_exception_inheritance(self):
        """Test that all exceptions inherit from OrchestratorError."""
        assert issubclass(DependencyError, OrchestratorError)
        assert issubclass(CycleError, OrchestratorError)
        assert issubclass(ValidationError, OrchestratorError)
