"""Tests for WorkflowExecutor ExecutionChain integration."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from execqueue.orchestrator.workflow_models import WorkflowContext, PreparedExecutionContext
from execqueue.runner.workflow_executor import WorkflowExecutor, TaskResult
from execqueue.runner.graph import DependencyGraph
from execqueue.runner.session_strategy import HybridSessionStrategy, SessionPlan
from execqueue.opencode.client import OpenCodeClient
from execqueue.runner.git_workflow import GitWorkflowManager


class TestWorkflowExecutorExecutionChainIntegration:
    """Tests for ExecutionChain integration in WorkflowExecutor."""

    @pytest.fixture
    def mock_opencode_client(self):
        """Create a mock OpenCode client."""
        return AsyncMock(spec=OpenCodeClient)

    @pytest.fixture
    def mock_session_strategy(self):
        """Create a mock session strategy."""
        strategy = AsyncMock(spec=HybridSessionStrategy)
        # Configure mock session plan
        mock_plan = MagicMock(spec=SessionPlan)
        mock_plan.get_session_for_task.return_value = "test-session-123"
        strategy.create_plan.return_value = mock_plan
        strategy.create_sessions = AsyncMock(return_value=mock_plan)
        strategy.cleanup_sessions = AsyncMock()
        return strategy

    @pytest.fixture
    def mock_git_manager(self):
        """Create a mock Git workflow manager."""
        return AsyncMock(spec=GitWorkflowManager)

    @pytest.fixture
    def workflow_executor(self, mock_opencode_client, mock_session_strategy, mock_git_manager):
        """Create a WorkflowExecutor instance with mocks."""
        return WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=mock_session_strategy,
            git_manager=mock_git_manager,
        )

    @pytest.mark.asyncio
    async def test_execute_task_calls_do_execute_task(
        self, workflow_executor, mock_session_strategy
    ):
        """Test that tasks are executed using the _do_execute_task method."""
        task_id = uuid4()
        workflow_id = uuid4()
        
        # Create workflow context
        ctx = WorkflowContext(
            workflow_id=workflow_id,
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task_id,
                    branch_name="feature/test",
                    worktree_path="/tmp/worktree/test",
                    commit_sha="abc123",
                )
            ],
            dependencies={task_id: []},
        )
        
        # Create dependency graph
        graph = DependencyGraph(
            nodes={task_id},
            edges={task_id: []},
        )
        
        # Execute workflow
        with patch.object(workflow_executor, '_do_execute_task') as mock_do_execute:
            # Configure mock to return a successful result
            mock_result = TaskResult(
                task_id=task_id,
                status="DONE",
                worktree_path="/tmp/worktree/test",
                duration_seconds=1.0,
            )
            mock_do_execute.return_value = mock_result
            
            results = await workflow_executor.execute(ctx, graph)
        
        # Verify results
        assert len(results) == 1
        assert isinstance(results[0], TaskResult)
        assert results[0].task_id == task_id
        assert results[0].status == "DONE"
        
        # Verify session management was called
        mock_session_strategy.create_sessions.assert_called_once()
        mock_session_strategy.cleanup_sessions.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_multiple_tasks_calls_do_execute_task_multiple_times(
        self, workflow_executor, mock_session_strategy
    ):
        """Test that multiple tasks call _do_execute_task multiple times."""
        task1_id = uuid4()
        task2_id = uuid4()
        workflow_id = uuid4()
        
        # Create workflow context
        ctx = WorkflowContext(
            workflow_id=workflow_id,
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task1_id,
                    branch_name="feature/test-1",
                    worktree_path="/tmp/worktree/test-1",
                    commit_sha="abc123",
                ),
                PreparedExecutionContext(
                    task_id=task2_id,
                    branch_name="feature/test-2",
                    worktree_path="/tmp/worktree/test-2",
                    commit_sha="def456",
                )
            ],
            dependencies={task1_id: [], task2_id: []},
        )
        
        # Create dependency graph
        graph = DependencyGraph(
            nodes={task1_id, task2_id},
            edges={task1_id: [], task2_id: []},
        )
        
        # Execute workflow
        with patch.object(workflow_executor, '_do_execute_task') as mock_do_execute:
            # Configure mock to return successful results
            mock_result1 = TaskResult(
                task_id=task1_id,
                status="DONE",
                worktree_path="/tmp/worktree/test-1",
                duration_seconds=1.0,
            )
            mock_result2 = TaskResult(
                task_id=task2_id,
                status="DONE",
                worktree_path="/tmp/worktree/test-2",
                duration_seconds=1.0,
            )
            mock_do_execute.side_effect = [mock_result1, mock_result2]
            
            results = await workflow_executor.execute(ctx, graph)
        
        # Verify results
        assert len(results) == 2
        task_ids = {result.task_id for result in results}
        assert task1_id in task_ids
        assert task2_id in task_ids
        assert all(result.status == "DONE" for result in results)
        
        # Verify _do_execute_task was called twice
        assert mock_do_execute.call_count == 2
        
        # Verify session management was called
        mock_session_strategy.create_sessions.assert_called_once()
        mock_session_strategy.cleanup_sessions.assert_called_once()