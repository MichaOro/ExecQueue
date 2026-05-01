"""Tests for ResultHandler (REQ-016 WP05)."""

from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4

import pytest

from execqueue.runner.result_handler import ResultHandler
from execqueue.runner.workflow_executor import TaskResult


class TestResultHandlerInit:
    """Test ResultHandler initialization."""

    def test_initializes_with_session(self):
        """Test that handler stores the session."""
        mock_session = MagicMock()
        handler = ResultHandler(mock_session)
        
        assert handler._session == mock_session


class TestResultHandlerUpdateExecution:
    """Test ResultHandler._update_execution_from_result()."""

    def test_updates_done_status(self):
        """Test updating execution for DONE result."""
        mock_session = MagicMock()
        handler = ResultHandler(mock_session)
        
        mock_execution = MagicMock()
        mock_execution.status = "pending"
        mock_execution.commit_sha_after = None
        mock_execution.worktree_path = None
        mock_execution.opencode_session_id = None
        mock_execution.error_message = None
        mock_execution.result_summary = None
        
        result = TaskResult(
            task_id=uuid4(),
            status="DONE",
            commit_sha="abc123",
            worktree_path="/tmp/worktree",
            opencode_session_id="session-xyz",
            duration_seconds=10.5,
        )
        
        handler._update_execution_from_result(mock_execution, result)
        
        assert mock_execution.status == "done"
        assert mock_execution.commit_sha_after == "abc123"
        assert mock_execution.worktree_path == "/tmp/worktree"
        assert mock_execution.opencode_session_id == "session-xyz"
        assert mock_execution.result_summary["duration_seconds"] == 10.5

    def test_updates_failed_status(self):
        """Test updating execution for FAILED result."""
        mock_session = MagicMock()
        handler = ResultHandler(mock_session)
        
        mock_execution = MagicMock()
        mock_execution.status = "running"
        
        result = TaskResult(
            task_id=uuid4(),
            status="FAILED",
            error_message="Task failed",
        )
        
        handler._update_execution_from_result(mock_execution, result)
        
        assert mock_execution.status == "failed"
        assert mock_execution.error_message == "Task failed"

    def test_updates_retry_status(self):
        """Test updating execution for RETRY result."""
        mock_session = MagicMock()
        handler = ResultHandler(mock_session)
        
        mock_execution = MagicMock()
        mock_execution.status = "running"
        
        result = TaskResult(
            task_id=uuid4(),
            status="RETRY",
        )
        
        handler._update_execution_from_result(mock_execution, result)
        
        assert mock_execution.status == "prepared"

    def test_only_updates_provided_fields(self):
        """Test that only provided fields are updated."""
        mock_session = MagicMock()
        handler = ResultHandler(mock_session)
        
        mock_execution = MagicMock()
        mock_execution.commit_sha_after = "existing-sha"
        mock_execution.status = "running"
        
        # Result without commit_sha
        result = TaskResult(
            task_id=uuid4(),
            status="DONE",
        )
        
        handler._update_execution_from_result(mock_execution, result)
        
        # Existing commit_sha should be preserved
        assert mock_execution.commit_sha_after == "existing-sha"


class TestResultHandlerLogEvent:
    """Test ResultHandler._log_event()."""

    def test_logs_event_with_data(self):
        """Test logging an event with data."""
        mock_session = MagicMock()
        handler = ResultHandler(mock_session)
        
        mock_execution = MagicMock()
        mock_execution.id = 1
        
        # Mock the TaskExecutionEvent class to avoid SQLAlchemy issues
        mock_event = MagicMock()
        
        with patch('execqueue.runner.result_handler.TaskExecutionEvent', return_value=mock_event):
            data = {"status": "DONE", "duration": 10.5}
            handler._log_event(mock_execution, "task_result", data)
        
        # Verify add was called
        assert mock_session.add.called
        call_args = mock_session.add.call_args[0][0]
        
        assert call_args.task_execution_id == 1
        assert call_args.event_type == "task_result"
        assert call_args.data == data

    def test_logs_event_without_data(self):
        """Test logging an event without data."""
        mock_session = MagicMock()
        handler = ResultHandler(mock_session)
        
        mock_execution = MagicMock()
        mock_execution.id = 1
        
        # Mock the TaskExecutionEvent class
        mock_event = MagicMock()
        
        with patch('execqueue.runner.result_handler.TaskExecutionEvent', return_value=mock_event):
            handler._log_event(mock_execution, "task_started")
        
        call_args = mock_session.add.call_args[0][0]
        assert call_args.data == {}


