"""Task grouping engine for REQ-015 workflow processing.

Implements efficient grouping of tasks by requirement_id, epic_id, or as standalone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from execqueue.db.models import Task

logger = logging.getLogger(__name__)


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
                logger.debug(
                    "Skipping task %s (no requirement_id)",
                    task.id,
                )
                continue
            
            req_id = task.requirement_id
            if req_id not in groups:
                logger.debug(
                    "Creating new requirement group %s for task %s",
                    req_id,
                    task.id,
                )
                groups[req_id] = []
            groups[req_id].append(task)
        
        result = {
            req_id: TaskGroup(
                group_id=req_id,
                tasks=task_list,
                group_type="requirement",
                requirement_id=req_id,
            )
            for req_id, task_list in groups.items()
        }
        
        logger.info(
            "Grouped %d tasks into %d requirement groups",
            len(tasks),
            len(result),
        )
        
        return result
    
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
        skipped_no_epic = 0
        skipped_invalid_epic = 0
        
        for task in tasks:
            epic_id_str = task.details.get("epic_id")
            if not epic_id_str:
                skipped_no_epic += 1
                logger.debug(
                    "Skipping task %s (no epic_id in details)",
                    task.id,
                )
                continue
            
            try:
                epic_id = UUID(epic_id_str) if isinstance(epic_id_str, str) else epic_id_str
            except (ValueError, TypeError):
                skipped_invalid_epic += 1
                logger.warning(
                    "Skipping task %s (invalid epic_id format: %s)",
                    task.id,
                    epic_id_str,
                )
                continue
            
            if epic_id not in groups:
                logger.debug(
                    "Creating new epic group %s for task %s",
                    epic_id,
                    task.id,
                )
                groups[epic_id] = []
            groups[epic_id].append(task)
        
        result = {
            epic_id: TaskGroup(
                group_id=epic_id,
                tasks=task_list,
                group_type="epic",
                epic_id=epic_id,
            )
            for epic_id, task_list in groups.items()
        }
        
        logger.info(
            "Grouped %d tasks into %d epic groups (skipped: %d no epic, %d invalid)",
            len(tasks),
            len(result),
            skipped_no_epic,
            skipped_invalid_epic,
        )
        
        return result
    
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
                logger.debug(
                    "Skipping task %s (already has requirement_id)",
                    task.id,
                )
                continue
            
            epic_id_str = task.details.get("epic_id")
            if epic_id_str:
                logger.debug(
                    "Skipping task %s (already has epic_id)",
                    task.id,
                )
                continue
            
            group_id = uuid4()
            logger.debug(
                "Creating standalone group %s for task %s",
                group_id,
                task.id,
            )
            groups.append(TaskGroup(
                group_id=group_id,
                tasks=[task],
                group_type="standalone",
            ))
        
        logger.info(
            "Created %d standalone groups from %d tasks",
            len(groups),
            len(tasks),
        )
        
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
        logger.info(
            "Starting task grouping for %d candidates",
            len(candidates),
        )
        
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
        logger.debug(
            "Grouping %d remaining tasks by epic_id",
            len(remaining_for_epic),
        )
        epic_groups = self.group_by_epic(remaining_for_epic)
        all_groups.extend(epic_groups.values())
        
        # Update grouped task IDs
        for group in epic_groups.values():
            for task in group.tasks:
                grouped_task_ids.add(task.id)
        
        # Step 3: Group remaining as standalone
        remaining_standalone = [t for t in candidates if t.id not in grouped_task_ids]
        logger.debug(
            "Grouping %d remaining tasks as standalone",
            len(remaining_standalone),
        )
        standalone_groups = self.group_standalone(remaining_standalone)
        all_groups.extend(standalone_groups)
        
        logger.info(
            "Task grouping complete: %d requirement groups, %d epic groups, %d standalone groups",
            len(requirement_groups),
            len(epic_groups),
            len(standalone_groups),
        )
        
        return all_groups
