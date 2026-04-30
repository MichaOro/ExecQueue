"""Tests for REQ-012-02 Atomic Claim Queue Lifecycle.

This module tests:
- Atomic claim logic for prepared tasks
- Concurrency protection (two runners cannot claim same task)
- TaskExecution creation during claim
- Status transitions (prepared -> queued)
- Runner ID generation and persistence
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task, TaskStatus
from execqueue.models.enums import ExecutionStatus, EventType
from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent
from execqueue.runner.claim import ClaimFailedError, claim_task
from execqueue.runner.polling import poll_and_claim_tasks
from uuid import uuid4


class TestClaimTask:
    """Test the claim_task function."""

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite database session."""
        engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def test_claim_prepared_task_succeeds(self, db_session: Session):
        """Test that claiming a prepared task succeeds."""
        # Create a prepared task
        task = Task(
            task_number=1,
            title="Test Task",
            prompt="Test prompt",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add(task)
        db_session.commit()

        # Claim the task
        runner_id = "runner-1"
        execution = claim_task(db_session, task.id, runner_id)

        # Verify execution was created
        assert execution is not None
        assert execution.task_id == task.id
        assert execution.runner_id == runner_id
        assert execution.status == ExecutionStatus.QUEUED.value
        assert execution.attempt == 1
        assert execution.max_attempts == 3

        # Verify task status was updated
        db_session.refresh(task)
        assert task.status == TaskStatus.QUEUED.value

    def test_claim_non_prepared_task_fails(self, db_session: Session):
        """Test that claiming a non-prepared task fails."""
        # Create a backlog task
        task = Task(
            task_number=2,
            title="Test Task",
            prompt="Test prompt",
            type="execution",
            status=TaskStatus.BACKLOG.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add(task)
        db_session.commit()

        # Attempt to claim
        with pytest.raises(ClaimFailedError) as exc_info:
            claim_task(db_session, task.id, "runner-1")

        assert "cannot be claimed" in str(exc_info.value)

    def test_claim_nonexistent_task_fails(self, db_session: Session):
        """Test that claiming a nonexistent task fails."""
        fake_task_id = uuid4()

        with pytest.raises(ClaimFailedError) as exc_info:
            claim_task(db_session, fake_task_id, "runner-1")

        assert "not found" in str(exc_info.value)

    def test_claim_creates_execution_event(self, db_session: Session):
        """Test that claiming creates an EXECUTION_CLAIMED event."""
        # Create a prepared task
        task = Task(
            task_number=3,
            title="Test Task",
            prompt="Test prompt",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add(task)
        db_session.commit()

        # Claim the task
        execution = claim_task(db_session, task.id, "runner-1")
        db_session.commit()  # Commit to persist the event

        # Verify event was created
        events = db_session.query(TaskExecutionEvent).filter(
            TaskExecutionEvent.task_execution_id == execution.id
        ).all()

        assert len(events) == 1
        assert events[0].event_type == EventType.EXECUTION_CLAIMED.value
        assert events[0].sequence == 1
        assert "runner_id" in events[0].payload


class TestClaimConcurrency:
    """Test concurrency protection for claim operations."""

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite database session."""
        engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def test_two_runners_cannot_claim_same_task(self, db_session: Session):
        """Test that two runners cannot claim the same task simultaneously.

        This is the core concurrency test for REQ-012-02:
        - Runner 1 claims successfully
        - Runner 2 fails with ClaimFailedError
        """
        # Create a prepared task
        task = Task(
            task_number=4,
            title="Test Task",
            prompt="Test prompt",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add(task)
        db_session.commit()

        # Runner 1 claims successfully
        execution1 = claim_task(db_session, task.id, "runner-1")
        assert execution1.runner_id == "runner-1"

        # Runner 2 should fail
        with pytest.raises(ClaimFailedError) as exc_info:
            claim_task(db_session, task.id, "runner-2")

        assert "already has an active execution" in str(exc_info.value)

    def test_multiple_tasks_can_be_claimed_by_different_runners(self, db_session: Session):
        """Test that different runners can claim different tasks."""
        # Create two prepared tasks
        task1 = Task(
            task_number=5,
            title="Task 1",
            prompt="Prompt 1",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        task2 = Task(
            task_number=6,
            title="Task 2",
            prompt="Prompt 2",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add_all([task1, task2])
        db_session.commit()

        # Runner 1 claims task1
        execution1 = claim_task(db_session, task1.id, "runner-1")
        assert execution1.task_id == task1.id

        # Runner 2 claims task2
        execution2 = claim_task(db_session, task2.id, "runner-2")
        assert execution2.task_id == task2.id

        # Both claims succeeded
        assert execution1.runner_id == "runner-1"
        assert execution2.runner_id == "runner-2"

    def test_completed_execution_allows_new_claim(self, db_session: Session):
        """Test that a completed execution allows a new claim on the same task."""
        # Create a prepared task
        task = Task(
            task_number=7,
            title="Test Task",
            prompt="Test prompt",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add(task)
        db_session.commit()

        # First claim
        execution1 = claim_task(db_session, task.id, "runner-1")
        assert execution1.status == ExecutionStatus.QUEUED.value

        # Mark execution as done
        execution1.status = ExecutionStatus.DONE.value
        db_session.commit()

        # Task status is still QUEUED, need to set it back to PREPARED for re-claim test
        # In real scenario, this would be handled by the lifecycle
        task.status = TaskStatus.PREPARED.value
        db_session.commit()

        # Second claim should succeed now
        execution2 = claim_task(db_session, task.id, "runner-2")
        assert execution2.runner_id == "runner-2"
        assert execution2.id != execution1.id


class TestPollAndClaimTasks:
    """Test the poll_and_claim_tasks function."""

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite database session."""
        engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def test_poll_no_prepared_tasks_returns_empty(self, db_session: Session):
        """Test that polling with no prepared tasks returns empty list."""
        executions = poll_and_claim_tasks(db_session, "runner-1", batch_size=1)
        assert executions == []

    def test_poll_claims_prepared_tasks(self, db_session: Session):
        """Test that polling claims prepared tasks."""
        # Create prepared tasks
        task1 = Task(
            task_number=8,
            title="Task 1",
            prompt="Prompt 1",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        task2 = Task(
            task_number=9,
            title="Task 2",
            prompt="Prompt 2",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add_all([task1, task2])
        db_session.commit()

        # Poll and claim
        executions = poll_and_claim_tasks(db_session, "runner-1", batch_size=2)

        assert len(executions) == 2
        assert all(e.runner_id == "runner-1" for e in executions)
        assert all(e.status == ExecutionStatus.QUEUED.value for e in executions)

    def test_poll_respects_batch_size(self, db_session: Session):
        """Test that polling respects batch_size limit."""
        # Create 5 prepared tasks
        tasks = []
        for i in range(5):
            task = Task(
                task_number=i + 10,
                title=f"Task {i}",
                prompt=f"Prompt {i}",
                type="execution",
                status=TaskStatus.PREPARED.value,
                max_retries=3,
                created_by_type="agent",
                created_by_ref="test",
            )
            tasks.append(task)
        db_session.add_all(tasks)
        db_session.commit()

        # Poll with batch_size=2
        executions = poll_and_claim_tasks(db_session, "runner-1", batch_size=2)

        assert len(executions) == 2

    def test_poll_handles_already_claimed_tasks(self, db_session: Session):
        """Test that polling gracefully handles already claimed tasks."""
        # Create prepared tasks
        task1 = Task(
            task_number=15,
            title="Task 1",
            prompt="Prompt 1",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        task2 = Task(
            task_number=16,
            title="Task 2",
            prompt="Prompt 2",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add_all([task1, task2])
        db_session.commit()

        # Runner 1 claims task1
        claim_task(db_session, task1.id, "runner-1")

        # Runner 2 polls (should only claim task2)
        executions = poll_and_claim_tasks(db_session, "runner-2", batch_size=2)

        assert len(executions) == 1
        assert executions[0].task_id == task2.id


class TestRunnerIdPersistence:
    """Test runner ID generation and persistence."""

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite database session."""
        engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def test_runner_id_is_persisted_in_execution(self, db_session: Session):
        """Test that runner ID is persisted in TaskExecution."""
        task = Task(
            task_number=17,
            title="Test Task",
            prompt="Test prompt",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add(task)
        db_session.commit()

        execution = claim_task(db_session, task.id, "test-runner-123")

        assert execution.runner_id == "test-runner-123"

    def test_different_runners_have_different_ids(self, db_session: Session):
        """Test that different runners have different IDs."""
        task1 = Task(
            task_number=18,
            title="Task 1",
            prompt="Prompt 1",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        task2 = Task(
            task_number=19,
            title="Task 2",
            prompt="Prompt 2",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
        )
        db_session.add_all([task1, task2])
        db_session.commit()

        execution1 = claim_task(db_session, task1.id, "runner-A")
        execution2 = claim_task(db_session, task2.id, "runner-B")

        assert execution1.runner_id != execution2.runner_id
