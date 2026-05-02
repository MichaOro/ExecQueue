"""Workflow context builder for REQ-015.

Builds and validates WorkflowContext from TaskGroup.

This module handles:
- Dependency extraction from task.details["depends_on"]
- Cycle detection using DFS with proper visited tracking
- Context validation with structured error reporting
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from execqueue.db.models import Task
from execqueue.orchestrator.exceptions import CycleError, DependencyError, ValidationError
from execqueue.orchestrator.grouping import TaskGroup
from execqueue.orchestrator.workflow_models import (
    PreparedExecutionContext,
    WorkflowContext,
)

logger = logging.getLogger(__name__)


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
        raise_on_error: bool = False,
    ) -> dict[UUID, list[UUID]]:
        """Extract dependencies from task details.
        
        Reads depends_on from task.details["depends_on"].
        Handles various input formats (string, list, UUID).
        
        Args:
            tasks: List of tasks to extract dependencies from
            raise_on_error: If True, raise DependencyError on malformed entries;
                           otherwise log warnings and continue
            
        Returns:
            Dictionary mapping task_id to list of dependency task_ids
            
        Raises:
            DependencyError: If raise_on_error is True and malformed entries are found
        """
        dependencies: dict[UUID, list[UUID]] = {}
        malformed_entries: list[Any] = []
        unknown_dependencies: list[str] = []
        
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
                    else:
                        unknown_dependencies.append(dep_id)
                        malformed_entries.append(f"Unknown dependency {dep_id} for task {task.id}")
                except (ValueError, TypeError) as e:
                    malformed_entries.append(f"Malformed dependency string '{depends_on}' for task {task.id}: {e}")
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
                        else:
                            unknown_dependencies.append(str(dep_id))
                            malformed_entries.append(f"Unknown dependency {dep_id} for task {task.id}")
                    except (ValueError, TypeError) as e:
                        malformed_entries.append(f"Malformed dependency '{dep}' for task {task.id}: {e}")
            elif depends_on is not None:
                # Unexpected type
                malformed_entries.append(f"Unexpected dependency type {type(depends_on)} for task {task.id}")
            
            dependencies[task.id] = task_deps
        
        # Log warnings for malformed entries
        if malformed_entries:
            for entry in malformed_entries:
                logger.warning(entry)
            
            if raise_on_error:
                raise DependencyError(
                    message=f"Found {len(malformed_entries)} malformed dependency entries",
                    workflow_id=None,
                    unknown_dependencies=unknown_dependencies,
                    malformed_entries=malformed_entries,
                )
        
        return dependencies
    
    def detect_cycles(
        self,
        dependencies: dict[UUID, list[UUID]],
        raise_on_cycle: bool = False,
    ) -> CycleDetectionResult:
        """Detect cycles in dependencies using DFS.
        
        This implementation uses a three-color DFS algorithm:
        - WHITE (0): Unvisited node
        - GRAY (1): Node currently being processed (in the recursion stack)
        - BLACK (2): Node and all its descendants have been processed
        
        A back edge to a GRAY node indicates a cycle.
        
        Args:
            dependencies: Dictionary mapping task_id to dependency list
            raise_on_cycle: If True, raise CycleError when cycles are found
            
        Returns:
            CycleDetectionResult with cycles found
            
        Raises:
            CycleError: If raise_on_cycle is True and cycles are detected
        """
        cycles: list[list[UUID]] = []
        error_messages: list[str] = []
        
        # States: 0 = unvisited (WHITE), 1 = in progress (GRAY), 2 = done (BLACK)
        state: dict[UUID, int] = {task_id: 0 for task_id in dependencies}
        path: list[UUID] = []
        
        def dfs(node: UUID) -> bool:
            """DFS to detect cycles. Returns True if cycle found.
            
            IMPORTANT: Node is marked as GRAY (1) BEFORE recursing to prevent
            infinite recursion on self-cycles and to properly detect back edges.
            """
            # Check if node is currently in the recursion stack (GRAY)
            if state[node] == 1:
                # Found a cycle - extract it from path
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                cycle_str = ' -> '.join(str(n) for n in cycle)
                error_msg = f"Cycle detected: {cycle_str}"
                error_messages.append(error_msg)
                logger.warning(error_msg)
                return True  # Short-circuit: cycle found
            
            # Skip if already fully processed (BLACK)
            if state[node] == 2:
                return False
            
            # Mark node as GRAY (in progress) BEFORE recursing
            # This is critical for:
            # 1. Detecting self-cycles (node depends on itself)
            # 2. Short-circuiting when a cycle is found
            state[node] = 1
            path.append(node)
            
            # Visit all dependencies
            for dep in dependencies.get(node, []):
                if dep in state:
                    if dfs(dep):
                        return True  # Short-circuit propagation
            
            # Mark node as BLACK (done) and remove from path
            path.pop()
            state[node] = 2
            return False
        
        # Visit all unvisited nodes
        for task_id in dependencies:
            if state[task_id] == 0:
                if dfs(task_id):
                    # Cycle found and already logged; continue to find all cycles
                    # or return early if only first cycle is needed
                    pass
        
        result = CycleDetectionResult(
            has_cycles=len(cycles) > 0,
            cycles=cycles,
            error_messages=error_messages,
        )
        
        if raise_on_cycle and result.has_cycles:
            raise CycleError(
                message=f"Found {len(cycles)} cycle(s) in task dependencies",
                cycles=[[str(tid) for tid in cycle] for cycle in cycles],
                workflow_id=None,
            )
        
        return result
    
    def validate_context(
        self,
        ctx: WorkflowContext,
        raise_on_error: bool = False,
    ) -> list[str]:
        """Validate a WorkflowContext.
        
        Checks:
        - All task_ids in dependencies are in tasks
        - No cycles in dependencies
        - Required fields are set
        - Every task appears in dependencies map (ensures complete coverage)
        - No unknown dependency references
        
        Args:
            ctx: WorkflowContext to validate
            raise_on_error: If True, raise ValidationError when validation fails
            
        Returns:
            List of error messages (empty if valid)
            
        Raises:
            ValidationError: If raise_on_error is True and validation fails
        """
        errors: list[str] = []
        
        # Check required fields
        if not ctx.workflow_id:
            errors.append("workflow_id is required")
        
        if not ctx.tasks:
            errors.append("tasks list is required")
            if raise_on_error:
                raise ValidationError(
                    message="Validation failed",
                    errors=errors,
                    workflow_id=str(ctx.workflow_id) if ctx.workflow_id else None,
                )
            return errors
        
        # Build set of task IDs from tasks
        task_ids = {task.task_id for task in ctx.tasks}
        
        # Ensure every task appears in dependencies map (complete coverage)
        # This simplifies later processing by guaranteeing all tasks have an entry
        for task in ctx.tasks:
            if task.task_id not in ctx.dependencies:
                errors.append(
                    f"Task {task.task_id} is missing from dependencies map. "
                    "All tasks must have a dependency entry (empty list if no deps)."
                )
        
        # Check all dependencies reference valid tasks
        unknown_deps: list[str] = []
        for task_id, deps in ctx.dependencies.items():
            if task_id not in task_ids:
                errors.append(f"Dependency map contains unknown task: {task_id}")
            for dep_id in deps:
                if dep_id not in task_ids:
                    unknown_deps.append(f"Task {task_id} depends on unknown task: {dep_id}")
        
        if unknown_deps:
            errors.extend(unknown_deps)
        
        # Detect cycles
        if ctx.dependencies:
            cycle_result = self.detect_cycles(ctx.dependencies, raise_on_cycle=False)
            if cycle_result.has_cycles:
                errors.extend(cycle_result.error_messages)
        
        # Raise if validation failed and raise_on_error is True
        if errors and raise_on_error:
            raise ValidationError(
                message=f"Validation failed with {len(errors)} error(s)",
                errors=errors,
                workflow_id=str(ctx.workflow_id) if ctx.workflow_id else None,
            )
        
        return errors
    
    def build_context(
        self,
        group: TaskGroup,
        prepared_tasks: list[PreparedExecutionContext] | None = None,
        ensure_complete_dependencies: bool = True,
    ) -> WorkflowContext:
        """Build WorkflowContext from TaskGroup.
        
        Args:
            group: TaskGroup to build context from
            prepared_tasks: Optional list of prepared execution contexts.
                          If not provided, creates empty placeholders.
            ensure_complete_dependencies: If True, ensures every task has a
                                         dependency entry (empty list if none)
            
        Returns:
            WorkflowContext
        """
        # Extract dependencies
        dependencies = self.extract_dependencies(group.tasks)
        
        # Ensure complete dependency map - every task has an entry
        if ensure_complete_dependencies:
            for task in group.tasks:
                if task.id not in dependencies:
                    logger.debug(
                        "Adding empty dependency entry for task %s",
                        task.id,
                    )
                    dependencies[task.id] = []
        
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
