"""Runner manager for REQ-015 workflow execution.

Manages runner instances and workflow-to-runner mappings.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Dict

from execqueue.orchestrator.workflow_models import WorkflowContext


@dataclass
class RunnerHandle:
    """Handle for a started runner.
    
    Attributes:
        runner_uuid: Unique identifier for the runner
        workflow_id: Workflow this runner is executing
        task: asyncio.Task for the runner execution (optional)
    """
    runner_uuid: str
    workflow_id: uuid.UUID
    task: asyncio.Task | None = None


class RunnerManager:
    """Manager for runner instances and workflow mappings.
    
    Handles starting, tracking, and stopping runners for workflows.
    """
    
    def __init__(self):
        """Initialize the runner manager."""
        self._workflow_to_runner: Dict[uuid.UUID, RunnerHandle] = {}
        self._runner_to_workflow: Dict[str, uuid.UUID] = {}
    
    async def start_runner_for_context(
        self,
        ctx: WorkflowContext,
        runner_class: type | None = None,
    ) -> RunnerHandle:
        """Start a runner for the given WorkflowContext.
        
        Args:
            ctx: WorkflowContext to execute
            runner_class: Optional custom runner class (for testing)
            
        Returns:
            RunnerHandle with runner_uuid and workflow_id
        """
        runner_uuid = str(uuid.uuid4())
        
        # Create a mock runner task if no runner_class provided
        # In production, this would be the actual Runner.run() coroutine
        if runner_class is not None:
            runner = runner_class(ctx=ctx, runner_uuid=runner_uuid)
            task = asyncio.create_task(runner.run())
        else:
            # Create a dummy task that does nothing
            async def dummy_run():
                await asyncio.sleep(0)
            task = asyncio.create_task(dummy_run())
        
        handle = RunnerHandle(
            runner_uuid=runner_uuid,
            workflow_id=ctx.workflow_id,
            task=task,
        )
        
        self._workflow_to_runner[ctx.workflow_id] = handle
        self._runner_to_workflow[runner_uuid] = ctx.workflow_id
        
        return handle
    
    def get_runner_handle(self, workflow_id: uuid.UUID) -> RunnerHandle | None:
        """Get runner handle for a workflow.
        
        Args:
            workflow_id: Workflow UUID
            
        Returns:
            RunnerHandle or None if not found
        """
        return self._workflow_to_runner.get(workflow_id)
    
    def get_workflow_id(self, runner_uuid: str) -> uuid.UUID | None:
        """Get workflow ID for a runner.
        
        Args:
            runner_uuid: Runner UUID
            
        Returns:
            Workflow UUID or None if not found
        """
        return self._runner_to_workflow.get(runner_uuid)
    
    async def stop_runner(self, runner_uuid: str) -> None:
        """Stop a running runner and remove the mapping.
        
        Args:
            runner_uuid: Runner UUID to stop
        """
        workflow_id = self._runner_to_workflow.pop(runner_uuid, None)
        if workflow_id:
            handle = self._workflow_to_runner.pop(workflow_id, None)
            if handle and handle.task:
                handle.task.cancel()
                try:
                    await handle.task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    # Ignore other exceptions during cancellation
                    pass
    
    def get_all_handles(self) -> list[RunnerHandle]:
        """Get all active runner handles.
        
        Returns:
            List of all RunnerHandle instances
        """
        return list(self._workflow_to_runner.values())
    
    def get_active_count(self) -> int:
        """Get count of active runners.
        
        Returns:
            Number of active runners
        """
        return len(self._workflow_to_runner)
