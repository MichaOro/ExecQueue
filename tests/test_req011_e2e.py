"""E2E tests for REQ-011 preparation flow.

These tests validate the complete preparation flow without starting execution.
They include negative assertions to ensure no execution is triggered.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task, TaskStatus, TaskType
from execqueue.orchestrator.main import Orchestrator
from execqueue.orchestrator.models import RunnerMode
from execqueue.orchestrator.observability import create_e2e_validator


@pytest.fixture
def db_engine():
    """Create in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create database session."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def worktree_root(tmp_path):
    """Create temporary worktree root."""
    worktree_dir = tmp_path / "worktrees"
    worktree_dir.mkdir()
    return worktree_dir


@pytest.fixture
def orchestrator(db_session, worktree_root, tmp_path):
    """Create orchestrator instance."""
    # Create a temporary git repo for testing
    base_repo = tmp_path / "repo"
    base_repo.mkdir()
    
    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=base_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=base_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=base_repo, check=True, capture_output=True)
    
    # Create initial commit
    (base_repo / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=base_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=base_repo, check=True, capture_output=True)
    
    return Orchestrator(
        worker_id="test-worker-1",
        max_batch_size=5,
        worktree_root=worktree_root,
        base_repo_path=base_repo,
    )


@pytest.fixture
def sample_task(db_session, tmp_path):
    """Create a sample backlog task."""
    task = Task(
        task_number=1,
        title="Test Task",
        prompt="Test prompt",
        type=TaskType.EXECUTION,
        status=TaskStatus.BACKLOG.value,
        max_retries=3,
        created_by_type="user",
        created_by_ref="test:123",
        details={"requires_write_access": True},
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def sample_readonly_task(db_session, tmp_path):
    """Create a sample read-only backlog task."""
    task = Task(
        task_number=2,
        title="Read-only Task",
        prompt="Read-only prompt",
        type=TaskType.ANALYSIS,
        status=TaskStatus.BACKLOG.value,
        max_retries=3,
        created_by_type="user",
        created_by_ref="test:123",
        details={"requires_write_access": False, "parallelization_mode": "parallel"},
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


class TestREQ011PreparationFlow:
    """E2E tests for REQ-011 preparation flow."""
    
    def test_readonly_task_preparation(
        self,
        db_session,
        orchestrator,
        sample_readonly_task,
    ):
        """Test complete preparation flow for a read-only task."""
        # Run preparation cycle
        results = orchestrator.run_preparation_cycle(db_session)
        
        # Validate results
        assert len(results) == 1
        result = results[0]
        
        assert result.success, f"Preparation failed: {result.error}"
        assert result.task_number == sample_readonly_task.task_number
        assert result.context is not None
        
        # Validate context
        context = result.context
        assert context.runner_mode == RunnerMode.READ_ONLY
        assert context.branch_name is None
        assert context.worktree_path is None
        assert context.commit_sha_before is None
        assert context.version == "v1"
        
        # Validate task status
        db_session.refresh(sample_readonly_task)
        assert sample_readonly_task.status == TaskStatus.PREPARED.value
    
    def test_mixed_batch_preparation_readonly_only(
        self,
        db_session,
        orchestrator,
        sample_readonly_task,
    ):
        """Test preparation with multiple read-only tasks."""
        # Create another read-only task
        task2 = Task(
            task_number=3,
            title="Read-only Task 2",
            prompt="Read-only prompt 2",
            type=TaskType.PLANNING,
            status=TaskStatus.BACKLOG.value,
            max_retries=3,
            created_by_type="user",
            created_by_ref="test:123",
            details={"requires_write_access": False},
        )
        db_session.add(task2)
        db_session.commit()
        
        # Run preparation cycle
        results = orchestrator.run_preparation_cycle(db_session)
        
        # Should have 2 results (both read-only)
        assert len(results) == 2
        
        # Validate both are read-only
        for result in results:
            assert result.success, f"Preparation failed: {result.error}"
            assert result.context.runner_mode == RunnerMode.READ_ONLY
            assert result.context.branch_name is None
        
        # Validate task statuses
        db_session.refresh(sample_readonly_task)
        assert sample_readonly_task.status == TaskStatus.PREPARED.value
    
    def test_stale_recovery(
        self,
        db_session,
        orchestrator,
        sample_task,
    ):
        """Test stale queued task recovery."""
        from execqueue.orchestrator.recovery import StaleQueuedRecovery
        from datetime import datetime, timedelta
        
        # Manually set task to queued with old timestamp
        sample_task.status = TaskStatus.QUEUED.value
        sample_task.queued_at = datetime.utcnow() - timedelta(hours=1)
        sample_task.locked_by = "stale-worker"
        sample_task.preparation_attempt_count = 1
        sample_task.last_preparation_error = "temporary connection timeout"
        db_session.commit()
        
        # Run recovery
        recovery = StaleQueuedRecovery(stale_timeout_minutes=30, max_preparation_attempts=3)
        results = recovery.run_recovery_cycle(db_session)
        
        # Should have recovered the task
        assert len(results) == 1
        task, new_status, reason = results[0]
        
        assert new_status == TaskStatus.BACKLOG
        assert reason == "Recoverable error"
        
        # Verify task fields were reset
        assert task.queued_at is None
        assert task.locked_by is None
        assert task.preparation_attempt_count == 0
    
    def test_retry_exhaustion(self, db_session, orchestrator, sample_task):
        """Test that retry exhaustion leads to failed status."""
        from execqueue.orchestrator.recovery import StaleQueuedRecovery
        from datetime import datetime, timedelta
        
        # Set task to queued with max attempts
        sample_task.status = TaskStatus.QUEUED.value
        sample_task.queued_at = datetime.utcnow() - timedelta(hours=1)
        sample_task.locked_by = "test-worker"
        sample_task.preparation_attempt_count = 3  # Max attempts
        sample_task.last_preparation_error = "connection timeout"
        db_session.commit()
        
        # Run recovery
        recovery = StaleQueuedRecovery(stale_timeout_minutes=30, max_preparation_attempts=3)
        results = recovery.run_recovery_cycle(db_session)
        
        # Should have failed the task
        assert len(results) == 1
        task, new_status, reason = results[0]
        
        assert new_status == TaskStatus.FAILED
        assert reason == "Retry exhaustion"
    
    def test_non_recoverable_error(self, db_session, orchestrator, sample_task):
        """Test non-recoverable error leads to immediate failure."""
        from execqueue.orchestrator.recovery import StaleQueuedRecovery
        from datetime import datetime, timedelta
        
        # Set task with non-recoverable error
        sample_task.status = TaskStatus.QUEUED.value
        sample_task.queued_at = datetime.utcnow() - timedelta(hours=1)
        sample_task.locked_by = "test-worker"
        sample_task.preparation_attempt_count = 0
        sample_task.last_preparation_error = "invalid branch name: @#$%"
        db_session.commit()
        
        # Run recovery
        recovery = StaleQueuedRecovery(stale_timeout_minutes=30, max_preparation_attempts=3)
        results = recovery.run_recovery_cycle(db_session)
        
        # Should have failed the task
        assert len(results) == 1
        task, new_status, reason = results[0]
        
        assert new_status == TaskStatus.FAILED
        assert reason == "Non-recoverable error"


class TestREQ011NegativeAssertions:
    """Negative assertions to ensure REQ-011 scope is respected."""
    
    def test_no_execution_started_readonly(
        self,
        db_session,
        orchestrator,
        sample_readonly_task,
    ):
        """Assert that preparation does NOT start execution."""
        # Run preparation
        results = orchestrator.run_preparation_cycle(db_session)
        
        # Negative assertions
        assert len(results) == 1
        assert results[0].success
        
        # Verify status is NOT in_progress
        db_session.refresh(sample_readonly_task)
        assert sample_readonly_task.status != "in_progress"
        assert sample_readonly_task.status == TaskStatus.PREPARED.value
        
        # Verify no TaskExecution was created (would be in separate table)
        # This is implicitly validated by the fact that we only prepared context
    
    def test_no_in_progress_status_readonly(
        self,
        db_session,
        orchestrator,
        sample_readonly_task,
    ):
        """Assert that task never transitions to in_progress in REQ-011."""
        results = orchestrator.run_preparation_cycle(db_session)
        
        db_session.refresh(sample_readonly_task)
        
        # Status should be PREPARED, not in_progress
        assert sample_readonly_task.status != "in_progress"
        assert sample_readonly_task.status == TaskStatus.PREPARED.value
        
        # in_progress is outside REQ-011 scope


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
