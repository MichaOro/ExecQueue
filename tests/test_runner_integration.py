"""Integration tests for REQ-016 workflow execution (WP01→WP02→WP03→WP04→WP05)."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import TaskExecution, TaskExecutionEvent
from execqueue.orchestrator.workflow_models import WorkflowContext
from execqueue.runner.graph import DependencyGraph
from execqueue.runner.git_workflow import GitWorkflowManager
from execqueue.runner.result_handler import ResultHandler
from execqueue.runner.session_strategy import HybridSessionStrategy, SessionPlan, SessionAssignment
from execqueue.runner.workflow_executor import WorkflowExecutor, TaskResult


@pytest.fixture
def sqlite_engine():
    """Create an in-memory SQLite engine."""
    engine = create_engine("sqlite:///:memory:", echo=False)
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
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        yield repo_path


@pytest.fixture
def mock_opencode_client():
    """Create a mock OpenCode client."""
    client = AsyncMock()

    async def mock_create_session(name: str):
        session = MagicMock()
        session.id = f"session-{name}-xyz"
        return session

    client.create_session = AsyncMock(side_effect=mock_create_session)
    client.close_session = AsyncMock()

    return client


class TestFullWorkflowIntegration:
    """Test full workflow execution from WP01 to WP05."""

    @pytest.mark.asyncio
    async def test_linear_workflow_execution(
        self, mock_opencode_client, temp_git_repo, db_session
    ):
        """Test complete linear workflow: A -> B -> C."""
        # WP04: Create GitWorkflowManager
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)

        # WP02: Create SessionStrategy
        session_strategy = HybridSessionStrategy(mock_opencode_client)

        # WP03: Create WorkflowExecutor
        executor = WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=session_strategy,
            git_manager=git_manager,
        )

        # Create workflow context with linear dependencies
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

        # WP01: Create DependencyGraph
        graph = DependencyGraph.from_context(ctx)

        # Verify graph structure
        assert len(graph.nodes) == 3
        assert graph.detect_cycles() is False

        # Mock task execution to succeed
        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(
                task_id=task_id,
                status="DONE",
                commit_sha=f"sha-{task_id.hex[:8]}",
                opencode_session_id=session_id,
                duration_seconds=0.1,
            )

        executor._do_execute_task = mock_do_execute_task

        # WP03: Execute workflow
        results = await executor.execute(ctx, graph)

        # Verify execution results
        assert len(results) == 3
        assert all(r.status == "DONE" for r in results)

        # WP05: Create TaskExecution records in DB
        for task in ctx.tasks:
            execution = TaskExecution(
                task_id=task.task_id,
                workflow_id=ctx.workflow_id,
                status="prepared",
            )
            db_session.add(execution)
        db_session.commit()

        # WP05: Persist results
        handler = ResultHandler(db_session)
        handler.persist_results(ctx.workflow_id, results)

        # Verify persistence
        for result in results:
            execution = db_session.query(TaskExecution).filter(
                TaskExecution.task_id == result.task_id
            ).first()
            assert execution is not None
            assert execution.status == "done"
            assert execution.commit_sha_after is not None

        # Verify workflow status aggregation
        status = handler.aggregate_workflow_status(ctx.workflow_id)
        assert status == "done"

    @pytest.mark.asyncio
    async def test_diamond_workflow_execution(
        self, mock_opencode_client, temp_git_repo, db_session
    ):
        """Test diamond workflow: A -> [B, C] -> D."""
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)
        session_strategy = HybridSessionStrategy(mock_opencode_client)
        executor = WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=session_strategy,
            git_manager=git_manager,
        )

        # Create diamond workflow
        task_a, task_b, task_c, task_d = uuid4(), uuid4(), uuid4(), uuid4()

        tasks = [
            MagicMock(task_id=task_a, branch_name="main", worktree_path="/tmp/a"),
            MagicMock(task_id=task_b, branch_name="main", worktree_path="/tmp/b"),
            MagicMock(task_id=task_c, branch_name="main", worktree_path="/tmp/c"),
            MagicMock(task_id=task_d, branch_name="main", worktree_path="/tmp/d"),
        ]

        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=tasks,
            dependencies={
                task_a: [],
                task_b: [task_a],
                task_c: [task_a],
                task_d: [task_b, task_c],
            },
            created_at=None,  # type: ignore
        )

        graph = DependencyGraph.from_context(ctx)

        # Verify diamond structure
        batches = graph.get_parallel_batches()
        assert len(batches) == 3  # [A], [B,C], [D]

        # Mock execution
        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(
                task_id=task_id,
                status="DONE",
                duration_seconds=0.1,
            )

        executor._do_execute_task = mock_do_execute_task

        # Execute
        results = await executor.execute(ctx, graph)

        assert len(results) == 4
        assert all(r.status == "DONE" for r in results)

        # Create DB records and persist
        for task in ctx.tasks:
            execution = TaskExecution(
                task_id=task.task_id,
                workflow_id=ctx.workflow_id,
                status="prepared",
            )
            db_session.add(execution)
        db_session.commit()

        handler = ResultHandler(db_session)
        handler.persist_results(ctx.workflow_id, results)

        status = handler.aggregate_workflow_status(ctx.workflow_id)
        assert status == "done"

    @pytest.mark.asyncio
    async def test_workflow_with_cycle_detection(
        self, mock_opencode_client, temp_git_repo, db_session
    ):
        """Test that cycles are detected and execution is aborted."""
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)
        session_strategy = HybridSessionStrategy(mock_opencode_client)
        executor = WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=session_strategy,
            git_manager=git_manager,
        )

        # Create cyclic dependencies
        task_a, task_b = uuid4(), uuid4()

        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                MagicMock(task_id=task_a, branch_name="main", worktree_path="/tmp/a"),
                MagicMock(task_id=task_b, branch_name="main", worktree_path="/tmp/b"),
            ],
            dependencies={task_a: [task_b], task_b: [task_a]},  # Cycle!
            created_at=None,  # type: ignore
        )

        graph = DependencyGraph.from_context(ctx)

        # Verify cycle is detected
        assert graph.detect_cycles() is True

        # Execute should return empty results
        results = await executor.execute(ctx, graph)

        assert results == []

    @pytest.mark.asyncio
    async def test_workflow_partial_failure_handling(
        self, mock_opencode_client, temp_git_repo, db_session
    ):
        """Test that partial failures are handled correctly."""
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)
        session_strategy = HybridSessionStrategy(mock_opencode_client)
        executor = WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=session_strategy,
            git_manager=git_manager,
        )

        task_a, task_b, task_c = uuid4(), uuid4(), uuid4()

        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                MagicMock(task_id=task_a, branch_name="main", worktree_path="/tmp/a"),
                MagicMock(task_id=task_b, branch_name="main", worktree_path="/tmp/b"),
                MagicMock(task_id=task_c, branch_name="main", worktree_path="/tmp/c"),
            ],
            dependencies={task_a: [], task_b: [], task_c: []},
            created_at=None,  # type: ignore
        )

        graph = DependencyGraph.from_context(ctx)

        # Mock execution with one failure
        call_count = 0

        async def mock_do_execute_task_with_failure(task_id, task_ctx, session_id):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second task fails
                raise Exception("Task failed")
            return TaskResult(task_id=task_id, status="DONE")

        executor._do_execute_task = mock_do_execute_task_with_failure

        results = await executor.execute(ctx, graph)

        # Should have partial results
        assert len(results) == 3
        done_count = sum(1 for r in results if r.status == "DONE")
        failed_count = sum(1 for r in results if r.status == "FAILED")

        assert done_count == 2
        assert failed_count == 1

        # Create DB records
        for task in ctx.tasks:
            execution = TaskExecution(
                task_id=task.task_id,
                workflow_id=ctx.workflow_id,
                status="prepared",
            )
            db_session.add(execution)
        db_session.commit()

        # Persist results
        handler = ResultHandler(db_session)
        handler.persist_results(ctx.workflow_id, results)

        # Workflow status should be failed
        status = handler.aggregate_workflow_status(ctx.workflow_id)
        assert status == "failed"

    @pytest.mark.asyncio
    async def test_session_lifecycle_complete(
        self, mock_opencode_client, temp_git_repo, db_session
    ):
        """Test that sessions are created and cleaned up correctly."""
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)
        session_strategy = HybridSessionStrategy(mock_opencode_client)
        executor = WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=session_strategy,
            git_manager=git_manager,
        )

        task_a, task_b = uuid4(), uuid4()

        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                MagicMock(task_id=task_a, branch_name="main", worktree_path="/tmp/a"),
                MagicMock(task_id=task_b, branch_name="main", worktree_path="/tmp/b"),
            ],
            dependencies={task_a: [], task_b: []},
            created_at=None,  # type: ignore
        )

        graph = DependencyGraph.from_context(ctx)

        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(task_id=task_id, status="DONE")

        executor._do_execute_task = mock_do_execute_task

        # Execute
        await executor.execute(ctx, graph)

        # Verify sessions were created and cleaned up
        assert mock_opencode_client.create_session.call_count == 2
        assert mock_opencode_client.close_session.call_count == 2
