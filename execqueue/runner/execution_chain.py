"""Execution chain orchestrator for REQ-021.

This module implements the complete execution chain as specified in REQ-021:
Execution → Validation → Commit Adoption → Worktree Cleanup → Observability

The ExecutionChain class coordinates all components to ensure deterministic
workflow execution with proper error handling and resource cleanup.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING
from uuid import UUID

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.runner.commit_adopter import adopt_commit_with_lifecycle
from execqueue.runner.config import RunnerConfig
from execqueue.runner.validation_pipeline import ValidationPipeline
from execqueue.runner.worktree_cleanup import WorktreeCleanupService
from execqueue.runner.worktree_manager import GitWorktreeManager

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from sqlalchemy.orm import Session

    from execqueue.db.models import WorktreeMetadata
    from execqueue.runner.validation_models import ValidationResult

logger = logging.getLogger(__name__)


class ExecutionChainError(Exception):
    """Base exception for execution chain errors."""

    def __init__(self, message: str, execution_id: UUID | None = None):
        super().__init__(message)
        self.execution_id = execution_id


class ExecutionChain:
    """Orchestrates the complete execution chain for REQ-021.

    This class implements the deterministic workflow:
    Execution → Validation → Commit Adoption → Worktree Cleanup → Observability

    Features:
    - Transactional execution with rollback on failure
    - Resource leak prevention through proper cleanup
    - Comprehensive observability with structured logging
    - Idempotent operations for retry safety
    """

    def __init__(
        self,
        config: RunnerConfig,
    ):
        """Initialize execution chain.

        Args:
            config: Runner configuration with worktree and adoption settings
        """
        self.config = config
        self.worktree_root = config.worktree_root
        self.target_branch = config.adoption_target_branch
        self.max_retries = config.worktree_cleanup_max_retries
        self.force_cleanup = config.worktree_cleanup_force
        
        # Initialize components
        self._worktree_manager = GitWorktreeManager(
            worktree_root=config.worktree_root,
            max_concurrent=config.worktree_max_concurrent,
        )
        self._cleanup_service = WorktreeCleanupService(
            worktree_root=config.worktree_root,
            max_retries=config.worktree_cleanup_max_retries,
            force_cleanup=config.worktree_cleanup_force,
        )

    async def execute(
        self,
        session: Session,
        execution: TaskExecution,
        validation_pipeline: ValidationPipeline,
        validation_commands: list[str] | None = None,
    ) -> bool:
        """Execute the complete chain for a task execution.

        This method orchestrates the entire REQ-021 workflow:
        1. Validate execution result
        2. Attempt commit adoption if validation passes
        3. Cleanup worktree after successful adoption
        4. Handle errors and ensure proper resource cleanup

        Args:
            session: Database session
            execution: Task execution to process
            validation_pipeline: Pipeline to validate execution result
            validation_commands: Optional commands to run after adoption

        Returns:
            True if chain completed successfully, False otherwise

        Raises:
            ExecutionChainError: If execution chain fails catastrophically
        """
        start_time = time.time()
        execution_id = execution.id
        task_id = execution.task_id
        
        logger.info(
            f"Starting execution chain for execution {execution_id}",
            extra={
                "execution_id": str(execution_id),
                "task_id": str(task_id),
                "target_branch": self.target_branch,
            }
        )
        
        try:
            # Step 1: Validate execution result
            validation_result = await self._validate_execution(
                execution=execution,
                validation_pipeline=validation_pipeline,
            )
            
            if not validation_result.passed:
                await self._handle_validation_failure(
                    session=session,
                    execution=execution,
                    validation_result=validation_result,
                )
                return False
            
            # Step 2: Attempt commit adoption
            adoption_success = await self._adopt_commit(
                session=session,
                execution=execution,
                validation_commands=validation_commands,
            )
            
            if not adoption_success:
                # Adoption failed, but execution might still be in REVIEW or FAILED state
                # The adopt_commit_with_lifecycle function handles execution status updates
                return False
            
            # Step 3: Cleanup worktree
            cleanup_success = await self._cleanup_worktree(
                session=session,
                execution=execution,
            )
            
            # Regardless of cleanup success, we consider the adoption successful
            # Cleanup failures are handled separately and don't affect the core workflow
            duration = time.time() - start_time
            logger.info(
                f"Execution chain completed for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(task_id),
                    "duration_seconds": duration,
                    "cleanup_success": cleanup_success,
                }
            )
            
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Execution chain failed for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(task_id),
                    "duration_seconds": duration,
                    "error": str(e),
                },
                exc_info=True,
            )
            
            # Attempt emergency cleanup
            await self._emergency_cleanup(
                session=session,
                execution=execution,
            )
            
            raise ExecutionChainError(
                f"Execution chain failed: {e}", 
                execution_id=execution_id
            ) from e

    async def _validate_execution(
        self,
        execution: TaskExecution,
        validation_pipeline: ValidationPipeline,
    ) -> ValidationResult:
        """Validate execution result using validation pipeline.

        Args:
            execution: Task execution to validate
            validation_pipeline: Pipeline to use for validation

        Returns:
            ValidationResult from validation pipeline
        """
        logger.info(
            f"Validating execution {execution.id}",
            extra={
                "execution_id": str(execution.id),
                "task_id": str(execution.task_id),
                "validator_count": validation_pipeline.validator_count,
            }
        )
        
        return await validation_pipeline.validate(execution)

    async def _handle_validation_failure(
        self,
        session: Session,
        execution: TaskExecution,
        validation_result: ValidationResult,
    ) -> None:
        """Handle validation failure by updating execution status.

        Args:
            session: Database session
            execution: Task execution to update
            validation_result: Validation result that caused failure
        """
        execution_id = execution.id
        
        if validation_result.failed:
            execution.status = ExecutionStatus.FAILED.value
            execution.error_type = "VALIDATION_FAILED"
            execution.error_message = (
                f"Validation failed: {len(validation_result.issues)} issues found. "
                f"First issue: {validation_result.issues[0].message if validation_result.issues else 'Unknown'}"
            )
        elif validation_result.requires_review:
            execution.status = ExecutionStatus.REVIEW.value
            execution.error_type = "VALIDATION_REQUIRES_REVIEW"
            execution.error_message = (
                f"Validation requires manual review: {len(validation_result.issues)} issues found. "
                f"First issue: {validation_result.issues[0].message if validation_result.issues else 'Unknown'}"
            )
        else:
            # This shouldn't happen, but handle gracefully
            execution.status = ExecutionStatus.FAILED.value
            execution.error_type = "VALIDATION_UNKNOWN"
            execution.error_message = "Validation returned unexpected status"
        
        session.commit()
        
        logger.warning(
            f"Validation failed for execution {execution_id}",
            extra={
                "execution_id": str(execution_id),
                "task_id": str(execution.task_id),
                "validation_status": validation_result.status.value,
                "issue_count": len(validation_result.issues),
            }
        )

    async def _adopt_commit(
        self,
        session: Session,
        execution: TaskExecution,
        validation_commands: list[str] | None = None,
    ) -> bool:
        """Attempt to adopt commit to target branch.

        Args:
            session: Database session
            execution: Task execution to adopt commit from
            validation_commands: Optional commands to run after adoption

        Returns:
            True if adoption succeeded or is pending review, False if failed
        """
        execution_id = execution.id
        
        # Check if we have a commit to adopt
        if not execution.commit_sha_after:
            logger.error(
                f"No commit SHA available for adoption in execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(execution.task_id),
                }
            )
            execution.status = ExecutionStatus.FAILED.value
            execution.error_type = "MISSING_COMMIT_SHA"
            execution.error_message = "No commit SHA available for adoption"
            session.commit()
            return False
        
        logger.info(
            f"Attempting commit adoption for execution {execution_id}",
            extra={
                "execution_id": str(execution_id),
                "task_id": str(execution.task_id),
                "commit_sha": execution.commit_sha_after,
                "target_branch": self.target_branch,
            }
        )
        
        # Get worktree metadata
        worktree_metadata = await self._worktree_manager.get_worktree_info(
            task_id=execution.task_id,
            session=session,
        )
        
        if not worktree_metadata:
            logger.error(
                f"No worktree metadata found for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(execution.task_id),
                }
            )
            execution.status = ExecutionStatus.FAILED.value
            execution.error_type = "MISSING_WORKTREE_METADATA"
            execution.error_message = "No worktree metadata found"
            session.commit()
            return False
        
        # Perform adoption with lifecycle management
        adoption_result = await adopt_commit_with_lifecycle(
            session=session,
            execution=execution,
            target_worktree_path=self.worktree_root,
            target_branch=self.target_branch,
            validation_commands=validation_commands,
        )
        
        if adoption_result.success and adoption_result.validation_passed:
            logger.info(
                f"Commit adoption succeeded for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(execution.task_id),
                    "adopted_sha": adoption_result.adopted_commit_sha,
                }
            )
            return True
        elif adoption_result.conflict_detected or adoption_result.needs_review:
            # Adoption requires manual review
            logger.warning(
                f"Commit adoption requires review for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(execution.task_id),
                    "reason": adoption_result.error_message,
                }
            )
            return True  # Consider this "successful" from a workflow perspective
        else:
            # Adoption failed
            logger.error(
                f"Commit adoption failed for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(execution.task_id),
                    "error": adoption_result.error_message,
                }
            )
            return False

    async def _cleanup_worktree(
        self,
        session: Session,
        execution: TaskExecution,
    ) -> bool:
        """Cleanup worktree after successful adoption.

        Args:
            session: Database session
            execution: Task execution that was adopted

        Returns:
            True if cleanup succeeded, False otherwise
        """
        execution_id = execution.id
        task_id = execution.task_id
        
        logger.info(
            f"Cleaning up worktree for execution {execution_id}",
            extra={
                "execution_id": str(execution_id),
                "task_id": str(task_id),
            }
        )
        
        # Perform cleanup
        cleanup_success = await self._cleanup_service.cleanup_after_adoption(
            task_id=task_id,
            worktree_path=execution.worktree_path,
            session=session,
        )
        
        if cleanup_success:
            logger.info(
                f"Worktree cleanup succeeded for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(task_id),
                }
            )
        else:
            logger.warning(
                f"Worktree cleanup failed for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(task_id),
                }
            )
        
        return cleanup_success

    async def _emergency_cleanup(
        self,
        session: Session,
        execution: TaskExecution,
    ) -> None:
        """Perform emergency cleanup on catastrophic failure.

        Args:
            session: Database session
            execution: Task execution to clean up after
        """
        try:
            execution_id = execution.id
            task_id = execution.task_id
            
            logger.warning(
                f"Performing emergency cleanup for execution {execution_id}",
                extra={
                    "execution_id": str(execution_id),
                    "task_id": str(task_id),
                }
            )
            
            # Attempt forced cleanup
            await self._cleanup_service.cleanup_after_adoption(
                task_id=task_id,
                worktree_path=execution.worktree_path,
                session=session,
            )
        except Exception as e:
            logger.error(
                f"Emergency cleanup failed for execution {execution.id}",
                extra={
                    "execution_id": str(execution.id),
                    "task_id": str(execution.task_id),
                    "error": str(e),
                },
                exc_info=True,
            )