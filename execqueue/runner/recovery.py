"""Recovery service for REQ-012-09 with observability for REQ-012-10.

This module provides:
- Recovery decision logic
- Write-task recovery with Git pre-checks
- Recovery event persistence
- Stale execution handling
- Per REQ-012-10: Structured logging with correlation IDs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import git
from sqlalchemy.orm import Session

from execqueue.models.enums import ExecutionStatus, EventType
from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent
from execqueue.observability import (
    get_logger,
    log_phase_event,
    record_retry_scheduled,
    record_retry_exhausted,
    record_stale_detection,
    record_adoption_conflict,
    get_metrics,
)
from execqueue.runner.error_classification import (
    DEFAULT_RETRY_MATRIX,
    DEFAULT_STALE_THRESHOLDS,
    ErrorType,
    RecoveryAction,
    RecoveryDecision,
    RetryDecision,
    RunnerPhase,
    StaleThresholds,
    calculate_retry_decision,
    classify_error,
    find_stale_executions,
    is_execution_stale,
)

logger = logging.getLogger(__name__)
obs_logger = get_logger(__name__)


# ============================================================================
# Recovery Service
# ============================================================================


class RecoveryService:
    """Service for handling execution recovery.

    Per REQ-012-09:
    - Fehler konsistent klassifizieren
    - Retrybare Fälle begrenzt wiederholen
    - Stale Executions sicher behandeln
    - Recovery muss idempotent sein, besonders bei Write-Tasks
    """

    def __init__(
        self,
        retry_matrix=None,
        stale_thresholds: StaleThresholds | None = None,
    ):
        """Initialize recovery service.

        Args:
            retry_matrix: Retry matrix configuration
            stale_thresholds: Stale detection thresholds
        """
        self.retry_matrix = retry_matrix or DEFAULT_RETRY_MATRIX
        self.stale_thresholds = stale_thresholds or DEFAULT_STALE_THRESHOLDS

    def handle_error(
        self,
        session: Session,
        execution: TaskExecution,
        exception: Exception,
        phase: RunnerPhase,
    ) -> RecoveryDecision:
        """Handle an error during execution.

        Per REQ-012-09: Recovery-Aktionen: weiter beobachten, retry planen,
        review, failed, adoption erneut validieren.
        Per REQ-012-10: Logs with correlation ID and structured format.

        Args:
            session: Database session
            execution: The failed TaskExecution
            exception: The exception that occurred
            phase: Current runner phase

        Returns:
            RecoveryDecision with recommended action
        """
        correlation_id = execution.correlation_id or "unknown"
        execution_id_str = str(execution.id)
        task_id_str = str(execution.task_id)

        # Classify the error
        error_type = classify_error(exception, phase)
        execution.error_type = error_type.value
        execution.error_message = str(exception)

        # Log error classification
        log_phase_event(
            obs_logger,
            f"Error classified as {error_type.value}: {exception}",
            correlation_id=correlation_id,
            execution_id=execution_id_str,
            task_id=task_id_str,
            runner_id=execution.runner_id,
            phase=phase.value,
            error_type=error_type.value,
        )

        # Calculate retry decision
        retry_decision = calculate_retry_decision(
            execution, error_type, phase, self.retry_matrix
        )

        # Determine recovery action
        if retry_decision.retry_exhausted:
            # Retry exhausted or not retryable
            if error_type == ErrorType.CONFLICT:
                log_phase_event(
                    obs_logger,
                    f"Conflict error requires manual intervention - marking for review",
                    correlation_id=correlation_id,
                    execution_id=execution_id_str,
                    task_id=task_id_str,
                    runner_id=execution.runner_id,
                    phase=phase.value,
                    level=logging.WARNING,
                )
                return RecoveryDecision(
                    action=RecoveryAction.REVIEW,
                    reason=f"Conflict error requires manual intervention: {exception}",
                    error_type=error_type,
                    phase=phase,
                    should_update_status=True,
                    new_status=ExecutionStatus.REVIEW,
                )
            else:
                log_phase_event(
                    obs_logger,
                    f"Recovery exhausted - marking as failed: {retry_decision.reason}",
                    correlation_id=correlation_id,
                    execution_id=execution_id_str,
                    task_id=task_id_str,
                    runner_id=execution.runner_id,
                    phase=phase.value,
                    level=logging.ERROR,
                )
                record_retry_exhausted()
                return RecoveryDecision(
                    action=RecoveryAction.FAILED,
                    reason=f"Recovery exhausted: {retry_decision.reason}",
                    error_type=error_type,
                    phase=phase,
                    should_update_status=True,
                    new_status=ExecutionStatus.FAILED,
                )
        elif retry_decision.should_retry:
            # Schedule retry
            execution.attempt = retry_decision.next_attempt
            execution.next_retry_at = retry_decision.next_retry_at

            log_phase_event(
                obs_logger,
                f"Scheduling retry: {retry_decision.reason}",
                correlation_id=correlation_id,
                execution_id=execution_id_str,
                task_id=task_id_str,
                runner_id=execution.runner_id,
                phase=phase.value,
                next_retry_at=retry_decision.next_retry_at.isoformat(),
                attempt=execution.attempt,
            )
            record_retry_scheduled()

            return RecoveryDecision(
                action=RecoveryAction.RETRY,
                reason=retry_decision.reason,
                error_type=error_type,
                phase=phase,
                next_retry_at=retry_decision.next_retry_at,
            )
        else:
            # Observe only
            return RecoveryDecision(
                action=RecoveryAction.OBSERVE,
                reason="Error logged but no action required",
                error_type=error_type,
                phase=phase,
            )

    def handle_stale_execution(
        self,
        session: Session,
        execution: TaskExecution,
    ) -> RecoveryDecision:
        """Handle a stale execution.

        Per REQ-012-09: Stale Executions bleiben nicht dauerhaft hängen.
        Per REQ-012-10: Logs with correlation ID and structured format.

        Args:
            session: Database session
            execution: The stale TaskExecution

        Returns:
            RecoveryDecision with recommended action
        """
        correlation_id = execution.correlation_id or "unknown"
        execution_id_str = str(execution.id)
        task_id_str = str(execution.task_id)
        phase = RunnerPhase(execution.phase) if execution.phase else RunnerPhase.STREAM

        # Log stale detection
        log_phase_event(
            obs_logger,
            f"Stale execution detected - phase: {phase.value}",
            correlation_id=correlation_id,
            execution_id=execution_id_str,
            task_id=task_id_str,
            runner_id=execution.runner_id,
            phase=phase.value,
            level=logging.WARNING,
            heartbeat_at=execution.heartbeat_at.isoformat() if execution.heartbeat_at else None,
            updated_at=execution.updated_at.isoformat(),
            started_at=execution.started_at.isoformat() if execution.started_at else None,
        )
        record_stale_detection()

        # Check if it's a write-task that might need revalidation
        if execution.phase == "adopting_commit":
            log_phase_event(
                obs_logger,
                "Stale during commit adoption - revalidate",
                correlation_id=correlation_id,
                execution_id=execution_id_str,
                task_id=task_id_str,
                runner_id=execution.runner_id,
                phase=phase.value,
            )
            record_adoption_conflict()
            return RecoveryDecision(
                action=RecoveryAction.REVALIDATE_ADOPTION,
                reason="Stale during commit adoption - revalidate",
                error_type=ErrorType.TRANSIENT,
                phase=phase,
            )

        # For other phases, check if retry is possible
        error_type = ErrorType.TRANSIENT  # Stale is treated as transient
        retry_decision = calculate_retry_decision(execution, error_type, phase)

        if retry_decision.should_retry:
            execution.attempt = retry_decision.next_attempt
            execution.next_retry_at = retry_decision.next_retry_at
            log_phase_event(
                obs_logger,
                f"Stale execution - scheduling retry: {retry_decision.reason}",
                correlation_id=correlation_id,
                execution_id=execution_id_str,
                task_id=task_id_str,
                runner_id=execution.runner_id,
                phase=phase.value,
                next_retry_at=retry_decision.next_retry_at.isoformat(),
            )
            record_retry_scheduled()
            return RecoveryDecision(
                action=RecoveryAction.RETRY,
                reason=f"Stale execution - scheduling retry: {retry_decision.reason}",
                error_type=error_type,
                phase=phase,
                next_retry_at=retry_decision.next_retry_at,
            )
        else:
            log_phase_event(
                obs_logger,
                f"Stale execution - retry exhausted: {retry_decision.reason}",
                correlation_id=correlation_id,
                execution_id=execution_id_str,
                task_id=task_id_str,
                runner_id=execution.runner_id,
                phase=phase.value,
                level=logging.ERROR,
            )
            record_retry_exhausted()
            return RecoveryDecision(
                action=RecoveryAction.FAILED,
                reason=f"Stale execution - retry exhausted: {retry_decision.reason}",
                error_type=error_type,
                phase=phase,
                should_update_status=True,
                new_status=ExecutionStatus.FAILED,
            )

    def process_stale_executions(self, session: Session) -> int:
        """Process all stale executions.

        Args:
            session: Database session

        Returns:
            Number of executions processed
        """
        stale_executions = find_stale_executions(
            session, self.stale_thresholds
        )
        processed = 0

        for execution in stale_executions:
            try:
                decision = self.handle_stale_execution(session, execution)
                self._apply_recovery_decision(session, execution, decision)
                processed += 1
                logger.info(
                    f"Processed stale execution {execution.id}: {decision.action.value}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to process stale execution {execution.id}: {e}",
                    exc_info=True,
                )

        return processed

    def _apply_recovery_decision(
        self,
        session: Session,
        execution: TaskExecution,
        decision: RecoveryDecision,
    ):
        """Apply a recovery decision to an execution.

        Args:
            session: Database session
            execution: The TaskExecution to update
            decision: The recovery decision
        """
        # Create recovery event
        event_type = {
            RecoveryAction.RETRY: EventType.RETRY_SCHEDULED,
            RecoveryAction.RETRY_EXHAUSTED: EventType.RETRY_EXHAUSTED,
            RecoveryAction.FAILED: EventType.EXECUTION_FAILED,
            RecoveryAction.REVIEW: EventType.EXECUTION_FAILED,
            RecoveryAction.REVALIDATE_ADOPTION: EventType.COMMIT_ADOPTION_CONFLICT,
        }.get(decision.action, EventType.STATUS_UPDATE)

        event = TaskExecutionEvent(
            task_execution_id=execution.id,
            sequence=execution.events[-1].sequence + 1 if execution.events else 1,
            external_event_id=None,
            direction="outbound",
            event_type=event_type.value,
            payload={
                "action": decision.action.value,
                "reason": decision.reason,
                "error_type": decision.error_type.value,
                "phase": decision.phase.value,
            },
            correlation_id=execution.correlation_id,
        )
        session.add(event)

        # Update execution status if needed
        if decision.should_update_status and decision.new_status:
            execution.status = decision.new_status.value
            if decision.new_status == ExecutionStatus.FAILED:
                execution.finished_at = datetime.now(timezone.utc)
            elif decision.new_status == ExecutionStatus.REVIEW:
                execution.finished_at = datetime.now(timezone.utc)

        # Update next_retry_at if retry scheduled
        if decision.next_retry_at:
            execution.next_retry_at = decision.next_retry_at

        session.add(execution)
        session.commit()


# ============================================================================
# Write-Task Recovery with Git Pre-Check
# ============================================================================


class WriteTaskRecovery:
    """Recovery service for write-tasks with Git pre-checks.

    Per REQ-012-09: Write-Task-Retry nur nach Vorprüfung:
    - Task-Worktree-Status
    - Zielbranch-Adoption
    - vorhandene Commits
    """

    def __init__(self, base_path: str = "."):
        """Initialize write-task recovery.

        Args:
            base_path: Base path for Git operations
        """
        self.base_path = Path(base_path)

    def check_worktree_status(
        self,
        execution: TaskExecution,
    ) -> dict[str, Any]:
        """Check the current state of the worktree.

        Args:
            execution: The TaskExecution with worktree info

        Returns:
            Dict with worktree status information
        """
        if not GITPYTHON_AVAILABLE:
            logger.warning("GitPython not available - worktree checks disabled")
            return {
                "exists": False,
                "is_git_repo": False,
                "current_branch": None,
                "has_uncommitted_changes": False,
                "untracked_files": [],
                "ahead_behind": None,
                "gitpython_unavailable": True,
            }

        result = {
            "exists": False,
            "is_git_repo": False,
            "current_branch": None,
            "has_uncommitted_changes": False,
            "untracked_files": [],
            "ahead_behind": None,
        }

        if not execution.worktree_path:
            return result

        worktree_path = Path(execution.worktree_path)
        if not worktree_path.exists():
            return result

        result["exists"] = True

        try:
            repo = git.Repo(worktree_path)
            result["is_git_repo"] = True
            result["current_branch"] = repo.active_branch.name

            # Check for uncommitted changes
            if repo.is_dirty():
                result["has_uncommitted_changes"] = True

            # Check for untracked files
            result["untracked_files"] = repo.untracked_files

            # Check ahead/behind status
            try:
                branch = repo.active_branch
                remote = repo.remote("origin")
                ahead, behind = repo.ahead_behind(branch, remote.refs[branch.name])
                result["ahead_behind"] = {"ahead": ahead, "behind": behind}
            except Exception:
                pass

        except git.InvalidGitRepositoryError:
            result["is_git_repo"] = False
        except Exception as e:
            logger.warning(f"Failed to check worktree status: {e}")

        return result

    def check_adoption_status(
        self,
        execution: TaskExecution,
        target_branch: str = "main",
    ) -> dict[str, Any]:
        """Check if changes have already been adopted to target branch.

        Args:
            execution: The TaskExecution
            target_branch: Target branch name

        Returns:
            Dict with adoption status information
        """
        if not GITPYTHON_AVAILABLE:
            logger.warning("GitPython not available - adoption checks disabled")
            return {
                "already_adopted": False,
                "adopted_commits": [],
                "conflict_detected": False,
                "gitpython_unavailable": True,
            }

        result = {
            "already_adopted": False,
            "adopted_commits": [],
            "conflict_detected": False,
        }

        if not execution.worktree_path or not execution.new_commit_shas:
            return result

        worktree_path = Path(execution.worktree_path)
        if not worktree_path.exists():
            return result

        try:
            repo = git.Repo(worktree_path)

            # Check if commits exist in target branch
            try:
                target = repo.branches[target_branch]
            except IndexError:
                # Target branch doesn't exist locally
                return result

            for commit_sha in execution.new_commit_shas:
                try:
                    commit = repo.commit(commit_sha)
                    # Check if commit is reachable from target branch
                    if commit in target.commit.ancestors() or commit.sha == target.commit.sha:
                        result["already_adopted"] = True
                        result["adopted_commits"].append(commit_sha)
                except git.BadName:
                    # Commit doesn't exist
                    pass

        except Exception as e:
            logger.warning(f"Failed to check adoption status: {e}")

        return result

    def validate_retry_safety(
        self,
        execution: TaskExecution,
        target_branch: str = "main",
    ) -> dict[str, Any]:
        """Validate whether it's safe to retry a write-task.

        Per REQ-012-09: Write-Task-Retry ist idempotent abgesichert.

        Args:
            execution: The TaskExecution to validate
            target_branch: Target branch name

        Returns:
            Dict with validation result and safety information
        """
        worktree_status = self.check_worktree_status(execution)
        adoption_status = self.check_adoption_status(execution, target_branch)

        validation = {
            "safe_to_retry": True,
            "warnings": [],
            "errors": [],
            "worktree_status": worktree_status,
            "adoption_status": adoption_status,
        }

        # Check for uncommitted changes
        if worktree_status["has_uncommitted_changes"]:
            validation["warnings"].append(
                "Worktree has uncommitted changes - retry may lose changes"
            )

        # Check for conflicts
        if adoption_status["already_adopted"]:
            validation["warnings"].append(
                f"Commits already adopted: {adoption_status['adopted_commits']}"
            )
            # If already adopted, retry might be unnecessary but not dangerous
            # unless there are conflicts

        # Check ahead/behind
        if worktree_status.get("ahead_behind"):
            ahead = worktree_status["ahead_behind"].get("ahead", 0)
            if ahead > 0:
                validation["warnings"].append(
                    f"Worktree is {ahead} commits ahead of remote"
                )

        # Check for untracked files that might conflict
        if worktree_status["untracked_files"]:
            validation["warnings"].append(
                f"Untracked files present: {len(worktree_status['untracked_files'])}"
            )

        # Determine if safe to retry
        if worktree_status["has_uncommitted_changes"]:
            # Not safe to retry without cleanup
            validation["safe_to_retry"] = False
            validation["errors"].append(
                "Uncommitted changes must be handled before retry"
            )

        return validation

    def cleanup_worktree(
        self,
        execution: TaskExecution,
        force: bool = False,
    ) -> dict[str, Any]:
        """Clean up worktree before retry.

        Args:
            execution: The TaskExecution
            force: Force cleanup even with uncommitted changes

        Returns:
            Dict with cleanup result
        """
        if not GITPYTHON_AVAILABLE:
            return {
                "success": False,
                "actions_taken": [],
                "errors": ["GitPython not available - cleanup disabled"],
                "gitpython_unavailable": True,
            }

        result = {
            "success": False,
            "actions_taken": [],
            "errors": [],
        }

        if not execution.worktree_path:
            result["errors"].append("No worktree path specified")
            return result

        worktree_path = Path(execution.worktree_path)
        if not worktree_path.exists():
            result["success"] = True
            result["actions_taken"].append("Worktree does not exist - nothing to clean")
            return result

        try:
            repo = git.Repo(worktree_path)

            # Check for uncommitted changes
            if repo.is_dirty() and not force:
                result["errors"].append(
                    "Worktree has uncommitted changes - use force=True to discard"
                )
                return result

            # Discard uncommitted changes
            if repo.is_dirty():
                repo.git.reset("--hard")
                result["actions_taken"].append("Discarded uncommitted changes")

            # Clean untracked files
            if repo.untracked_files:
                for file in repo.untracked_files:
                    file_path = worktree_path / file
                    if file_path.exists():
                        file_path.unlink()
                result["actions_taken"].append(
                    f"Removed {len(repo.untracked_files)} untracked files"
                )

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Cleanup failed: {e}")

        return result


# ============================================================================
# Recovery Event Helpers
# ============================================================================


def create_recovery_event(
    execution: TaskExecution,
    action: RecoveryAction,
    reason: str,
    error_type: ErrorType,
    phase: RunnerPhase,
    session: Session,
) -> TaskExecutionEvent:
    """Create a recovery event for persistence.

    Args:
        execution: The TaskExecution
        action: Recovery action taken
        reason: Reason for the action
        error_type: Classified error type
        phase: Runner phase
        session: Database session

    Returns:
        Created TaskExecutionEvent
    """
    sequence = (
        max([e.sequence for e in execution.events], default=0) + 1
        if execution.events
        else 1
    )

    event = TaskExecutionEvent(
        task_execution_id=execution.id,
        sequence=sequence,
        external_event_id=None,
        direction="outbound",
        event_type=EventType.RETRY_SCHEDULED.value
        if action == RecoveryAction.RETRY
        else EventType.RETRY_EXHAUSTED.value
        if action == RecoveryAction.FAILED
        else EventType.STATUS_UPDATE.value,
        payload={
            "action": action.value,
            "reason": reason,
            "error_type": error_type.value,
            "phase": phase.value,
            "attempt": execution.attempt,
            "max_attempts": execution.max_attempts,
        },
        correlation_id=execution.correlation_id,
    )

    session.add(event)
    return event
