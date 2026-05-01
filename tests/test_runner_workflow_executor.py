"""Tests for WorkflowExecutor (REQ-016 WP03)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from execqueue.runner.graph import DependencyGraph
from execqueue.runner.git_workflow import GitWorkflowManager
from execqueue.runner.session_strategy import HybridSessionStrategy, SessionPlan, SessionAssignment
from execqueue.runner.workflow_executor import (
    WorkflowExecutor,
    TaskResult,
    BatchResult,
)
from execqueue.orchestrator.workflow_models import WorkflowContext


@pytest.fixture
def mock_opencode_client():
    """Create a mock OpenCode client."""
    client = AsyncMock()
    
    async def mock_create_session(name: str):
        session = MagicMock()
        session.id = f"session-{name}-xyz"
        return session
    
    client.create_session = mock_create_session
    client.close_session = AsyncMock()
    
    return client


@pytest.fixture
def mock_session_strategy():
    """Create a mock session strategy."""
    strategy = AsyncMock(spec=HybridSessionStrategy)
    
    # Default session plan
    def create_plan(sequential_paths, all_task_ids):
        plan = SessionPlan()
        for path in sequential_paths:
            plan.assignments.append(
                SessionAssignment(
                    session_id=f"seq-session",
                    task_ids=path,
                    is_sequential=True,
                )
            )
        return plan
    
    strategy.create_plan = create_plan
    strategy.create_sessions = AsyncMock(side_effect=lambda plan: plan)
    strategy.cleanup_sessions = AsyncMock()
    
    return strategy


@pytest.fixture
def mock_git_manager():
    """Create a mock GitWorkflowManager."""
    manager = AsyncMock(spec=GitWorkflowManager)
    return manager


@pytest.fixture
def sample_workflow_context():
    """Create a sample WorkflowContext."""
    task1_id = uuid4()
    task2_id = uuid4()
    
    # Create minimal task contexts
    task1 = MagicMock()
    task1.task_id = task1_id
    task1.branch_name = "main"
    task1.worktree_path = "/tmp/worktree1"
    task1.commit_sha = None
    
    task2 = MagicMock()
    task2.task_id = task2_id
    task2.branch_name = "main"
    task2.worktree_path = "/tmp/worktree2"
    task2.commit_sha = None
    
    ctx = WorkflowContext(
        workflow_id=uuid4(),
        epic_id=None,
        requirement_id=None,
        tasks=[task1, task2],  # type: ignore
        dependencies={task1_id: [], task2_id: [task1_id]},
        created_at=None,  # type: ignore
    )
    
    return ctx


@pytest.fixture
def sample_dependency_graph(sample_workflow_context):
    """Create a sample DependencyGraph."""
    return DependencyGraph.from_context(sample_workflow_context)


class TestTaskResult:
    """Test TaskResult dataclass."""

    def test_successful_result(self):
        """Test successful task result."""
        result = TaskResult(
            task_id=uuid4(),
            status="DONE",
            commit_sha="abc123",
            duration_seconds=10.5,
        )
        
        assert result.status == "DONE"
        assert result.commit_sha == "abc123"
        assert result.duration_seconds == 10.5
        assert result.error_message is None

    def test_failed_result(self):
        """Test failed task result."""
        task_id = uuid4()
        result = TaskResult(
            task_id=task_id,
            status="FAILED",
            error_message="Task failed due to timeout",
        )
        
        assert result.status == "FAILED"
        assert result.error_message == "Task failed due to timeout"


class TestBatchResult:
    """Test BatchResult dataclass."""

    def test_successful_batch(self):
        """Test batch with all successful tasks."""
        results = [
            TaskResult(task_id=uuid4(), status="DONE"),
            TaskResult(task_id=uuid4(), status="DONE"),
        ]
        batch = BatchResult(batch_index=0, task_results=results)
        
        assert batch.success is True

    def test_failed_batch(self):
        """Test batch with at least one failed task."""
        results = [
            TaskResult(task_id=uuid4(), status="DONE"),
            TaskResult(task_id=uuid4(), status="FAILED", error_message="Error"),
        ]
        batch = BatchResult(batch_index=0, task_results=results)
        
        assert batch.success is False

    def test_empty_batch(self):
        """Test empty batch is considered successful."""
        batch = BatchResult(batch_index=0, task_results=[])
        
        assert batch.success is True


class TestWorkflowExecutorInit:
    """Test WorkflowExecutor initialization."""

    def test_default_timeouts(self, mock_opencode_client, mock_session_strategy, mock_git_manager):
        """Test default timeout values."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        assert executor._task_timeout == 300
        assert executor._batch_timeout == 600

    def test_custom_timeouts(self, mock_opencode_client, mock_session_strategy, mock_git_manager):
        """Test custom timeout values."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
            task_timeout_seconds=600,
            batch_timeout_seconds=1200,
        )
        
        assert executor._task_timeout == 600
        assert executor._batch_timeout == 1200


class TestWorkflowExecutorExecute:
    """Test WorkflowExecutor.execute()."""

    @pytest.mark.asyncio
    async def test_empty_workflow_returns_empty_results(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager
    ):
        """Test that empty workflow returns empty results."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        # Create empty context
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
            created_at=None,  # type: ignore
        )
        graph = DependencyGraph()
        
        results = await executor.execute(ctx, graph)
        
        assert results == []

    @pytest.mark.asyncio
    async def test_cycle_detection_returns_empty(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager
    ):
        """Test that cycle detection returns empty results."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        # Create graph with cycle
        a, b = uuid4(), uuid4()
        graph = DependencyGraph(
            nodes={a, b},
            edges={a: [b], b: [a]},  # Cycle: A -> B -> A
        )
        
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={a: [b], b: [a]},
            created_at=None,  # type: ignore
        )
        
        results = await executor.execute(ctx, graph)
        
        assert results == []
        # No sessions should be created when cycle is detected (early exit)
        mock_session_strategy.create_sessions.assert_not_called()
        mock_session_strategy.cleanup_sessions.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_execution(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager,
        sample_workflow_context, sample_dependency_graph
    ):
        """Test successful workflow execution."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        # Mock _do_execute_task to return successful result
        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(
                task_id=task_id,
                status="DONE",
                opencode_session_id=session_id,
                duration_seconds=1.0,
            )
        
        executor._do_execute_task = mock_do_execute_task
        
        results = await executor.execute(sample_workflow_context, sample_dependency_graph)
        
        assert len(results) == 2
        assert all(r.status == "DONE" for r in results)

    @pytest.mark.asyncio
    async def test_session_cleanup_called_on_success(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager,
        sample_workflow_context, sample_dependency_graph
    ):
        """Test that session cleanup is called after successful execution."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(task_id=task_id, status="DONE")
        
        executor._do_execute_task = mock_do_execute_task
        
        await executor.execute(sample_workflow_context, sample_dependency_graph)
        
        mock_session_strategy.cleanup_sessions.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_cleanup_called_on_failure(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager,
        sample_workflow_context, sample_dependency_graph
    ):
        """Test that session cleanup is called even on failure."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        async def mock_do_execute_task_fail(task_id, task_ctx, session_id):
            raise Exception("Task execution failed")
        
        executor._do_execute_task = mock_do_execute_task_fail
        
        results = await executor.execute(sample_workflow_context, sample_dependency_graph)
        
        # Cleanup should still be called
        mock_session_strategy.cleanup_sessions.assert_called_once()
        
        # Results should indicate failure
        assert len(results) == 2
        assert all(r.status == "FAILED" for r in results)


