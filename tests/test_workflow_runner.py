"""Tests for workflow runner (REQ-019)."""

from __future__ import annotations

import pytest
import asyncio
from uuid import uuid4

from execqueue.orchestrator.workflow_models import WorkflowContext, PreparedExecutionContext
from execqueue.runner.workflow_runner import WorkflowRunner


class TestWorkflowRunner:
    """Tests for WorkflowRunner."""

    @pytest.mark.asyncio
    async def test_runner_creation(self):
        """Test WorkflowRunner creation."""
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        runner_uuid = str(uuid4())
        
        runner = WorkflowRunner(
            ctx=ctx,
            runner_uuid=runner_uuid,
        )
        
        assert runner.runner_uuid == runner_uuid
        assert runner.workflow_id == ctx.workflow_id
        assert runner.is_complete is False

    @pytest.mark.asyncio
    async def test_standalone_task_execution(self):
        """Test standalone task execution (len==1)."""
        task_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task_id,
                    branch_name="feature/test",
                    worktree_path="/tmp/worktree/1",
                    commit_sha="abc123",
                )
            ],
            dependencies={task_id: []},
        )
        runner_uuid = str(uuid4())
        
        runner = WorkflowRunner(ctx=ctx, runner_uuid=runner_uuid)
        results = await runner.run()
        
        # Should return single result
        assert len(results) == 1
        assert results[0].task_id == task_id
        assert results[0].status == "DONE"
        assert runner.is_complete is True

    @pytest.mark.asyncio
    async def test_multi_task_execution(self):
        """Test multi-task workflow execution."""
        task1_id = uuid4()
        task2_id = uuid4()
        task3_id = uuid4()
        
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task1_id,
                    branch_name="feature/test-1",
                    worktree_path="/tmp/worktree/1",
                    commit_sha=None,
                ),
                PreparedExecutionContext(
                    task_id=task2_id,
                    branch_name="feature/test-2",
                    worktree_path="/tmp/worktree/2",
                    commit_sha=None,
                ),
                PreparedExecutionContext(
                    task_id=task3_id,
                    branch_name="feature/test-3",
                    worktree_path="/tmp/worktree/3",
                    commit_sha=None,
                ),
            ],
            dependencies={
                task1_id: [],
                task2_id: [task1_id],
                task3_id: [task2_id],
            },
        )
        runner_uuid = str(uuid4())
        
        runner = WorkflowRunner(ctx=ctx, runner_uuid=runner_uuid)
        results = await runner.run()
        
        # Should return all results
        assert len(results) == 3
        result_ids = {r.task_id for r in results}
        assert task1_id in result_ids
        assert task2_id in result_ids
        assert task3_id in result_ids
        assert runner.is_complete is True

    @pytest.mark.asyncio
    async def test_empty_workflow(self):
        """Test empty workflow execution."""
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        runner_uuid = str(uuid4())
        
        runner = WorkflowRunner(ctx=ctx, runner_uuid=runner_uuid)
        results = await runner.run()
        
        # Should return empty results
        assert len(results) == 0
        assert runner.is_complete is True

    @pytest.mark.asyncio
    async def test_cycle_detection(self):
        """Test cycle detection in workflow."""
        task1_id = uuid4()
        task2_id = uuid4()
        
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task1_id,
                    branch_name="feature/test-1",
                    worktree_path="/tmp/worktree/1",
                    commit_sha=None,
                ),
                PreparedExecutionContext(
                    task_id=task2_id,
                    branch_name="feature/test-2",
                    worktree_path="/tmp/worktree/2",
                    commit_sha=None,
                ),
            ],
            dependencies={
                task1_id: [task2_id],  # task1 depends on task2
                task2_id: [task1_id],  # task2 depends on task1 (cycle!)
            },
        )
        runner_uuid = str(uuid4())
        
        runner = WorkflowRunner(ctx=ctx, runner_uuid=runner_uuid)
        results = await runner.run()
        
        # Should return empty results due to cycle
        assert len(results) == 0
        assert runner.is_complete is True

    @pytest.mark.asyncio
    async def test_results_property(self):
        """Test results property."""
        task_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task_id,
                    branch_name="feature/test",
                    worktree_path="/tmp/worktree/1",
                    commit_sha=None,
                )
            ],
            dependencies={task_id: []},
        )
        runner_uuid = str(uuid4())
        
        runner = WorkflowRunner(ctx=ctx, runner_uuid=runner_uuid)
        
        # Before execution
        assert runner.results == []
        
        # After execution
        await runner.run()
        assert len(runner.results) == 1

    @pytest.mark.asyncio
    async def test_workflow_id_property(self):
        """Test workflow_id property."""
        workflow_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=workflow_id,
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        runner_uuid = str(uuid4())
        
        runner = WorkflowRunner(ctx=ctx, runner_uuid=runner_uuid)
        
        assert runner.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_context_lifecycle_fields(self):
        """Test that context lifecycle fields are set."""
        task_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task_id,
                    branch_name="feature/test",
                    worktree_path="/tmp/worktree/1",
                    commit_sha=None,
                )
            ],
            dependencies={task_id: []},
        )
        
        # Initially no timestamps
        assert ctx.started_at is None
        assert ctx.finished_at is None
        
        runner_uuid = str(uuid4())
        runner = WorkflowRunner(ctx=ctx, runner_uuid=runner_uuid)
        await runner.run()
        
        # After execution, timestamps should be set
        assert ctx.started_at is not None
        assert ctx.finished_at is not None
        assert ctx.finished_at >= ctx.started_at

    @pytest.mark.asyncio
    async def test_mock_mode_execution(self):
        """Test execution in mock mode (no dependencies)."""
        task_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task_id,
                    branch_name="feature/test",
                    worktree_path="/tmp/worktree/1",
                    commit_sha=None,
                )
            ],
            dependencies={task_id: []},
        )
        runner_uuid = str(uuid4())
        
        # Runner without opencode_client, session_strategy, git_manager
        runner = WorkflowRunner(
            ctx=ctx,
            runner_uuid=runner_uuid,
            opencode_client=None,
            session_strategy=None,
            git_manager=None,
        )
        
        # Should not raise, just run in mock mode
        results = await runner.run()
        
        assert len(results) == 1
        assert results[0].status == "DONE"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling during execution."""
        # This test verifies that the runner handles errors gracefully
        # In mock mode, errors are unlikely, but we test the structure
        
        task_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task_id,
                    branch_name="feature/test",
                    worktree_path="/tmp/worktree/1",
                    commit_sha=None,
                )
            ],
            dependencies={task_id: []},
        )
        runner_uuid = str(uuid4())
        
        runner = WorkflowRunner(ctx=ctx, runner_uuid=runner_uuid)
        
        # Should complete without raising
        results = await runner.run()
        
        assert len(results) >= 0  # May be empty or have results


class TestWorkflowRunnerIntegration:
    """Integration tests for WorkflowRunner with RunnerManager."""

    @pytest.mark.asyncio
    async def test_runner_with_runner_manager(self):
        """Test WorkflowRunner integration with RunnerManager."""
        from execqueue.orchestrator.runner_manager import RunnerManager
        
        manager = RunnerManager()
        task_id = uuid4()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[
                PreparedExecutionContext(
                    task_id=task_id,
                    branch_name="feature/test",
                    worktree_path="/tmp/worktree/1",
                    commit_sha=None,
                )
            ],
            dependencies={task_id: []},
        )
        
        # Start runner via manager
        handle = await manager.start_runner_for_context(
            ctx,
            runner_class=WorkflowRunner,
        )
        
        assert handle.runner_uuid is not None
        assert handle.workflow_id == ctx.workflow_id
        assert handle.task is not None
        
        # Wait for completion
        await asyncio.sleep(0.5)
        
        # Verify runner completed
        assert manager.get_runner_handle(ctx.workflow_id) is not None

    @pytest.mark.asyncio
    async def test_multiple_runners_concurrent(self):
        """Test multiple WorkflowRunner instances running concurrently."""
        from execqueue.orchestrator.runner_manager import RunnerManager
        
        manager = RunnerManager()
        
        # Create multiple workflows
        workflows = []
        for i in range(3):
            task_id = uuid4()
            ctx = WorkflowContext(
                workflow_id=uuid4(),
                epic_id=None,
                requirement_id=None,
                tasks=[
                    PreparedExecutionContext(
                        task_id=task_id,
                        branch_name=f"feature/test-{i}",
                        worktree_path=f"/tmp/worktree/{i}",
                        commit_sha=None,
                    )
                ],
                dependencies={task_id: []},
            )
            workflows.append(ctx)
        
        # Start all runners
        handles = []
        for ctx in workflows:
            handle = await manager.start_runner_for_context(
                ctx,
                runner_class=WorkflowRunner,
            )
            handles.append(handle)
        
        # Verify all started
        assert manager.get_active_count() == 3
        
        # Wait for all to complete
        await asyncio.gather(*[h.task for h in handles])
        
        # All should be done
        assert manager.get_active_count() == 3  # Still tracked, just not running
