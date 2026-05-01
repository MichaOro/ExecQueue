"""Tests for workflow repository."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4, UUID

from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus
from execqueue.orchestrator.workflow_repo import WorkflowRepository
from execqueue.orchestrator.context_builder import WorkflowContextBuilder
from execqueue.orchestrator.grouping import TaskGroup


def create_mock_task(
    task_id: str | None = None,
    task_number: int = 1,
    details: dict | None = None,
    branch_name: str | None = None,
    worktree_path: str | None = None,
    commit_sha: str | None = None,
):
    """Helper to create mock Task instances."""
    from unittest.mock import MagicMock
    from execqueue.db.models import Task
    from uuid import uuid4, UUID
    
    task = MagicMock(spec=Task)
    task.id = uuid4() if task_id is None else UUID(task_id)
    task.task_number = task_number
    task.details = details or {}
    task.branch_name = branch_name
    task.worktree_path = worktree_path
    task.commit_sha_before = commit_sha
    return task


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock()
    session.get = MagicMock()
    session.add = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    session.execute = MagicMock()
    return session


class TestWorkflowRepository:
    """Tests for WorkflowRepository."""

    def test_create_workflow(self, mock_session):
        """Test creating a new workflow."""
        from execqueue.orchestrator.workflow_models import WorkflowContext
        
        repo = WorkflowRepository()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=uuid4(),
            tasks=[],
            dependencies={},
        )
        
        # Mock the flush to set the id
        created_wf = MagicMock(spec=Workflow)
        created_wf.id = uuid4()
        mock_session.flush = MagicMock()
        
        # Mock session.get to return the created workflow
        mock_session.get = MagicMock(return_value=created_wf)
        
        result = repo.create_workflow(mock_session, ctx)
        
        assert mock_session.add.called
        assert mock_session.flush.called
        assert result is not None

    def test_get_workflow_found(self, mock_session):
        """Test getting an existing workflow."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        expected_wf = MagicMock(spec=Workflow)
        
        mock_session.get = MagicMock(return_value=expected_wf)
        
        result = repo.get_workflow(mock_session, workflow_id)
        
        mock_session.get.assert_called_once_with(Workflow, workflow_id)
        assert result == expected_wf

    def test_get_workflow_not_found(self, mock_session):
        """Test getting a non-existent workflow."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        
        mock_session.get = MagicMock(return_value=None)
        
        result = repo.get_workflow(mock_session, workflow_id)
        
        assert result is None

    def test_update_status(self, mock_session):
        """Test updating workflow status."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        expected_wf = MagicMock(spec=Workflow)
        expected_wf.status = WorkflowStatus.RUNNING.value
        
        mock_session.get = MagicMock(return_value=expected_wf)
        
        repo.update_status(mock_session, workflow_id, WorkflowStatus.DONE)
        
        assert expected_wf.status == WorkflowStatus.DONE.value
        mock_session.commit.assert_called_once()

    def test_update_status_not_found(self, mock_session):
        """Test updating status of non-existent workflow."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        
        mock_session.get = MagicMock(return_value=None)
        
        with pytest.raises(ValueError, match="not found"):
            repo.update_status(mock_session, workflow_id, WorkflowStatus.DONE)

    def test_set_runner_uuid(self, mock_session):
        """Test setting runner_uuid."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        runner_uuid = "runner-123"
        expected_wf = MagicMock(spec=Workflow)
        
        mock_session.get = MagicMock(return_value=expected_wf)
        
        repo.set_runner_uuid(mock_session, workflow_id, runner_uuid)
        
        assert expected_wf.runner_uuid == runner_uuid
        mock_session.commit.assert_called_once()

    def test_set_runner_uuid_not_found(self, mock_session):
        """Test setting runner_uuid on non-existent workflow."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        
        mock_session.get = MagicMock(return_value=None)
        
        # Should not raise, just silently do nothing
        repo.set_runner_uuid(mock_session, workflow_id, "runner-123")
        
        mock_session.commit.assert_not_called()

    def test_get_running_workflows(self, mock_session):
        """Test getting all running workflows."""
        repo = WorkflowRepository()
        
        wf1 = MagicMock(spec=Workflow)
        wf1.status = WorkflowStatus.RUNNING.value
        wf2 = MagicMock(spec=Workflow)
        wf2.status = WorkflowStatus.RUNNING.value
        
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[wf1, wf2])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = MagicMock(return_value=mock_result)
        
        result = repo.get_running_workflows(mock_session)
        
        assert len(result) == 2
        assert result[0] == wf1
        assert result[1] == wf2

    def test_update_workflow(self, mock_session):
        """Test updating workflow fields."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        expected_wf = MagicMock(spec=Workflow)
        expected_wf.status = WorkflowStatus.RUNNING.value
        expected_wf.runner_uuid = None
        
        mock_session.get = MagicMock(return_value=expected_wf)
        
        result = repo.update_workflow(
            mock_session,
            workflow_id,
            status=WorkflowStatus.FAILED.value,
            runner_uuid="new-runner",
        )
        
        assert expected_wf.status == WorkflowStatus.FAILED.value
        assert expected_wf.runner_uuid == "new-runner"
        mock_session.commit.assert_called_once()
        assert result == expected_wf

    def test_update_workflow_not_found(self, mock_session):
        """Test updating non-existent workflow."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        
        mock_session.get = MagicMock(return_value=None)
        
        with pytest.raises(ValueError, match="not found"):
            repo.update_workflow(mock_session, workflow_id, status="done")
