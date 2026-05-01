"""Workflow context builder for REQ-015.

Builds and validates WorkflowContext from TaskGroup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from execqueue.db.models import Task
from execqueue.orchestrator.grouping import TaskGroup
from execqueue.orchestrator.workflow_models import (
    PreparedExecutionContext,
    WorkflowContext,
)


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass
class CycleDetectionResult:
    """Result of cycle detection in dependencies."""
    has_cycles: bool
    cycles: list[list[UUID]]
    error_messages: list[str]


class WorkflowContextBuilder:
    """Builder for creating WorkflowContext from TaskGroup.
    
    Handles dependency extraction, cycle detection, and validation.
    """
    
    def __init__(self):
        """Initialize the context builder."""
        pass
    
    def extract_dependencies(
        self,
        tasks: list[Task],
    ) -> dict[UUID, list[UUID]]:
        """Extract dependencies from task details.
        
        Reads depends_on from task.details["depends_on"].
        Handles various input formats (string, list, UUID).
        
        Args:
            tasks: List of tasks to extract dependencies from
            
        Returns:
            Dictionary mapping task_id to list of dependency task_ids
        """
        dependencies: dict[UUID, list[UUID]] = {}
        
        # Build a map of task_id for quick lookup
        task_ids = {task.id for task in tasks}
        
        for task in tasks:
            task_deps: list[UUID] = []
            depends_on = task.details.get("depends_on", [])
            
            # Handle different input formats
            if isinstance(depends_on, str):
                # Single UUID string
                try:
                    dep_id = UUID(depends_on)
                    if dep_id in task_ids:
                        task_deps.append(dep_id)
                except (ValueError, TypeError):
                    pass
            elif isinstance(depends_on, list):
                # List of UUID strings or UUID objects
                for dep in depends_on:
                    try:
                        if isinstance(dep, UUID):
                            dep_id = dep
                        else:
                            dep_id = UUID(dep)
                        if dep_id in task_ids:
                            task_deps.append(dep_id)
                    except (ValueError, TypeError):
                        pass
            
            dependencies[task.id] = task_deps
        
        return dependencies
    
    def detect_cycles(
        self,
        dependencies: dict[UUID, list[UUID]],
    ) -> CycleDetectionResult:
        """Detect cycles in dependencies using DFS.
        
        Args:
            dependencies: Dictionary mapping task_id to dependency list
            
        Returns:
            CycleDetectionResult with cycles found
        """
        cycles: list[list[UUID]] = []
        error_messages: list[str] = []
        
        # States: 0 = unvisited, 1 = in progress, 2 = done
        state: dict[UUID, int] = {task_id: 0 for task_id in dependencies}
        path: list[UUID] = []
        
        def dfs(node: UUID) -> bool:
            """DFS to detect cycles. Returns True if cycle found."""
            if state[node] == 1:
                # Found a cycle - extract it from path
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                error_messages.append(
                    f"Cycle detected: {' -> '.join(str(n) for n in cycle)}"
                )
                return True
            
            if state[node] == 2:
                return False
            
            state[node] = 1
            path.append(node)
            
            for dep in dependencies.get(node, []):
                if dep in state:
                    dfs(dep)
            
            path.pop()
            state[node] = 2
            return False
        
        for task_id in dependencies:
            if state[task_id] == 0:
                dfs(task_id)
        
        return CycleDetectionResult(
            has_cycles=len(cycles) > 0,
            cycles=cycles,
            error_messages=error_messages,
        )
    
    def validate_context(
        self,
        ctx: WorkflowContext,
    ) -> list[str]:
        """Validate a WorkflowContext.
        
        Checks:
        - All task_ids in dependencies are in tasks
        - No cycles in dependencies
        - Required fields are set
        
        Args:
            ctx: WorkflowContext to validate
            
        Returns:
            List of error messages (empty if valid)
        """
        errors: list[str] = []
        
        # Check required fields
        if not ctx.workflow_id:
            errors.append("workflow_id is required")
        
        if not ctx.tasks:
            errors.append("tasks list is required")
        
        # Build set of task IDs from tasks
        task_ids = {task.task_id for task in ctx.tasks}
        
        # Check all dependencies reference valid tasks
        for task_id, deps in ctx.dependencies.items():
            if task_id not in task_ids:
                errors.append(f"Dependency references unknown task: {task_id}")
            for dep_id in deps:
                if dep_id not in task_ids:
                    errors.append(
                        f"Task {task_id} depends on unknown task: {dep_id}"
                    )
        
        # Detect cycles
        if ctx.dependencies:
            cycle_result = self.detect_cycles(ctx.dependencies)
            errors.extend(cycle_result.error_messages)
        
        return errors
    
    def build_context(
        self,
        group: TaskGroup,
        prepared_tasks: list[PreparedExecutionContext] | None = None,
    ) -> WorkflowContext:
        """Build WorkflowContext from TaskGroup.
        
        Args:
            group: TaskGroup to build context from
            prepared_tasks: Optional list of prepared execution contexts.
                          If not provided, creates empty placeholders.
            
        Returns:
            WorkflowContext
        """
        # Extract dependencies
        dependencies = self.extract_dependencies(group.tasks)
        
        # Use provided prepared tasks or create placeholders
        if prepared_tasks is not None:
            tasks = prepared_tasks
        else:
            # Create placeholder contexts for each task
            tasks = [
                PreparedExecutionContext(
                    task_id=task.id,
                    branch_name=task.branch_name or "",
                    worktree_path=task.worktree_path or "",
                    commit_sha=task.commit_sha_before,
                )
                for task in group.tasks
            ]
        
        return WorkflowContext(
            workflow_id=group.group_id,
            epic_id=group.epic_id,
            requirement_id=group.requirement_id,
            tasks=tasks,
            dependencies=dependencies,
            created_at=utcnow(),
        )