class TestResultHandlerGetExecution:
    """Test ResultHandler._get_execution()."""

    def test_returns_execution_when_found(self):
        """Test getting execution when it exists."""
        mock_session = MagicMock()
        mock_execution = MagicMock()
        mock_execution.task_id = uuid4()
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_execution
        
        handler = ResultHandler(mock_session)
        
        execution = handler._get_execution(mock_execution.task_id)
        
        assert execution == mock_execution

    def test_returns_none_when_not_found(self):
        """Test getting execution when it doesn't exist."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        handler = ResultHandler(mock_session)
        
        execution = handler._get_execution(uuid4())
        
        assert execution is None


class TestResultHandlerPersistResults:
    """Test ResultHandler.persist_results()."""

    def test_persists_single_result(self):
        """Test persisting a single successful result."""
        mock_session = MagicMock()
        mock_task_execution = MagicMock()
        mock_task_execution.task_id = uuid4()
        mock_task_execution.status = "pending"
        mock_task_execution.result_summary = None
        
        # Setup mock to return the execution
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task_execution
        
        # Mock TaskExecutionEvent to avoid SQLAlchemy issues
        mock_event = MagicMock()
        
        with patch('execqueue.runner.result_handler.TaskExecutionEvent', return_value=mock_event):
            handler = ResultHandler(mock_session)
            
            result = TaskResult(
                task_id=mock_task_execution.task_id,
                status="DONE",
                commit_sha="abc123",
                duration_seconds=10.5,
            )
            
            handler.persist_results(uuid4(), [result])
        
        # Verify execution was updated
        assert mock_task_execution.status == "done"
        assert mock_task_execution.commit_sha_after == "abc123"
        
        # Verify commit was called
        mock_session.commit.assert_called_once()

    def test_persists_multiple_results(self):
        """Test persisting multiple results."""
        mock_session = MagicMock()
        mock_task_execution = MagicMock()
        mock_task_execution.task_id = uuid4()
        mock_task_execution.status = "pending"
        mock_task_execution.result_summary = None
        
        # Setup mock to return the execution for each task
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task_execution
        
        # Mock TaskExecutionEvent
        mock_event = MagicMock()
        
        with patch('execqueue.runner.result_handler.TaskExecutionEvent', return_value=mock_event):
            handler = ResultHandler(mock_session)
            
            results = [
                TaskResult(task_id=uuid4(), status="DONE", duration_seconds=1.0),
                TaskResult(task_id=uuid4(), status="DONE", duration_seconds=2.0),
                TaskResult(task_id=uuid4(), status="FAILED", error_message="Error"),
            ]
            
            handler.persist_results(uuid4(), results)
        
        # Verify commit was called once for all results
        mock_session.commit.assert_called_once()

    def test_handles_missing_task_execution(self, caplog):
        """Test handling of missing TaskExecution."""
        mock_session = MagicMock()
        
        # Setup mock to return None (execution not found)
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        handler = ResultHandler(mock_session)
        
        result = TaskResult(
            task_id=uuid4(),
            status="DONE",
        )
        
        # Should not raise, just log warning
        handler.persist_results(uuid4(), [result])
        
        # Verify commit was not called (no results persisted)
        mock_session.commit.assert_not_called()

    def test_rolls_back_on_error(self):
        """Test that transaction is rolled back on error."""
        mock_session = MagicMock()
        mock_task_execution = MagicMock()
        mock_task_execution.task_id = uuid4()
        mock_task_execution.result_summary = None
        
        # Setup mock to return the execution
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task_execution
        
        # Make commit raise an error
        mock_session.commit.side_effect = Exception("DB error")
        
        # Mock TaskExecutionEvent
        mock_event = MagicMock()
        
        with patch('execqueue.runner.result_handler.TaskExecutionEvent', return_value=mock_event):
            handler = ResultHandler(mock_session)
            
            result = TaskResult(
                task_id=mock_task_execution.task_id,
                status="DONE",
            )
            
            # Should raise the error
            with pytest.raises(Exception, match="DB error"):
                handler.persist_results(uuid4(), [result])
        
        # Verify rollback was called
        mock_session.rollback.assert_called_once()


class TestResultHandlerAggregateWorkflowStatus:
    """Test ResultHandler.aggregate_workflow_status()."""

    def test_returns_failed_if_any_failed(self):
        """Test that failed status is returned if any execution failed."""
        mock_session = MagicMock()
        
        # Setup mock to return executions with one failed
        mock_executions = [
            MagicMock(status="done"),
            MagicMock(status="failed"),
            MagicMock(status="done"),
        ]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_executions
        
        handler = ResultHandler(mock_session)
        
        status = handler.aggregate_workflow_status(uuid4())
        
        assert status == "failed"

    def test_returns_done_if_all_done(self):
        """Test that done status is returned if all executions done."""
        mock_session = MagicMock()
        
        mock_executions = [
            MagicMock(status="done"),
            MagicMock(status="done"),
            MagicMock(status="done"),
        ]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_executions
        
        handler = ResultHandler(mock_session)
        
        status = handler.aggregate_workflow_status(uuid4())
        
        assert status == "done"

    def test_returns_running_if_some_pending(self):
        """Test that running status is returned if some pending."""
        mock_session = MagicMock()
        
        mock_executions = [
            MagicMock(status="done"),
            MagicMock(status="pending"),
            MagicMock(status="done"),
        ]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_executions
        
        handler = ResultHandler(mock_session)
        
        status = handler.aggregate_workflow_status(uuid4())
        
        assert status == "running"

    def test_returns_done_for_empty_workflow(self):
        """Test that done status is returned for empty workflow."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        handler = ResultHandler(mock_session)
        
        status = handler.aggregate_workflow_status(uuid4())
        
        assert status == "done"


class TestResultHandlerIntegration:
    """Integration tests for ResultHandler."""

    def test_full_persist_and_aggregate_workflow(self):
        """Test complete workflow: persist results and aggregate status."""
        mock_session = MagicMock()
        workflow_id = uuid4()
        task_id = uuid4()
        
        # Setup mock execution
        mock_task_execution = MagicMock()
        mock_task_execution.task_id = task_id
        mock_task_execution.workflow_id = workflow_id
        mock_task_execution.status = "pending"
        mock_task_execution.result_summary = None
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task_execution
        
        # Mock TaskExecutionEvent
        mock_event = MagicMock()
        
        with patch('execqueue.runner.result_handler.TaskExecutionEvent', return_value=mock_event):
            handler = ResultHandler(mock_session)
            
            # Persist results
            results = [
                TaskResult(task_id=task_id, status="DONE", duration_seconds=5.0),
            ]
            handler.persist_results(workflow_id, results)
            
            # Verify execution was updated
            assert mock_task_execution.status == "done"
        
        # Setup mock for aggregate_workflow_status
        mock_executions = [MagicMock(status="done")]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_executions
        
        # Aggregate status
        status = handler.aggregate_workflow_status(workflow_id)
        
        assert status == "done"
