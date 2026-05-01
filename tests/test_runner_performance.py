"""Performance tests for REQ-016 workflow execution."""

import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from execqueue.orchestrator.workflow_models import WorkflowContext
from execqueue.runner.graph import DependencyGraph
from execqueue.runner.git_workflow import GitWorkflowManager
from execqueue.runner.session_strategy import HybridSessionStrategy
from execqueue.runner.workflow_executor import WorkflowExecutor, TaskResult


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
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "repo"
        repo_path.mkdir()

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

        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        yield repo_path


class TestDependencyGraphPerformance:
    """Test DependencyGraph performance with large graphs."""

    def test_100_node_graph_topological_sort(self):
        """Test topological sort with 100 nodes completes quickly."""
        import time

        # Create 100 nodes in a chain
        from uuid import uuid4

        nodes = {uuid4() for _ in range(100)}
        node_list = list(nodes)

        edges = {}
        for i, node in enumerate(node_list):
            deps = []
            if i > 0:
                deps.append(node_list[i - 1])
            edges[node] = deps

        graph = DependencyGraph(nodes=nodes, edges=edges)

        start = time.perf_counter()
        batches = graph.topological_sort()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 50, f"Topological sort took {elapsed_ms:.2f}ms (>50ms)"
        assert len(batches) == 100  # All sequential

    def test_500_node_graph_topological_sort(self):
        """Test topological sort with 500 nodes."""
        from uuid import uuid4

        nodes = {uuid4() for _ in range(500)}
        node_list = list(nodes)

        # Create a mix of sequential and parallel
        edges = {}
        for i, node in enumerate(node_list):
            deps = []
            if i > 0 and i % 10 != 0:
                deps.append(node_list[i - 1])
            edges[node] = deps

        graph = DependencyGraph(nodes=nodes, edges=edges)

        start = time.perf_counter()
        batches = graph.topological_sort()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 200, f"Topological sort took {elapsed_ms:.2f}ms (>200ms)"
        assert len(batches) > 0

    def test_1000_node_graph_sequential_paths(self):
        """Test sequential path detection with 1000 nodes."""
        from uuid import uuid4

        nodes = {uuid4() for _ in range(1000)}
        node_list = list(nodes)

        edges = {}
        for i, node in enumerate(node_list):
            deps = []
            if i > 0:
                deps.append(node_list[i - 1])
            edges[node] = deps

        graph = DependencyGraph(nodes=nodes, edges=edges)

        start = time.perf_counter()
        paths = graph.get_sequential_paths()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 300, f"Sequential paths took {elapsed_ms:.2f}ms (>300ms)"
        assert len(paths) > 0


