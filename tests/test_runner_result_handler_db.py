"""DB Integration tests for ResultHandler (REQ-016 WP05)."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import TaskExecution, TaskExecutionEvent
from execqueue.runner.result_handler import ResultHandler
from execqueue.runner.workflow_executor import TaskResult


@pytest.fixture
def sqlite_engine():
    """Create an in-memory SQLite engine."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    return engine


@pytest.fixture
def db_session(sqlite_engine):
    """Create a database session."""
    Session = sessionmaker(bind=sqlite_engine)
    session = Session()
    
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def workflow_context():
    """Create workflow context data."""
    return {
        "workflow_id": uuid4(),
        "task_ids": [uuid4(), uuid4(), uuid4()],
    }


@pytest.fixture
def task_executions(db_session, workflow_context):
    """Create TaskExecution records for the workflow."""
    executions = []
    
    for task_id in workflow_context["task_ids"]:
        execution = TaskExecution(
            task_id=task_id,
            workflow_id=workflow_context["workflow_id"],
            status="pending",
        )
        db_session.add(execution)
        executions.append(execution)
    
    db_session.commit()
    
    return executions


class TestResultHandlerDBPersistence:
    """Test ResultHandler with real database."""

    def test_persist_single_result(self, db_session, task_executions, workflow_context):
        """Test persisting a single result to real database."""
        handler = ResultHandler(db_session)
        
        result = TaskResult(
            task_id=task_executions[0].task_id,
            status="DONE",
            commit_sha="abc123def456",
            worktree_path="/tmp/worktree-123",
            opencode_session_id="session-xyz",
            duration_seconds=10.5,
            error_message=None,
        )
        
        handler.persist_results(workflow_context["workflow_id"], [result])
        
        # Verify in database
        execution = db_session.query(TaskExecution).filter(
            TaskExecution.task_id == result.task_id
        ).first()
        
        assert execution is not None
        assert execution.status == "done"
        assert execution.commit_sha_after == "abc123def456"
        assert execution.worktree_path == "/tmp/worktree-123"
        assert execution.opencode_session_id == "session-xyz"
        assert execution.result_summary["duration_seconds"] == 10.5

    def test_persist_multiple_results(self, db_session, task_executions, workflow_context):
        """Test persisting multiple results to real database."""
        handler = ResultHandler(db_session)
        
        results = [
            TaskResult(
                task_id=task_executions[0].task_id,
                status="DONE",
                duration_seconds=5.0,
            ),
            TaskResult(
                task_id=task_executions[1].task_id,
                status="DONE",
                duration_seconds=7.5,
            ),
            TaskResult(
                task_id=task_executions[2].task_id,
                status="FAILED",
                error_message="Task failed due to timeout",
            ),
        ]
        
        handler.persist_results(workflow_context["workflow_id"], results)
        
        # Verify all results in database
        for result in results:
            execution = db_session.query(TaskExecution).filter(
                TaskExecution.task_id == result.task_id
            ).first()
            
            assert execution is not None
            assert execution.status == result.status.lower()
            
            if result.error_message:
                assert execution.error_message == result.error_message

    def test_persist_rolls_back_on_error(self, db_session, task_executions, workflow_context):
        """Test that persist rolls back on database error."""
        # Create handler
        handler = ResultHandler(db_session)
        
        # Create result for non-existent task
        result = TaskResult(
            task_id=uuid4(),  # Not in database
            status="DONE",
        )
        
        # Should not raise, just skip missing executions
        handler.persist_results(workflow_context["workflow_id"], [result])
        
        # No new executions should be created
        count = db_session.query(TaskExecution).count()
        assert count == len(task_executions)

    def test_events_are_logged(self, db_session, task_executions, workflow_context):
        """Test that events are logged to database."""
        handler = ResultHandler(db_session)
        
        result = TaskResult(
            task_id=task_executions[0].task_id,
            status="DONE",
            duration_seconds=10.5,
        )
        
        handler.persist_results(workflow_context["workflow_id"], [result])
        
        # Verify events were created
        events = db_session.query(TaskExecutionEvent).filter(
            TaskExecutionEvent.task_execution_id == task_executions[0].id
        ).all()
        
        assert len(events) >= 1
        
        # Check at least one event has the right type
        event_types = [e.event_type for e in events]
        assert "task_result" in event_types

    def test_aggregate_workflow_status_done(self, db_session, task_executions, workflow_context):
        """Test workflow status aggregation when all done."""
        handler = ResultHandler(db_session)
        
        # Persist all as done
        results = [
            TaskResult(task_id=te.task_id, status="DONE")
            for te in task_executions
        ]
        handler.persist_results(workflow_context["workflow_id"], results)
        
        # Aggregate status
        status = handler.aggregate_workflow_status(workflow_context["workflow_id"])
        
        assert status == "done"

    def test_aggregate_workflow_status_failed(self, db_session, task_executions, workflow_context):
        """Test workflow status aggregation when one failed."""
        handler = ResultHandler(db_session)
        
        # Persist with one failed
        results = [
            TaskResult(task_id=task_executions[0].task_id, status="DONE"),
            TaskResult(task_id=task_executions[1].task_id, status="FAILED", error_message="Error"),
            TaskResult(task_id=task_executions[2].task_id, status="DONE"),
        ]
        handler.persist_results(workflow_context["workflow_id"], results)
        
        # Aggregate status
        status = handler.aggregate_workflow_status(workflow_context["workflow_id"])
        
        assert status == "failed"

    def test_aggregate_workflow_status_running(self, db_session, task_executions, workflow_context):
        """Test workflow status aggregation when some pending."""
        handler = ResultHandler(db_session)
        
        # Persist only some
        results = [
            TaskResult(task_id=task_executions[0].task_id, status="DONE"),
        ]
        handler.persist_results(workflow_context["workflow_id"], results)
        
        # Aggregate status (others still pending)
        status = handler.aggregate_workflow_status(workflow_context["workflow_id"])
        
        assert status == "running"

    def test_transaction_rollback_on_error(self, db_session, task_executions, workflow_context):
        """Test that transaction rollback works correctly."""
        # Manually cause an error by creating invalid data
        handler = ResultHandler(db_session)
        
        # First, persist a valid result
        result = TaskResult(
            task_id=task_executions[0].task_id,
            status="DONE",
        )
        
        # This should succeed
        handler.persist_results(workflow_context["workflow_id"], [result])
        
        # Verify it was persisted
        execution = db_session.query(TaskExecution).filter(
            TaskExecution.task_id == result.task_id
        ).first()
        assert execution.status == "done"

    def test_concurrent_result_persistence(self, db_session, task_executions, workflow_context):
        """Test persisting results in a concurrent-like scenario."""
        handler = ResultHandler(db_session)
        
        # Persist results one by one (simulating concurrent updates)
        for i, te in enumerate(task_executions):
            result = TaskResult(
                task_id=te.task_id,
                status="DONE",
                duration_seconds=float(i + 1),
            )
            handler.persist_results(workflow_context["workflow_id"], [result])
        
        # Verify all results
        for i, te in enumerate(task_executions):
            execution = db_session.query(TaskExecution).filter(
                TaskExecution.task_id == te.task_id
            ).first()
            
            assert execution.status == "done"
            assert execution.result_summary["duration_seconds"] == float(i + 1)