class TestWorkflowExecutorExecuteBatch:
    """Test WorkflowExecutor._execute_batch()."""

    @pytest.mark.asyncio
    async def test_batch_execution_parallel(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager
    ):
        """Test that batch tasks are executed in parallel."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        call_order = []
        
        async def mock_do_execute_task(task_id, task_ctx, session_id):
            call_order.append(task_id)
            return TaskResult(task_id=task_id, status="DONE")
        
        executor._do_execute_task = mock_do_execute_task
        
        # Create task IDs
        task1, task2, task3 = uuid4(), uuid4(), uuid4()
        
        # Create minimal context
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                MagicMock(task_id=task1, branch_name="main", worktree_path="/tmp"),
                MagicMock(task_id=task2, branch_name="main", worktree_path="/tmp"),
                MagicMock(task_id=task3, branch_name="main", worktree_path="/tmp"),
            ],
            dependencies={task1: [], task2: [], task3: []},
            created_at=None,  # type: ignore
        )
        
        # Create session plan
        plan = SessionPlan([
            SessionAssignment(session_id="session-1", task_ids=[task1], is_sequential=False),
            SessionAssignment(session_id="session-2", task_ids=[task2], is_sequential=False),
            SessionAssignment(session_id="session-3", task_ids=[task3], is_sequential=False),
        ])
        
        batch = [task1, task2, task3]
        result = await executor._execute_batch(0, batch, ctx, plan)
        
        assert len(result.task_results) == 3
        assert all(r.status == "DONE" for r in result.task_results)

    @pytest.mark.asyncio
    async def test_batch_handles_exceptions(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager
    ):
        """Test that exceptions in batch tasks are handled gracefully."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        call_count = 0
        
        async def mock_do_execute_task(task_id, task_ctx, session_id):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Task 2 failed")
            return TaskResult(task_id=task_id, status="DONE")
        
        executor._do_execute_task = mock_do_execute_task
        
        task1, task2 = uuid4(), uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                MagicMock(task_id=task1, branch_name="main", worktree_path="/tmp"),
                MagicMock(task_id=task2, branch_name="main", worktree_path="/tmp"),
            ],
            dependencies={task1: [], task2: []},
            created_at=None,  # type: ignore
        )
        
        plan = SessionPlan([
            SessionAssignment(session_id="session-1", task_ids=[task1], is_sequential=False),
            SessionAssignment(session_id="session-2", task_ids=[task2], is_sequential=False),
        ])
        
        result = await executor._execute_batch(0, [task1, task2], ctx, plan)
        
        # One success, one failure
        assert len(result.task_results) == 2
        done_count = sum(1 for r in result.task_results if r.status == "DONE")
        failed_count = sum(1 for r in result.task_results if r.status == "FAILED")
        assert done_count == 1
        assert failed_count == 1


