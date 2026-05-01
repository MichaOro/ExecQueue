"""Task grouping engine for REQ-015 workflow processing.

Implements efficient grouping of tasks by requirement_id, epic_id, or as standalone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from execqueue.db.models import Task


@dataclass(frozen=True)
class TaskGroup:
    """A group of related tasks that form a workflow.
    
    Attributes:
        group_id: requirement_id, epic_id or random-UUID for standalone
        tasks: List of tasks in this group
        group_type: Type of group ("requirement", "epic", "standalone")
        epic_id: Optional Epic ID for standalone workflows
        requirement_id: Optional Requirement ID for epic workflows
    """
    group_id: UUID
    tasks: list[Task]
    group_type: Literal["requirement", "epic", "standalone"]
    epic_id: UUID | None = None
    requirement_id: UUID | None = None


class TaskGroupingEngine:
    """Engine for grouping tasks into workflows.
    
    Groups tasks by priority: requirement_id > epic_id > standalone.
    Algorithm is O(n) using dictionary-based grouping.
    """
    
    def __init__(self):
        """Initialize the grouping engine."""
        pass
    
    def group_by_requirement(
        self,
        tasks: list[Task],
    ) -> dict[UUID, TaskGroup]:
        """Group tasks by requirement_id.
        
        Args:
            tasks: List of tasks to group
            
        Returns:
            Dictionary mapping requirement_id to TaskGroup
        """
        groups: dict[UUID, list[Task]] = {}
        
        for task in tasks:
            if task.requirement_id is None:
                continue
            
            req_id = task.requirement_id
            if req_id not in groups:
                groups[req_id] = []
            groups[req_id].append(task)
        
        return {
            req_id: TaskGroup(
                group_id=req_id,
                tasks=task_list,
                group_type="requirement",
                requirement_id=req_id,
            )
            for req_id, task_list in groups.items()
        }
    
    def group_by_epic(
        self,
        tasks: list[Task],
    ) -> dict[UUID, TaskGroup]:
        """Group tasks by epic_id (from task.details["epic_id"]).
        
        Args:
            tasks: List of tasks to group
            
        Returns:
            Dictionary mapping epic_id to TaskGroup
        """
        groups: dict[UUID, list[Task]] = {}
        
        for task in tasks:
            epic_id_str = task.details.get("epic_id")
            if not epic_id_str:
                continue
            
            try:
                epic_id = UUID(epic_id_str) if isinstance(epic_id_str, str) else epic_id_str
            except (ValueError, TypeError):
                continue
            
            if epic_id not in groups:
                groups[epic_id] = []
            groups[epic_id].append(task)
        
        return {
            epic_id: TaskGroup(
                group_id=epic_id,
                tasks=task_list,
                group_type="epic",
                epic_id=epic_id,
            )
            for epic_id, task_list in groups.items()
        }
    
    def group_standalone(
        self,
        tasks: list[Task],
    ) -> list[TaskGroup]:
        """Group standalone tasks (no requirement_id or epic_id).
        
        Each standalone task gets its own group with a random UUID.
        
        Args:
            tasks: List of tasks to group
            
        Returns:
            List of TaskGroup (one per task)
        """
        groups: list[TaskGroup] = []
        
        for task in tasks:
            if task.requirement_id is not None:
                continue
            
            epic_id_str = task.details.get("epic_id")
            if epic_id_str:
                continue
            
            group_id = uuid4()
            groups.append(TaskGroup(
                group_id=group_id,
                tasks=[task],
                group_type="standalone",
            ))
        
        return groups
    
    def create_groups(
        self,
        session: Session,
        candidates: list[Task],
    ) -> list[TaskGroup]:
        """Create task groups from candidates.
        
        Priority: requirement_id > epic_id > standalone
        
        Args:
            session: Database session
            candidates: List of candidate tasks
            
        Returns:
            List of TaskGroup
        """
        all_groups: list[TaskGroup] = []
        
        # Step 1: Group by requirement_id
        requirement_groups = self.group_by_requirement(candidates)
        all_groups.extend(requirement_groups.values())
        
        # Track task IDs already grouped
        grouped_task_ids: set[UUID] = set()
        for group in all_groups:
            for task in group.tasks:
                grouped_task_ids.add(task.id)
        
        # Step 2: Group remaining tasks by epic_id
        remaining_for_epic = [t for t in candidates if t.id not in grouped_task_ids]
        epic_groups = self.group_by_epic(remaining_for_epic)
        all_groups.extend(epic_groups.values())
        
        # Update grouped task IDs
        for group in epic_groups.values():
            for task in group.tasks:
                grouped_task_ids.add(task.id)
        
        # Step 3: Group remaining as standalone
        remaining_standalone = [t for t in candidates if t.id not in grouped_task_ids]
        standalone_groups = self.group_standalone(remaining_standalone)
        all_groups.extend(standalone_groups)
        
        return all_groups
