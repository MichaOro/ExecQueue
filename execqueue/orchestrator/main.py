"""Main orchestrator for REQ-011/REQ-015 execution preparation.

This module provides the main Orchestrator class that coordinates all
preparation steps from candidate discovery to context handoff, including
workflow-based processing for REQ-015.
"""

from __future__ import annotations

import asyncio
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
from execqueue.orchestrator.grouping import TaskGroup, TaskGroupingEngine
from execqueue.orchestrator.context_builder import WorkflowContextBuilder
from execqueue.orchestrator.workflow_repo import WorkflowRepository
from execqueue.orchestrator.runner_manager import RunnerManager, RunnerHandle
from execqueue.orchestrator.workflow_models import WorkflowStatus
from execqueue.runner.config import RunnerConfig

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
    workflow_id: UUID | None = None

class Orchestrator:
    """Main orchestrator for execution preparation (REQ-011/REQ-015).
    
    This orchestrator implements the full preparation flow:
    1. Candidate Discovery - Find executable backlog tasks
    2. Task Grouping - Group tasks by requirement/epic/standalone
    3. Classification - Determine read-only/write, parallel/sequential
    4. Batch Planning - Create safe execution batches
    5. Atomic Locking - Claim tasks (backlog -> queued)
    6. Git Context - Prepare branch/worktree for write tasks
    7. Context Contract - Build PreparedExecutionContext for handoff
    8. Workflow Persistence - Store workflow state for crash recovery
    9. Runner Management - Start and track runner instances
    
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
        
        # REQ-015 components
        self.grouping_engine = TaskGroupingEngine()
        self.workflow_builder = WorkflowContextBuilder()
        self.workflow_repo = WorkflowRepository()
        self.runner_manager = RunnerManager()
    
    def run_preparation_cycle(self, session: Session) -> list[PreparationResult]:
        """Run a full preparation cycle with workflow support.
        
        This is the main entry point for the orchestrator. It discovers
        candidates, groups them into workflows, and prepares contexts.
        
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
            
            # Step 2: Group tasks into workflows (REQ-015)
            groups = self.grouping_engine.create_groups(session, candidates)
            logger.info("Created %d task groups", len(groups))
            
            # Step 3: Process each group as a workflow
            for group in groups:
                result = self._process_workflow_group(session, group)
                results.extend(result)
            
            logger.info(
                "Preparation cycle complete: %d succeeded, %d failed",
                sum(1 for r in results if r.success),
                sum(1 for r in results if not r.success),
            )
            
        except Exception as e:
            logger.error("Preparation cycle failed: %s", e, exc_info=True)
        
        return results
    
    def _process_workflow_group(
        self,
        session: Session,
        group: TaskGroup,
    ) -> list[PreparationResult]:
        """Process a task group as a workflow.
        
        Args:
            session: Database session
            group: TaskGroup to process
            
        Returns:
            List of preparation results
        """
        results: list[PreparationResult] = []
        
        try:
            # Step 1: Build workflow context
            wf_ctx = self.workflow_builder.build_context(group)
            
            # Step 2: Validate context
            errors = self.workflow_builder.validate_context(wf_ctx)
            if errors:
                logger.warning("Workflow context validation failed: %s", errors)
                # Create failed results for all tasks in group
                for task in group.tasks:
                    results.append(PreparationResult(
                        task_id=task.id,
                        task_number=task.task_number,
                        success=False,
                        error=PreparationError(
                            error_type=PreparationErrorType.NON_RECOVERABLE,
                            message=f"Context validation failed: {errors}",
                            task_id=task.id,
                        ),
                        workflow_id=group.group_id,
                    ))
                return results
            
            # Step 3: Create workflow record
            workflow = self.workflow_repo.create_workflow(session, wf_ctx)
            logger.info(
                "Created workflow %s (type=%s, tasks=%d)",
                workflow.id,
                group.group_type,
                len(group.tasks),
            )
            
            # Step 4: Prepare contexts for each task in the group
            for task in group.tasks:
                result = self._prepare_task_context(
                    session, task, str(workflow.id),
                )
                result.workflow_id = workflow.id
                results.append(result)
            
            # Step 5: Start runner for workflow (async, non-blocking)
            try:
                handle = asyncio.run(
                    self.runner_manager.start_runner_for_context(wf_ctx)
                )
                
                # Step 6: Store runner_uuid in workflow
                self.workflow_repo.set_runner_uuid(
                    session, workflow.id, handle.runner_uuid
                )
                logger.info(
                    "Started runner %s for workflow %s",
                    handle.runner_uuid,
                    workflow.id,
                )
            except Exception as e:
                logger.warning("Failed to start runner: %s", e)
            
        except Exception as e:
            logger.error("Failed to process workflow group: %s", e, exc_info=True)
            # Create failed results for all tasks in group
            for task in group.tasks:
                results.append(PreparationResult(
                    task_id=task.id,
                    task_number=task.task_number,
                    success=False,
                    error=PreparationError(
                        error_type=PreparationErrorType.RECOVERABLE,
                        message=f"Workflow processing failed: {e}",
                        task_id=task.id,
                    ),
                    workflow_id=group.group_id,
                ))
        
        return results
    
    async def recover_running_workflows(
        self,
        session: Session,
    ) -> None:
        """Recover running workflows after a crash.
        
        Loads running workflows from the database and restarts missing runners.
        Already completed tasks (status=DONE) are skipped.
        
        Args:
            session: Database session
        """
        logger.info("Starting workflow recovery")
        
        try:
            # Get all running workflows
            running = self.workflow_repo.get_running_workflows(session)
            logger.info("Found %d running workflows to recover", len(running))
            
            for wf in running:
                # Check if runner already exists
                if wf.runner_uuid:
                    handle = self.runner_manager.get_runner_handle(wf.id)
                    if handle is None:
                        # Runner lost, need to restart
                        logger.info(
                            "Restarting lost runner for workflow %s",
                            wf.id,
                        )
                    else:
                        # Runner still running, skip
                        logger.info(
                            "Runner %s already running for workflow %s",
                            wf.runner_uuid,
                            wf.id,
                        )
                        continue
                
                # Load tasks for this workflow
                # Note: We use batch_id as the workflow ID reference
                tasks = session.query(Task).filter(
                    Task.batch_id == str(wf.id)
                ).all()
                
                if not tasks:
                    # No tasks found, mark workflow as done
                    logger.warning(
                        "No tasks found for workflow %s, marking as done",
                        wf.id,
                    )
                    self.workflow_repo.update_status(
                        session, wf.id, WorkflowStatus.DONE
                    )
                    continue
                
                # Filter out done tasks
                pending_tasks = [
                    t for t in tasks
                    if t.status != TaskStatus.DONE.value
                ]
                
                if not pending_tasks:
                    # All tasks done, mark workflow as done
                    logger.info(
                        "All tasks done for workflow %s, marking as done",
                        wf.id,
                    )
                    self.workflow_repo.update_status(
                        session, wf.id, WorkflowStatus.DONE
                    )
                    continue
                
                # Rebuild group and context
                group = TaskGroup(
                    group_id=wf.id,
                    tasks=pending_tasks,
                    group_type="recovered",
                    epic_id=wf.epic_id,
                    requirement_id=wf.requirement_id,
                )
                
                wf_ctx = self.workflow_builder.build_context(group)
                
                # Start new runner
                handle = await self.runner_manager.start_runner_for_context(wf_ctx)
                self.workflow_repo.set_runner_uuid(
                    session, wf.id, handle.runner_uuid
                )
                logger.info(
                    "Restarted runner %s for recovered workflow %s",
                    handle.runner_uuid,
                    wf.id,
                )
        
        except Exception as e:
            logger.error("Workflow recovery failed: %s", e, exc_info=True)
    
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
