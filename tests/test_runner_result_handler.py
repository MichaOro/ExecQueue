from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from execqueue.models.enums import EventDirection
from execqueue.runner.result_handler import ResultHandler
from execqueue.runner.workflow_executor import TaskResult


class TestResultHandlerUpdateExecution:
    def test_updates_done_result_fields(self):
        handler = ResultHandler(MagicMock())
        execution = MagicMock()
        execution.result_summary = None
        execution.commit_sha_after = None

        result = TaskResult(
            task_id=uuid4(),
            status="DONE",
            commit_sha="abc123",
            worktree_path="/tmp/worktree",
            opencode_session_id="sess-1",
            duration_seconds=12.5,
            result_payload={"ok": True},
        )

        handler._update_execution_from_result(execution, result)

        assert execution.status == "done"
        assert execution.commit_sha_after == "abc123"
        assert execution.worktree_path == "/tmp/worktree"
        assert execution.opencode_session_id == "sess-1"
        assert execution.result_summary["duration_seconds"] == 12.5
        assert execution.result_summary["result_payload"] == {"ok": True}
        assert execution.finished_at is not None

    def test_updates_failed_result_fields(self):
        handler = ResultHandler(MagicMock())
        execution = MagicMock()
        execution.result_summary = {}

        result = TaskResult(task_id=uuid4(), status="FAILED", error_message="boom")

        handler._update_execution_from_result(execution, result)

        assert execution.status == "failed"
        assert execution.error_message == "boom"
        assert execution.finished_at is not None

    def test_retry_resets_to_prepared(self):
        handler = ResultHandler(MagicMock())
        execution = MagicMock()
        execution.result_summary = {}

        result = TaskResult(task_id=uuid4(), status="RETRY")

        handler._update_execution_from_result(execution, result)

        assert execution.status == "prepared"
        assert execution.finished_at is None


class TestResultHandlerPersistence:
    def test_skips_commit_when_no_execution_found(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        handler = ResultHandler(session)

        handler.persist_results(uuid4(), [TaskResult(task_id=uuid4(), status="DONE")])

        session.commit.assert_not_called()

    def test_commits_and_updates_workflow_status_when_execution_found(self):
        session = MagicMock()
        execution = MagicMock()
        execution.task_id = uuid4()
        execution.result_summary = None
        execution.workflow_id = None
        execution.id = uuid4()
        execution.correlation_id = "corr-1"
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = execution
        session.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [execution, None]

        handler = ResultHandler(session)
        handler._workflow_repo = MagicMock()

        handler.persist_results(
            uuid4(),
            [TaskResult(task_id=execution.task_id, status="DONE", duration_seconds=1.0)],
        )

        session.commit.assert_called_once()
        handler._workflow_repo.check_and_update_workflow_status.assert_called_once()


class TestResultHandlerLogging:
    def test_log_event_creates_payload_and_sequence(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        handler = ResultHandler(session)

        execution = MagicMock()
        execution.id = uuid4()
        execution.correlation_id = "corr-123"

        handler._log_event(execution, "status_update", {"status": "DONE"})

        added_event = session.add.call_args[0][0]
        assert added_event.task_execution_id == execution.id
        assert added_event.sequence == 1
        assert added_event.direction == EventDirection.OUTBOUND.value
        assert added_event.event_type == "status_update"
        assert added_event.payload == {"status": "DONE"}
        assert added_event.correlation_id == "corr-123"
