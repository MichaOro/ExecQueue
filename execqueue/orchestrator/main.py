"""Main orchestrator for REQ-011 execution preparation.

This module provides the main Orchestrator class that coordinates all
preparation steps from candidate discovery to context handoff.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from execqueue.db.models import Task, TaskStatus
from execqueue.orchestrator.candidate_discovery import CandidateDiscovery
from execqueue.orchestrator.classification import TaskClassifier, BatchPlanner
from execqueue.orchestrator.context_contract import PreparedContextBuilder
from execqueue.orchestrator.git_context import GitContextPreparer
from execqueue.orchestrator.locking import TaskLocker
from execqueue.orchestrator.models import (
    BatchPlan,
    BatchType,
    PreparedExecutionContext,
    PreparationError,
    PreparationErrorType,
    TaskClassification,
)

logger = logging.getLogger(__name__)


@dataclass
class PreparationResult:
    """Result of preparation for a single task."""
    
    task_id: UUID
    task_number: int
    success: bool
    context: PreparedExecutionContext | None = None
    error: PreparationError | None = None
    queued_at: datetime | None = None


class Orchestrator:
    """Main orchestrator for execution preparation (REQ-011).
    
    This orchestrator implements the full preparation flow:
    1. Candidate Discovery - Find executable backlog tasks
    2. Classification - Determine read-only/write, parallel/sequential
    3. Batch Planning - Create safe execution batches
    4. Atomic Locking - Claim tasks (backlog -> queued)
    5. Git Context - Prepare branch/worktree for write tasks
    6. Context Contract - Build PreparedExecutionContext for handoff
    
    Scope: Prepares tasks up to prepared_context_available. Does NOT:
    - Start OpenCode sessions
    - Send prompts
    - Transition to in_progress
    """
    
    def __init__(
        self,
        worker_id: str | None = None,
        max_batch_size: int = 10,
        worktree_root: Path | None = None,
        base_repo_path: Path | None = None,
    ):
        """Initialize orchestrator.
        
        Args:
            worker_id: Unique worker identifier (auto-generated if not provided)
            max_batch_size: Maximum tasks per batch
            worktree_root: Root for Git worktrees
            base_repo_path: Base repository path
        """
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.max_batch_size = max_batch_size
        
        # Defaults for paths
        self.worktree_root = worktree_root or Path("/tmp/execqueue/worktrees")
        self.base_repo_path = base_repo_path or Path(".")
        
        # Initialize components
        self.candidate_discovery = CandidateDiscovery(max_batch_size=max_batch_size)
        self.classifier = TaskClassifier()
        self.batch_planner = BatchPlanner(max_batch_size=max_batch_size)
        self.locker = TaskLocker(worker_id=self.worker_id)
        self.context_builder = PreparedContextBuilder(base_repo_path=str(self.base_repo_path))
        self.git_preparer = GitContextPreparer(
            worktree_root=self.worktree_root,
            base_repo_path=self.base_repo_path,
        )
    
    def run_preparation_cycle(self, session: Session) -> list[PreparationResult]:
        """Run a full preparation cycle.
        
        This is the main entry point for the orchestrator. It discovers
        candidates, classifies them, locks them, and prepares contexts.
        
        Args:
            session: Database session
            
        Returns:
            List of preparation results
        """
        logger.info("Starting preparation cycle (worker=%s)", self.worker_id)
        
        results: list[PreparationResult] = []
        
        try:
            # Step 1: Discover candidates
            candidates = self.candidate_discovery.find_candidates(session)
            if not candidates:
                logger.info("No executable backlog candidates found")
                return results
            
            logger.info("Found %d candidates", len(candidates))
            
            # Step 2: Classify tasks
            task_data = [
                {
                    "id": task.id,
                    "task_number": task.task_number,
                    "type": task.type,
                    "details": task.details,
                }
                for task in candidates
            ]
            classifications = self.classifier.classify_batch(task_data)
            
            # Step 3: Create batch plan
            batch_plan = self.batch_planner.create_batch_plan(classifications)
            logger.info(
                "Created batch plan %s (type=%s, tasks=%d, excluded=%d)",
                batch_plan.batch_id,
                batch_plan.batch_type,
                len(batch_plan.task_ids),
                len(batch_plan.excluded_task_ids),
            )
            
            # Step 4: Atomic locking
            lock_result = self.locker.lock_tasks(session, batch_plan)
            
            if not lock_result.success:
                logger.warning(
                    "Locking failed for some tasks: %s",
                    lock_result.failure_reasons,
                )
                # Add failed tasks as results
                for task_id, reason in lock_result.failure_reasons.items():
                    task = session.get(Task, task_id)
                    if task:
                        results.append(PreparationResult(
                            task_id=task_id,
                            task_number=task.task_number,
                            success=False,
                            error=PreparationError(
                                error_type=PreparationErrorType.CONFLICT,
                                message=reason,
                                task_id=task_id,
                            ),
                        ))
            
            # Step 5-6: Prepare contexts for locked tasks
            for task_id in lock_result.locked_task_ids:
                task = session.get(Task, task_id)
                if not task:
                    continue
                
                result = self._prepare_task_context(session, task, batch_plan.batch_id)
                results.append(result)
            
            logger.info(
                "Preparation cycle complete: %d succeeded, %d failed",
                sum(1 for r in results if r.success),
                sum(1 for r in results if not r.success),
            )
            
        except Exception as e:
            logger.error("Preparation cycle failed: %s", e, exc_info=True)
        
        return results
    
    def _prepare_task_context(
        self,
        session: Session,
        task: Task,
        batch_id: str,
    ) -> PreparationResult:
        """Prepare context for a single task.
        
        Args:
            session: Database session
            task: Locked task
            batch_id: Batch ID
            
        Returns:
            PreparationResult
        """
        try:
            # Get classification for this task
            classification = self.classifier.classify(
                task_id=task.id,
                task_number=task.task_number,
                task_type=task.type,
                details=task.details,
            )
            
            # Prepare Git context if needed
            branch_name: str | None = None
            worktree_path: str | None = None
            commit_sha_before: str | None = None
            
            if classification.requires_write_access:
                git_context = self.git_preparer.prepare_context(
                    task_id=task.id,
                    task_number=task.task_number,
                    explicit_branch=None,  # Could be from task.details
                )
                branch_name = git_context.branch_name
                worktree_path = str(git_context.worktree_path)
                commit_sha_before = git_context.commit_sha_before
                
                # Update task with Git context
                task.branch_name = branch_name
                task.worktree_path = worktree_path
                task.commit_sha_before = commit_sha_before
            
            # Build context
            context = self.context_builder.build_context(
                task_id=task.id,
                task_number=task.task_number,
                task_type=task.type,
                requires_write=classification.requires_write_access,
                branch_name=branch_name,
                worktree_path=worktree_path,
                commit_sha_before=commit_sha_before,
                batch_id=batch_id,
                correlation_id=f"prep-{task.id.hex[:8]}",
                details=task.details,
            )
            
            # Validate context
            errors = self.context_builder.validate_context(context)
            if errors:
                raise PreparationError(
                    error_type=PreparationErrorType.NON_RECOVERABLE,
                    message=f"Context validation failed: {errors}",
                    task_id=task.id,
                    details={"errors": errors},
                )
            
            # Update task status to prepared
            task.status = TaskStatus.PREPARED.value
            task.prepared_context_version = context.version
            task.updated_at = datetime.utcnow()
            
            session.commit()
            
            logger.info(
                "Prepared context for task %s (runner_mode=%s)",
                task.task_number,
                context.runner_mode.value,
            )
            
            return PreparationResult(
                task_id=task.id,
                task_number=task.task_number,
                success=True,
                context=context,
                queued_at=task.queued_at,
            )
        
        except PreparationError as e:
            # Handle preparation error
            task.preparation_attempt_count = (task.preparation_attempt_count or 0) + 1
            task.last_preparation_error = e.message
            task.updated_at = datetime.utcnow()
            
            # Determine target status based on error type
            if e.is_non_recoverable():
                task.status = TaskStatus.FAILED.value
            else:
                # Release lock and return to backlog
                self.locker.release_lock(session, task.id, TaskStatus.BACKLOG)
            
            session.commit()
            
            logger.error(
                "Preparation failed for task %s: %s (type=%s)",
                task.task_number,
                e.message,
                e.error_type.value,
            )
            
            return PreparationResult(
                task_id=task.id,
                task_number=task.task_number,
                success=False,
                error=e,
            )
        
        except Exception as e:
            # Unexpected error
            task.preparation_attempt_count = (task.preparation_attempt_count or 0) + 1
            task.last_preparation_error = str(e)
            task.updated_at = datetime.utcnow()
            session.commit()
            
            logger.error(
                "Unexpected error preparing task %s: %s",
                task.task_number,
                e,
                exc_info=True,
            )
            
            return PreparationResult(
                task_id=task.id,
                task_number=task.task_number,
                success=False,
                error=PreparationError(
                    error_type=PreparationErrorType.RECOVERABLE,
                    message=f"Unexpected error: {e}",
                    task_id=task.id,
                ),
            )