class TestResultHandlerEdgeCases:
    """Test ResultHandler edge cases with real database."""

    def test_persist_empty_results(self, db_session, workflow_context):
        """Test persisting empty results list."""
        handler = ResultHandler(db_session)
        
        # Should not raise
        handler.persist_results(workflow_context["workflow_id"], [])
        
        # No executions should be created or modified
        count = db_session.query(TaskExecution).count()
        assert count == 0

    def test_persist_with_null_fields(self, db_session, workflow_context):
        """Test persisting result with null/None fields."""
        # Create execution
        execution = TaskExecution(
            task_id=uuid4(),
            workflow_id=workflow_context["workflow_id"],
            status="pending",
        )
        db_session.add(execution)
        db_session.commit()
        
        handler = ResultHandler(db_session)
        
        # Result with minimal data
        result = TaskResult(
            task_id=execution.task_id,
            status="DONE",
            commit_sha=None,
            worktree_path=None,
            opencode_session_id=None,
            duration_seconds=None,
            error_message=None,
        )
        
        # Should not raise
        handler.persist_results(workflow_context["workflow_id"], [result])
        
        # Verify execution was updated
        updated = db_session.query(TaskExecution).filter(
            TaskExecution.task_id == execution.task_id
        ).first()
        
        assert updated.status == "done"
        # Other fields should remain None

    def test_persist_retry_status(self, db_session, workflow_context):
        """Test persisting RETRY status."""
        execution = TaskExecution(
            task_id=uuid4(),
            workflow_id=workflow_context["workflow_id"],
            status="running",
        )
        db_session.add(execution)
        db_session.commit()
        
        handler = ResultHandler(db_session)
        
        result = TaskResult(
            task_id=execution.task_id,
            status="RETRY",
        )
        
        handler.persist_results(workflow_context["workflow_id"], [result])
        
        # RETRY should map to "prepared" status
        updated = db_session.query(TaskExecution).filter(
            TaskExecution.task_id == execution.task_id
        ).first()
        
        assert updated.status == "prepared"

    def test_large_result_batch(self, db_session, workflow_context):
        """Test persisting a large batch of results."""
        # Create many executions
        num_tasks = 50
        task_ids = [uuid4() for _ in range(num_tasks)]
        
        for task_id in task_ids:
            execution = TaskExecution(
                task_id=task_id,
                workflow_id=workflow_context["workflow_id"],
                status="pending",
            )
            db_session.add(execution)
        
        db_session.commit()
        
        handler = ResultHandler(db_session)
        
        # Create results
        results = [
            TaskResult(task_id=task_id, status="DONE", duration_seconds=1.0)
            for task_id in task_ids
        ]
        
        # Should handle large batch
        handler.persist_results(workflow_context["workflow_id"], results)
        
        # Verify all persisted
        count = db_session.query(TaskExecution).filter(
            TaskExecution.workflow_id == workflow_context["workflow_id"]
        ).filter(TaskExecution.status == "done").count()
        
        assert count == num_tasks
