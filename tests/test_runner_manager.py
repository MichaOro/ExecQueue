"""Tests for runner manager."""

from __future__ import annotations

import pytest
import asyncio
from uuid import uuid4

from execqueue.orchestrator.workflow_models import WorkflowContext
from execqueue.orchestrator.runner_manager import RunnerManager, RunnerHandle


class MockRunner:
    """Mock runner for testing."""
    
    def __init__(self, ctx: WorkflowContext, runner_uuid: str):
        self.ctx = ctx
        self.runner_uuid = runner_uuid
        self.ran = False
    
    async def run(self):
        """Mock run that sets flag."""
        self.ran = True
        await asyncio.sleep(0.1)


class TestRunnerHandle:
    """Tests for RunnerHandle dataclass."""

    def test_runner_handle_creation(self):
        """Test RunnerHandle creation."""
        workflow_id = uuid4()
        handle = RunnerHandle(
            runner_uuid="runner-123",
            workflow_id=workflow_id,
            task=None,
        )
        
        assert handle.runner_uuid == "runner-123"
        assert handle.workflow_id == workflow_id
        assert handle.task is None


class TestRunnerManager:
    """Tests for RunnerManager."""

    @pytest.mark.asyncio
    async def test_start_runner_for_context(self):
        """Test starting a runner for context."""
        manager = RunnerManager()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        
        handle = manager.start_runner_for_context(ctx)
        
        assert handle.runner_uuid is not None
        assert handle.workflow_id == ctx.workflow_id
        assert handle.task is not None
        
        # Verify mapping
        assert manager.get_runner_handle(ctx.workflow_id) == handle
        assert manager.get_workflow_id(handle.runner_uuid) == ctx.workflow_id

    @pytest.mark.asyncio
    async def test_start_runner_for_context_with_mock_runner(self):
        """Test starting a runner with custom runner class."""
        manager = RunnerManager()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        
        handle = manager.start_runner_for_context(ctx, runner_class=MockRunner)
        
        assert handle.runner_uuid is not None
        assert handle.workflow_id == ctx.workflow_id
        
        # Wait for runner to complete
        await asyncio.sleep(0.15)
        
        # Verify mapping
        assert manager.get_runner_handle(ctx.workflow_id) == handle

    @pytest.mark.asyncio
    async def test_get_runner_handle_not_found(self):
        """Test getting non-existent runner handle."""
        manager = RunnerManager()
        
        handle = manager.get_runner_handle(uuid4())
        
        assert handle is None

    @pytest.mark.asyncio
    async def test_get_workflow_id_not_found(self):
        """Test getting workflow ID for non-existent runner."""
        manager = RunnerManager()
        
        workflow_id = manager.get_workflow_id("non-existent-runner")
        
        assert workflow_id is None

    @pytest.mark.asyncio
    async def test_stop_runner(self):
        """Test stopping a runner."""
        manager = RunnerManager()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        
        handle = manager.start_runner_for_context(ctx)
        runner_uuid = handle.runner_uuid
        workflow_id = ctx.workflow_id
        
        # Verify exists
        assert manager.get_runner_handle(workflow_id) is not None
        
        # Stop runner
        await manager.stop_runner(runner_uuid)
        
        # Verify removed
        assert manager.get_runner_handle(workflow_id) is None
        assert manager.get_workflow_id(runner_uuid) is None

    @pytest.mark.asyncio
    async def test_stop_nonexistent_runner(self):
        """Test stopping non-existent runner."""
        manager = RunnerManager()
        
        # Should not raise
        await manager.stop_runner("non-existent")

    @pytest.mark.asyncio
    async def test_get_all_handles(self):
        """Test getting all runner handles."""
        manager = RunnerManager()
        ctx1 = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        ctx2 = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        
        handle1 = manager.start_runner_for_context(ctx1)
        handle2 = manager.start_runner_for_context(ctx2)
        
        handles = manager.get_all_handles()
        
        assert len(handles) == 2
        assert handle1 in handles
        assert handle2 in handles

    @pytest.mark.asyncio
    async def test_get_active_count(self):
        """Test getting active runner count."""
        manager = RunnerManager()
        ctx1 = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        ctx2 = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        
        assert manager.get_active_count() == 0
        
        manager.start_runner_for_context(ctx1)
        assert manager.get_active_count() == 1
        
        manager.start_runner_for_context(ctx2)
        assert manager.get_active_count() == 2
        
        # Stop one
        handle = manager.get_runner_handle(ctx1.workflow_id)
        await manager.stop_runner(handle.runner_uuid)
        assert manager.get_active_count() == 1

    @pytest.mark.asyncio
    async def test_runner_handle_contains_task(self):
        """Test that runner handle contains asyncio task."""
        manager = RunnerManager()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=None,
            tasks=[],
            dependencies={},
        )
        
        handle = manager.start_runner_for_context(ctx)
        
        assert handle.task is not None
        assert isinstance(handle.task, asyncio.Task)
