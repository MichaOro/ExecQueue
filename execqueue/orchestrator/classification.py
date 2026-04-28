"""Task classification and batch planning for REQ-011.

This module implements task classification (read-only vs write, parallel vs sequential)
and safe batch planning without any side effects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from execqueue.orchestrator.models import (
    BatchPlan,
    BatchType,
    RunnerMode,
    TaskClassification,
)

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Internal classification result before batch planning."""
    
    task_id: UUID
    task_number: int
    requires_write: bool
    parallel_mode: str
    conflict_key: str | None
    reasons: list[str]


class TaskClassifier:
    """Classifies tasks for execution preparation.
    
    Classification rules (conservative defaults):
    - Missing requires_write_access => write (default True)
    - Missing parallelization_mode => sequential (default)
    - Unknown task types => conservative: write + sequential
    
    This class produces no side effects - it only reads task metadata.
    """
    
    def __init__(self):
        """Initialize classifier with default rules."""
        self._write_access_field = "requires_write_access"
        self._parallel_mode_field = "parallelization_mode"
        self._branch_field = "branch_name"
    
    def classify(self, task_id: UUID, task_number: int, task_type: str, details: dict[str, Any] | None) -> TaskClassification:
        """Classify a single task.
        
        Args:
            task_id: Task UUID
            task_number: Public task number
            task_type: Task type (planning, execution, analysis)
            details: Task details JSON
            
        Returns:
            TaskClassification with computed values
        """
        details = details or {}
        reasons = []
        
        # Determine requires_write_access
        # Default: True (conservative - missing means write)
        requires_write = details.get(self._write_access_field, True)
        if requires_write is True:
            reasons.append("requires_write_access default=True")
        elif requires_write is False:
            reasons.append("requires_write_access=False explicitly set")
        
        # Determine parallelization_mode
        # Default: sequential (conservative)
        parallel_mode = details.get(self._parallel_mode_field, "sequential")
        if parallel_mode == "sequential":
            reasons.append("parallelization_mode=sequential (default or explicit)")
        elif parallel_mode == "parallel":
            reasons.append("parallelization_mode=parallel")
        else:
            reasons.append(f"parallelization_mode={parallel_mode} (unknown, treated as sequential)")
            parallel_mode = "sequential"
        
        # Determine conflict key
        # For write tasks: branch_name or generated key
        # For read-only: None or repo-based key
        conflict_key = None
        if requires_write:
            explicit_branch = details.get(self._branch_field)
            if explicit_branch:
                conflict_key = f"branch:{explicit_branch}"
                reasons.append(f"conflict_key=branch:{explicit_branch}")
            else:
                # Will generate deterministic branch name during preparation
                conflict_key = f"task:{task_number}"
                reasons.append(f"conflict_key=task:{task_number} (auto-generated branch)")
        else:
            # Read-only tasks can run in parallel
            conflict_key = None
            reasons.append("no conflict_key for read-only")
        
        # Determine effective runner mode
        runner_mode = RunnerMode.WRITE if requires_write else RunnerMode.READ_ONLY
        
        return TaskClassification(
            task_id=task_id,
            task_number=task_number,
            requires_write_access=requires_write,
            parallelization_mode=parallel_mode,
            effective_runner_mode=runner_mode,
            conflict_key=conflict_key,
            reason_codes=tuple(reasons),
        )
    
    def classify_batch(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[TaskClassification]:
        """Classify a batch of tasks.
        
        Args:
            tasks: List of task dicts with id, task_number, type, details
            
        Returns:
            List of TaskClassification objects
        """
        classifications = []
        for task in tasks:
            classification = self.classify(
                task_id=task["id"],
                task_number=task["task_number"],
                task_type=task["type"],
                details=task.get("details"),
            )
            classifications.append(classification)
            logger.debug(
                "Classified task %s: %s",
                task["task_number"],
                ", ".join(classification.reason_codes),
            )
        return classifications


class BatchPlanner:
    """Creates safe batch plans from classified tasks.
    
    Batch types:
    1. readonly_parallel: Multiple read-only tasks, no conflicts
    2. write_parallel_isolated: Write tasks with isolated branches/worktrees
    3. write_sequential: Single write task or serialized conflict group
    
    The planner produces transient plans that are not persisted until
    atomic locking (AP 04) succeeds.
    """
    
    def __init__(self, max_batch_size: int = 10):
        """Initialize batch planner.
        
        Args:
            max_batch_size: Maximum tasks per batch
        """
        self.max_batch_size = max_batch_size
    
    def create_batch_plan(
        self,
        classifications: list[TaskClassification],
    ) -> BatchPlan:
        """Create a batch plan from task classifications.
        
        Args:
            classifications: List of task classifications
            
        Returns:
            BatchPlan with included/excluded tasks
        """
        batch_id = f"batch-{datetime.utcnow().isoformat()}-{uuid4().hex[:8]}"
        
        # Separate read-only and write tasks
        readonly_tasks: list[TaskClassification] = []
        write_tasks: list[TaskClassification] = []
        
        for classification in classifications:
            if classification.effective_runner_mode == RunnerMode.READ_ONLY:
                readonly_tasks.append(classification)
            else:
                write_tasks.append(classification)
        
        # Group write tasks by conflict key
        conflict_groups: dict[str | None, list[TaskClassification]] = {}
        for task in write_tasks:
            key = task.conflict_key
            if key not in conflict_groups:
                conflict_groups[key] = []
            conflict_groups[key].append(task)
        
        # Build batch based on rules
        included_ids: list[UUID] = []
        excluded_ids: list[UUID] = []
        exclusion_reasons: dict[UUID, str] = {}
        
        # Read-only tasks can all run in parallel (up to max_batch_size)
        readonly_batch = readonly_tasks[:self.max_batch_size]
        included_ids.extend(t.task_id for t in readonly_batch)
        if len(readonly_tasks) > self.max_batch_size:
            for t in readonly_tasks[self.max_batch_size:]:
                excluded_ids.append(t.task_id)
                exclusion_reasons[t.task_id] = f"Exceeded max_batch_size ({self.max_batch_size})"
        
        # Write tasks: serialize conflict groups
        write_count = 0
        for conflict_key, group in conflict_groups.items():
            if conflict_key is None:
                # Should not happen for write tasks, but handle gracefully
                for t in group[:1]:
                    if write_count < self.max_batch_size:
                        included_ids.append(t.task_id)
                        write_count += 1
                    else:
                        excluded_ids.append(t.task_id)
                        exclusion_reasons[t.task_id] = "Exceeded max_batch_size"
            elif len(group) == 1:
                # Single task in conflict group - can be parallelized with other isolated tasks
                if write_count < self.max_batch_size:
                    included_ids.append(group[0].task_id)
                    write_count += 1
                else:
                    excluded_ids.append(group[0].task_id)
                    exclusion_reasons[group[0].task_id] = "Exceeded max_batch_size"
            else:
                # Multiple tasks with same conflict key - serialize (take first)
                for t in group[:1]:
                    if write_count < self.max_batch_size:
                        included_ids.append(t.task_id)
                        write_count += 1
                    else:
                        excluded_ids.append(t.task_id)
                        exclusion_reasons[t.task_id] = f"Conflict with branch {conflict_key}"
                for t in group[1:]:
                    excluded_ids.append(t.task_id)
                    exclusion_reasons[t.task_id] = f"Blocked by conflict key {conflict_key}"
        
        # Determine batch type
        if not write_tasks:
            batch_type = BatchType.READONLY_PARALLEL
        elif len(included_ids) == 1 and write_tasks:
            batch_type = BatchType.WRITE_SEQUENTIAL
        else:
            # Check if all write tasks have isolated conflict keys
            conflict_keys = set(t.conflict_key for t in write_tasks if t.conflict_key)
            if len(conflict_keys) >= len([t for t in write_tasks if t.conflict_key]):
                batch_type = BatchType.WRITE_PARALLEL_ISOLATED
            else:
                batch_type = BatchType.WRITE_SEQUENTIAL
        
        return BatchPlan(
            batch_id=batch_id,
            batch_type=batch_type,
            task_ids=tuple(included_ids),
            excluded_task_ids=tuple(excluded_ids),
            exclusion_reasons=exclusion_reasons,
            created_at=datetime.utcnow(),
        )
    
    def plan_for_single_task(
        self,
        classification: TaskClassification,
    ) -> BatchPlan:
        """Create a batch plan for a single task.
        
        Args:
            classification: Single task classification
            
        Returns:
            BatchPlan with single task
        """
        batch_id = f"single-{datetime.utcnow().isoformat()}-{uuid4().hex[:8]}"
        batch_type = (
            BatchType.READONLY_PARALLEL
            if classification.effective_runner_mode == RunnerMode.READ_ONLY
            else BatchType.WRITE_SEQUENTIAL
        )
        
        return BatchPlan(
            batch_id=batch_id,
            batch_type=batch_type,
            task_ids=(classification.task_id,),
            created_at=datetime.utcnow(),
        )
