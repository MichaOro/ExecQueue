"""Commit adoption for target branch validation.

This module implements REQ-012-08:
- Safely adopt commits from task worktree to target branch
- Cherry-pick with conflict detection
- Validation before allowing done status
- Idempotency checks for retry
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from execqueue.models.enums import ExecutionStatus, EventType
from execqueue.orchestrator.models import RunnerMode
from execqueue.models.task_execution import TaskExecution
from execqueue.observability import (
    record_cherry_pick_attempt,
    record_cherry_pick_success,
    record_adoption_conflict,
)

logger = logging.getLogger(__name__)


@dataclass
class AdoptionResult:
    """Result of commit adoption.

    Attributes:
        success: Whether adoption succeeded
        adopted_commit_sha: SHA of commit in target branch (may differ from source)
        original_commit_sha: Original commit SHA from task worktree
        conflict_detected: Whether cherry-pick conflict occurred
        validation_passed: Whether validation commands passed
        target_branch_head: HEAD of target branch after adoption
        error_message: Error details if failed
        needs_review: Whether manual review is required
    """
    success: bool = False
    adopted_commit_sha: str | None = None
    original_commit_sha: str | None = None
    conflict_detected: bool = False
    validation_passed: bool = False
    target_branch_head: str | None = None
    error_message: str | None = None
    needs_review: bool = False


class CommitAdopter:
    """Adopts commits from task worktree to target branch.

    This class implements the commit adoption logic for REQ-012-08:
    - Cherry-pick commits from task branch to target branch
    - Detect and handle conflicts
    - Run validation commands
    - Ensure idempotency on retry
    """

    def __init__(
        self,
        target_worktree_path: str,
        target_branch: str,
        task_worktree_path: str,
        task_commit_sha: str,
        validation_commands: list[str] | None = None,
    ):
        """Initialize commit adopter.

        Args:
            target_worktree_path: Path to target branch worktree
            target_branch: Name of target branch (e.g., "main", "develop")
            task_worktree_path: Path to task worktree with commit
            task_commit_sha: SHA of commit to adopt
            validation_commands: Optional list of commands to run after adoption
        """
        self.target_worktree_path = Path(target_worktree_path).resolve()
        self.target_branch = target_branch
        self.task_worktree_path = Path(task_worktree_path).resolve()
        self.task_commit_sha = task_commit_sha
        self.validation_commands = validation_commands or []

    def _run_git_command(
        self,
        args: list[str],
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a Git command.

        Args:
            args: Git command arguments (without 'git')
            cwd: Working directory
            check: Raise on non-zero exit

        Returns:
            Completed process
        """
        cmd = ["git"] + args
        cwd = cwd or self.target_worktree_path

        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
                check=check,
            )
            return result
        except subprocess.TimeoutExpired as e:
            logger.error(f"Git command timed out: {' '.join(cmd)}")
            raise
        except subprocess.CalledProcessError as e:
            if check:
                logger.error(f"Git command failed: {' '.join(cmd)} - {e.stderr}")
            return e

    def _is_target_branch_clean(self) -> bool:
        """Check if target branch worktree is clean.

        Returns:
            True if no uncommitted changes
        """
        try:
            result = self._run_git_command(
                ["status", "--porcelain"],
                check=False,
            )
            return not result.stdout.strip()
        except Exception:
            return False

    def _get_current_target_head(self) -> str | None:
        """Get current HEAD of target branch.

        Returns:
            Commit SHA or None
        """
        try:
            result = self._run_git_command(
                ["rev-parse", "HEAD"],
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def _is_commit_already_adopted(self) -> bool:
        """Check if the commit is already in target branch.

        Uses git log to check if the original commit (or a cherry-pick
        with same message/pattern) exists in target branch.

        Returns:
            True if commit already adopted
        """
        try:
            # Check if exact SHA exists in target branch
            result = self._run_git_command(
                ["merge-base", "--is-ancestor", self.task_commit_sha, "HEAD"],
                check=False,
            )
            if result.returncode == 0:
                logger.info(f"Commit {self.task_commit_sha} already in target branch")
                return True

            # Check by commit message (for idempotency on retry)
            result = self._run_git_command(
                ["log", "--oneline", "HEAD"],
                check=False,
            )
            if result.returncode == 0:
                # Look for commit message pattern
                log_output = result.stdout
                if self.task_commit_sha[:8] in log_output:
                    logger.info(f"Commit {self.task_commit_sha} appears already adopted")
                    return True

            return False
        except Exception:
            return False

    def _checkout_target_branch(self) -> bool:
        """Checkout target branch in target worktree.

        Returns:
            True if successful
        """
        try:
            # Fetch latest from remote if available
            self._run_git_command(
                ["fetch", "origin", self.target_branch],
                check=False,
            )

            # Checkout target branch
            result = self._run_git_command(
                ["checkout", self.target_branch],
                check=False,
            )

            if result.returncode != 0:
                # Try pulling instead
                result = self._run_git_command(
                    ["pull", "origin", self.target_branch],
                    check=False,
                )
                if result.returncode != 0:
                    logger.error(f"Failed to checkout/pull {self.target_branch}")
                    return False

            # Pull to get latest
            self._run_git_command(
                ["pull", "origin", self.target_branch],
                check=False,
            )

            return True
        except Exception as e:
            logger.error(f"Error checking out target branch: {e}")
            return False

    def _run_validation_commands(self) -> bool:
        """Run validation commands after adoption.

        Returns:
            True if all commands passed
        """
        if not self.validation_commands:
            return True  # No validation required

        for cmd in self.validation_commands:
            try:
                logger.info(f"Running validation command: {cmd}")
                result = subprocess.run(
                    cmd,
                    cwd=str(self.target_worktree_path),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    shell=True,  # Allow shell commands
                )

                if result.returncode != 0:
                    logger.error(
                        f"Validation command failed: {cmd}\n{result.stderr}"
                    )
                    return False

                logger.info(f"Validation command succeeded: {cmd}")
            except subprocess.TimeoutExpired:
                logger.error(f"Validation command timed out: {cmd}")
                return False
            except Exception as e:
                logger.error(f"Error running validation command {cmd}: {e}")
                return False

        return True

    def adopt(self) -> AdoptionResult:
        """Perform commit adoption.

        Returns:
            AdoptionResult with adoption status and metadata
        """
        result = AdoptionResult(
            original_commit_sha=self.task_commit_sha,
        )

        # Step 1: Check if target worktree is clean
        if not self._is_target_branch_clean():
            result.error_message = "Target worktree has uncommitted changes"
            result.needs_review = True
            logger.warning(result.error_message)
            return result

        # Step 2: Check if commit already adopted (idempotency)
        if self._is_commit_already_adopted():
            logger.info(f"Commit {self.task_commit_sha} already adopted, skipping")
            result.success = True
            result.adopted_commit_sha = self.task_commit_sha
            result.validation_passed = True
            result.target_branch_head = self._get_current_target_head()
            return result

        # Step 3: Checkout target branch
        if not self._checkout_target_branch():
            result.error_message = "Failed to checkout target branch"
            result.needs_review = True
            return result

        # Step 4: Store target HEAD before cherry-pick
        target_head_before = self._get_current_target_head()

        # Step 5: Cherry-pick the commit
        logger.info(
            f"Cherry-picking commit {self.task_commit_sha} to {self.target_branch}"
        )
        
        # Record metrics
        record_cherry_pick_attempt()

        cherry_pick_result = self._run_git_command(
            ["cherry-pick", self.task_commit_sha],
            check=False,
        )

        if cherry_pick_result.returncode != 0:
            # Check if it's a conflict
            status_result = self._run_git_command(
                ["status", "--porcelain"],
                check=False,
            )

            if "conflict" in status_result.stdout.lower() or cherry_pick_result.returncode != 0:
                result.conflict_detected = True
                result.error_message = f"Cherry-pick conflict: {cherry_pick_result.stderr}"
                result.needs_review = True

                # Abort cherry-pick to leave clean state
                self._run_git_command(
                    ["cherry-pick", "--abort"],
                    check=False,
                )

                logger.warning(result.error_message)
                
                # Record metrics
                record_adoption_conflict()
                
                return result

            result.error_message = f"Cherry-pick failed: {cherry_pick_result.stderr}"
            result.needs_review = True
            return result

        # Step 6: Get adopted commit SHA
        adopted_sha = self._get_current_target_head()
        result.adopted_commit_sha = adopted_sha

        # Step 7: Run validation commands
        if self.validation_commands:
            result.validation_passed = self._run_validation_commands()
            if not result.validation_passed:
                result.error_message = "Validation commands failed"
                result.needs_review = True
                # Note: We don't revert the commit - it's already in the branch
                # but mark as needing review
                return result
        else:
            result.validation_passed = True

        # Step 8: Verify adoption
        final_head = self._get_current_target_head()
        result.target_branch_head = final_head

        if final_head and final_head != target_head_before:
            result.success = True
            logger.info(
                f"Successfully adopted commit {self.task_commit_sha} "
                f"as {adopted_sha} in {self.target_branch}"
            )
            # Record metrics
            record_cherry_pick_success()
        else:
            result.error_message = "Adoption verification failed: HEAD unchanged"
            result.needs_review = True

        return result


async def adopt_commit(
    target_worktree_path: str,
    target_branch: str,
    task_worktree_path: str,
    task_commit_sha: str,
    validation_commands: list[str] | None = None,
) -> AdoptionResult:
    """Convenience function to adopt a commit.

    Args:
        target_worktree_path: Path to target branch worktree
        target_branch: Name of target branch
        task_worktree_path: Path to task worktree
        task_commit_sha: SHA of commit to adopt
        validation_commands: Optional validation commands

    Returns:
        AdoptionResult
    """
    adopter = CommitAdopter(
        target_worktree_path=target_worktree_path,
        target_branch=target_branch,
        task_worktree_path=task_worktree_path,
        task_commit_sha=task_commit_sha,
        validation_commands=validation_commands,
    )
    return adopter.adopt()


async def adopt_commit_with_lifecycle(
    session: Session,
    execution: TaskExecution,
    target_worktree_path: str,
    target_branch: str,
    validation_commands: list[str] | None = None,
) -> AdoptionResult:
    """Adopt commit with full lifecycle tracking per REQ-021 Section 5.

    This function:
    1. Updates execution status to ADOPTING_COMMIT
    2. Sets adoption_status to in_progress
    3. Performs the adoption
    4. Updates execution based on result (success, failed, review)
    5. Persists adoption_status and adoption_error

    Args:
        session: Database session
        execution: TaskExecution to update
        target_worktree_path: Path to target branch worktree
        target_branch: Name of target branch
        validation_commands: Optional validation commands

    Returns:
        AdoptionResult with adoption status
    """
    from execqueue.runner.commit_adopter import CommitAdopter

    logger.info(
        f"Starting commit adoption for execution {execution.id}",
        extra={
            "execution_id": str(execution.id),
            "task_id": str(execution.task_id),
            "commit_sha": execution.commit_sha_after,
        }
    )

    # Step 1: Update status to ADOPTING_COMMIT
    execution.status = ExecutionStatus.ADOPTING_COMMIT.value
    execution.adoption_status = "in_progress"
    session.commit()

    # Step 2: Create adopter and perform adoption
    if not execution.commit_sha_after:
        result = AdoptionResult(
            success=False,
            error_message="No commit SHA available for adoption",
            needs_review=True,
        )
        execution.adoption_status = "failed"
        execution.adoption_error = result.error_message
        session.commit()
        return result

    adopter = CommitAdopter(
        target_worktree_path=target_worktree_path,
        target_branch=target_branch,
        task_worktree_path=execution.worktree_path or "",
        task_commit_sha=execution.commit_sha_after,
        validation_commands=validation_commands,
    )

    result = adopter.adopt()

    # Step 3: Update execution based on result
    execution.adopted_commit_sha = result.adopted_commit_sha

    if result.success and result.validation_passed:
        execution.status = ExecutionStatus.DONE.value
        execution.adoption_status = "success"
        execution.adoption_error = None
        logger.info(
            f"Commit adoption succeeded for execution {execution.id}",
            extra={
                "execution_id": str(execution.id),
                "adopted_sha": result.adopted_commit_sha,
            }
        )

    elif result.conflict_detected or result.needs_review:
        execution.status = ExecutionStatus.REVIEW.value
        execution.adoption_status = "review"
        execution.adoption_error = result.error_message
        logger.warning(
            f"Commit adoption requires review for execution {execution.id}",
            extra={
                "execution_id": str(execution.id),
                "reason": result.error_message,
            }
        )

    else:
        execution.status = ExecutionStatus.FAILED.value
        execution.adoption_status = "failed"
        execution.adoption_error = result.error_message
        logger.error(
            f"Commit adoption failed for execution {execution.id}",
            extra={
                "execution_id": str(execution.id),
                "error": result.error_message,
            }
        )

    session.commit()

    return result