class TestWorkflowExecutorPerformance:
    """Test WorkflowExecutor performance with many tasks."""

    @pytest.mark.asyncio
    async def test_50_parallel_tasks_execution(self, mock_opencode_client, temp_git_repo):
        """Test execution of 50 parallel tasks."""
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)
        session_strategy = HybridSessionStrategy(mock_opencode_client)
        executor = WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=session_strategy,
            git_manager=git_manager,
        )

        # Create 50 parallel tasks
        task_ids = [uuid4() for _ in range(50)]
        tasks = [
            MagicMock(task_id=task_id, branch_name="main", worktree_path=f"/tmp/{i}")
            for i, task_id in enumerate(task_ids)
        ]

        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=tasks,
            dependencies={task_id: [] for task_id in task_ids},
            created_at=None,  # type: ignore
        )

        graph = DependencyGraph.from_context(ctx)

        # Mock fast execution
        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(task_id=task_id, status="DONE", duration_seconds=0.001)

        executor._do_execute_task = mock_do_execute_task

        start = time.perf_counter()
        results = await executor.execute(ctx, graph)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(results) == 50
        assert all(r.status == "DONE" for r in results)
        # Should complete quickly since execution is mocked

    @pytest.mark.asyncio
    async def test_100_task_linear_workflow(self, mock_opencode_client, temp_git_repo):
        """Test execution of 100 tasks in a linear chain."""
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)
        session_strategy = HybridSessionStrategy(mock_opencode_client)
        executor = WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=session_strategy,
            git_manager=git_manager,
        )

        task_ids = [uuid4() for _ in range(100)]
        tasks = [
            MagicMock(task_id=task_id, branch_name="main", worktree_path=f"/tmp/{i}")
            for i, task_id in enumerate(task_ids)
        ]

        # Linear chain: each task depends on the previous
        dependencies = {task_ids[0]: []}
        for i in range(1, len(task_ids)):
            dependencies[task_ids[i]] = [task_ids[i - 1]]

        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=tasks,
            dependencies=dependencies,
            created_at=None,  # type: ignore
        )

        graph = DependencyGraph.from_context(ctx)

        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(task_id=task_id, status="DONE", duration_seconds=0.001)

        executor._do_execute_task = mock_do_execute_task

        start = time.perf_counter()
        results = await executor.execute(ctx, graph)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(results) == 100
        assert all(r.status == "DONE" for r in results)

    @pytest.mark.asyncio
    async def test_mixed_workflow_performance(self, mock_opencode_client, temp_git_repo):
        """Test execution of mixed parallel/sequential workflow."""
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)
        session_strategy = HybridSessionStrategy(mock_opencode_client)
        executor = WorkflowExecutor(
            opencode_client=mock_opencode_client,
            session_strategy=session_strategy,
            git_manager=git_manager,
        )

        # Create a complex workflow:
        # - 10 parallel "root" tasks
        # - Each root has 5 sequential children
        # Total: 10 * 6 = 60 tasks

        all_tasks = []
        dependencies = {}

        for root_idx in range(10):
            root_id = uuid4()
            all_tasks.append(
                MagicMock(
                    task_id=root_id,
                    branch_name="main",
                    worktree_path=f"/tmp/root-{root_idx}",
                )
            )
            dependencies[root_id] = []

            for child_idx in range(5):
                child_id = uuid4()
                all_tasks.append(
                    MagicMock(
                        task_id=child_id,
                        branch_name="main",
                        worktree_path=f"/tmp/root-{root_idx}-child-{child_idx}",
                    )
                )

                # Child depends on previous in chain (or root if first)
                if child_idx == 0:
                    dependencies[child_id] = [root_id]
                else:
                    dependencies[child_id] = [all_tasks[-2].task_id]

        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=all_tasks,
            dependencies=dependencies,
            created_at=None,  # type: ignore
        )

        graph = DependencyGraph.from_context(ctx)

        async def mock_do_execute_task(task_id, task_ctx, session_id):
            return TaskResult(task_id=task_id, status="DONE", duration_seconds=0.001)

        executor._do_execute_task = mock_do_execute_task

        start = time.perf_counter()
        results = await executor.execute(ctx, graph)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(results) == 60
        assert all(r.status == "DONE" for r in results)


class TestSessionStrategyPerformance:
    """Test HybridSessionStrategy performance."""

    def test_create_plan_100_tasks(self):
        """Test session plan creation for 100 tasks."""
        client = AsyncMock()
        strategy = HybridSessionStrategy(client)

        task_ids = [uuid4() for _ in range(100)]

        # Create 10 sequential paths of 5 tasks each (50 tasks in paths)
        # Remaining 50 tasks become parallel
        sequential_paths = [
            task_ids[i * 5 : (i + 1) * 5] for i in range(10)
        ]

        start = time.perf_counter()
        plan = strategy.create_plan(sequential_paths, task_ids)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert plan.sequential_count == 10
        assert plan.parallel_count == 50
        assert elapsed_ms < 10, f"Plan creation took {elapsed_ms:.2f}ms (>10ms)"

    def test_create_plan_all_parallel(self):
        """Test session plan when all tasks are parallel."""
        client = AsyncMock()
        strategy = HybridSessionStrategy(client)

        task_ids = [uuid4() for _ in range(100)]

        start = time.perf_counter()
        plan = strategy.create_plan([], task_ids)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert plan.sequential_count == 0
        assert plan.parallel_count == 100
        assert elapsed_ms < 10


class TestGitWorkflowPerformance:
    """Test GitWorkflowManager performance."""

    @pytest.mark.asyncio
    async def test_create_multiple_worktrees(self, temp_git_repo):
        """Test creating multiple worktrees."""
        git_manager = GitWorkflowManager(base_repo_path=temp_git_repo)

        start = time.perf_counter()

        worktrees = []
        for i in range(10):
            workflow_id = f"workflow-{i}"
            task_id = uuid4()
            branch = f"branch-{i}"

            worktree = await git_manager.create_worktree(workflow_id, task_id, branch)
            worktrees.append(worktree)

        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(worktrees) == 10
        assert all(wt.path.exists() for wt in worktrees)

        # Cleanup
        for wt in worktrees:
            await git_manager.cleanup_worktree(wt.path)