class TestWorkflowExecutorExecuteSingleTask:
    """Test WorkflowExecutor._execute_single_task()."""

    @pytest.mark.asyncio
    async def test_task_without_session_returns_failed(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager
    ):
        """Test that task without session returns FAILED."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        task_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
            created_at=None,  # type: ignore
        )
        plan = SessionPlan()  # Empty plan
        
        result = await executor._execute_single_task(task_id, ctx, plan)
        
        assert result.status == "FAILED"
        assert "No session assigned" in result.error_message

    @pytest.mark.asyncio
    async def test_task_not_in_context_returns_failed(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager
    ):
        """Test that task not in context returns FAILED."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        task_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],  # Empty tasks
            dependencies={task_id: []},
            created_at=None,  # type: ignore
        )
        plan = SessionPlan([
            SessionAssignment(session_id="session-1", task_ids=[task_id], is_sequential=False),
        ])
        
        result = await executor._execute_single_task(task_id, ctx, plan)
        
        assert result.status == "FAILED"
        assert "not found in workflow context" in result.error_message

    @pytest.mark.asyncio
    async def test_task_timeout_returns_failed(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager
    ):
        """Test that task timeout returns FAILED."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
            task_timeout_seconds=1,  # Short timeout for testing
        )
        
        task_id = uuid4()
        task_ctx = MagicMock(task_id=task_id, branch_name="main", worktree_path="/tmp")
        
        async def mock_do_execute_task_slow(task_id, task_ctx, session_id):
            await asyncio.sleep(10)  # Longer than timeout
            return TaskResult(task_id=task_id, status="DONE")
        
        executor._do_execute_task = mock_do_execute_task_slow
        
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[task_ctx],
            dependencies={task_id: []},
            created_at=None,  # type: ignore
        )
        plan = SessionPlan([
            SessionAssignment(session_id="session-1", task_ids=[task_id], is_sequential=False),
        ])
        
        result = await executor._execute_single_task(task_id, ctx, plan)
        
        assert result.status == "FAILED"
        assert "timed out" in result.error_message.lower()


class TestWorkflowExecutorIntegration:
    """Integration tests for WorkflowExecutor."""

    @pytest.mark.asyncio
    async def test_full_workflow_execution(
        self, mock_opencode_client, mock_session_strategy, mock_git_manager
    ):
        """Test complete workflow execution from start to finish."""
        executor = WorkflowExecutor(
            mock_opencode_client,
            mock_session_strategy,
            mock_git_manager,
        )
        
        # Create a 3-task linear workflow: A -> B -> C
        task_a, task_b, task_c = uuid4(), uuid4(), uuid4()
        
        task_a_ctx = MagicMock(task_id=task_a, branch_name="main", worktree_path="/tmp/a")
        task_b_ctx = MagicMock(task_id=task_b, branch_name="main", worktree_path="/tmp/b")
        task_c_ctx = MagicMock(task_id=task_c, branch_name="main", worktree_path="/tmp/c")
        
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[task_a_ctx, task_b_ctx, task_c_ctx],
            dependencies={task_a: [], task_b: [task_a], task_c: [task_b]},
            created_at=None,  # type: ignore
        )
        
        graph = DependencyGraph.from_context(ctx)
        
        # Mock execution to always succeed
        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(
                task_id=task_id,
                status="DONE",
                commit_sha=f"sha-{task_id.hex[:8]}",
                opencode_session_id=session_id,
                duration_seconds=0.1,
            )
        
        executor._do_execute_task = mock_do_execute_task
        
        # Execute workflow
        results = await executor.execute(ctx, graph)
        
        # Verify results
        assert len(results) == 3
        assert all(r.status == "DONE" for r in results)
        
        # Verify all tasks were executed
        result_task_ids = {r.task_id for r in results}
        assert result_task_ids == {task_a, task_b, task_c}
        
        # Verify session cleanup
        mock_session_strategy.cleanup_sessions.assert_called_once()
