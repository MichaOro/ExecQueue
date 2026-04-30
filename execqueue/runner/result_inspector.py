"""Result inspection for Task Worktree after OpenCode execution.

This module implements REQ-012-07:
- Detect new commits, changed files, uncommitted changes
- Validate changes against allowed paths
- Detect read-only violations
- Persist result metadata
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from execqueue.models.enums import ExecutionStatus, EventType
from execqueue.orchestrator.models import RunnerMode

logger = logging.getLogger(__name__)


@dataclass
class InspectionResult:
    """Result of worktree inspection.

    Attributes:
        commit_sha_after: Current HEAD commit SHA
        new_commit_shas: List of new commit SHAs since baseline
        changed_files: List of changed file paths
        diff_stat: Diff statistics summary
        has_uncommitted_changes: Whether uncommitted changes exist
        inspection_status: Inspection status (passed, failed, review)
        read_only_violation: Whether read-only task has changes
        out_of_scope_changes: Changes outside allowed paths
        violation_details: Details about any violations
    """
    commit_sha_after: str | None = None
    new_commit_shas: list[str] | None = None
    changed_files: list[str] | None = None
    diff_stat: str | None = None
    has_uncommitted_changes: bool = False
    inspection_status: str = "passed"
    read_only_violation: bool = False
    out_of_scope_changes: bool = False
    violation_details: dict[str, Any] | None = None


class ResultInspector:
    """Inspects worktree state after OpenCode execution.

    This class implements the result inspection logic for REQ-012-07:
    - Compares current state against baseline (commit_sha_before)
    - Detects new commits, changed files, uncommitted changes
    - Validates changes against allowed paths
    - Detects read-only violations
    """

    def __init__(
        self,
        worktree_path: str,
        commit_sha_before: str | None = None,
        allowed_paths: list[str] | None = None,
        runner_mode: RunnerMode = RunnerMode.WRITE,
    ):
        """Initialize result inspector.

        Args:
            worktree_path: Path to the task worktree
            commit_sha_before: Baseline commit SHA before execution
            allowed_paths: List of allowed file paths/patterns
            runner_mode: Read-only or write mode
        """
        self.worktree_path = Path(worktree_path).resolve()
        self.commit_sha_before = commit_sha_before
        self.allowed_paths = allowed_paths or []
        self.runner_mode = runner_mode

    def _run_git_command(
        self,
        args: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a Git command in the worktree.

        Args:
            args: Git command arguments (without 'git')
            check: Raise on non-zero exit

        Returns:
            Completed process
        """
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.worktree_path),
                capture_output=True,
                text=True,
                timeout=30,
                check=check,
            )
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"Git command timed out: {' '.join(cmd)}")
            raise
        except subprocess.CalledProcessError as e:
            if check:
                logger.error(f"Git command failed: {' '.join(cmd)} - {e.stderr}")
                raise
            return e

    def _get_current_commit(self) -> str | None:
        """Get current HEAD commit SHA.

        Returns:
            Commit SHA or None if not a git repo
        """
        try:
            result = self._run_git_command(["rev-parse", "HEAD"], check=False)
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def _get_new_commits(self) -> list[str]:
        """Get list of new commits since baseline.

        Returns:
            List of commit SHAs (newest first)
        """
        if not self.commit_sha_before:
            return []

        try:
            result = self._run_git_command(
                ["rev-list", f"{self.commit_sha_before}..HEAD"],
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                commits = result.stdout.strip().split("\n")
                # Return newest first (already in that order from git)
                return commits
            return []
        except Exception:
            return []

    def _get_changed_files(self) -> list[str]:
        """Get list of all changed files (committed and uncommitted).

        Returns:
            List of changed file paths
        """
        changed = set()

        # Get changed files in new commits
        if self.commit_sha_before:
            try:
                result = self._run_git_command(
                    ["diff", "--name-only", f"{self.commit_sha_before}..HEAD"],
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    changed.update(result.stdout.strip().split("\n"))
            except Exception:
                pass

        # Get uncommitted changed files
        try:
            result = self._run_git_command(
                ["status", "--porcelain"],
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    # Extract file path from porcelain status
                    parts = line[3:].strip().split()
                    if parts:
                        changed.add(parts[0])
        except Exception:
            pass

        return sorted(changed)

    def _get_diff_stat(self) -> str | None:
        """Get diff statistics summary.

        Returns:
            Diff stat string or None
        """
        if not self.commit_sha_before:
            return None

        try:
            result = self._run_git_command(
                ["diff", "--stat", self.commit_sha_before],
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def _has_uncommitted_changes(self) -> bool:
        """Check if worktree has uncommitted changes.

        Returns:
            True if there are uncommitted changes
        """
        try:
            result = self._run_git_command(
                ["status", "--porcelain"],
                check=False,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def _normalize_path(self, path: str) -> str:
        """Normalize path for cross-platform comparison.

        Args:
            path: Path to normalize

        Returns:
            Normalized path with forward slashes
        """
        return path.replace("\\", "/").lstrip("/")

    def _is_path_allowed(self, path: str) -> bool:
        """Check if path is within allowed paths.

        Args:
            path: Path to check

        Returns:
            True if path is allowed
        """
        if not self.allowed_paths:
            return True  # No restrictions

        normalized_path = self._normalize_path(path)

        for allowed in self.allowed_paths:
            normalized_allowed = self._normalize_path(allowed)
            if normalized_path.startswith(normalized_allowed):
                return True

        return False

    def _check_out_of_scope_changes(self, changed_files: list[str]) -> tuple[bool, list[str]]:
        """Check if any changed files are outside allowed scope.

        Args:
            changed_files: List of changed file paths

        Returns:
            Tuple of (has_out_of_scope, list_of_violations)
        """
        if not self.allowed_paths:
            return False, []

        violations = []
        for file_path in changed_files:
            if not self._is_path_allowed(file_path):
                violations.append(file_path)

        return len(violations) > 0, violations

    def inspect(self) -> InspectionResult:
        """Perform full inspection of worktree state.

        Returns:
            InspectionResult with all metadata
        """
        # Gather state information
        commit_sha_after = self._get_current_commit()
        new_commit_shas = self._get_new_commits()
        changed_files = self._get_changed_files()
        diff_stat = self._get_diff_stat()
        has_uncommitted = self._has_uncommitted_changes()

        # Initialize result
        result = InspectionResult(
            commit_sha_after=commit_sha_after,
            new_commit_shas=new_commit_shas if new_commit_shas else None,
            changed_files=changed_files if changed_files else None,
            diff_stat=diff_stat,
            has_uncommitted_changes=has_uncommitted,
        )

        # Check for read-only violations
        if self.runner_mode == RunnerMode.READ_ONLY:
            if changed_files or has_uncommitted:
                result.read_only_violation = True
                result.inspection_status = "failed"
                result.violation_details = {
                    "reason": "Read-only task has changes",
                    "changed_files": changed_files,
                    "has_uncommitted": has_uncommitted,
                }
                logger.warning(
                    f"Read-only violation detected: {len(changed_files)} files changed"
                )

        # Check for out-of-scope changes (write mode)
        if self.runner_mode == RunnerMode.WRITE and self.allowed_paths:
            out_of_scope, violations = self._check_out_of_scope_changes(changed_files)
            if out_of_scope:
                result.out_of_scope_changes = True
                if result.inspection_status == "passed":
                    result.inspection_status = "review"
                result.violation_details = result.violation_details or {}
                result.violation_details["out_of_scope_files"] = violations
                logger.warning(
                    f"Out-of-scope changes detected: {violations}"
                )

        # Check for missing commits (write mode should have commits)
        if self.runner_mode == RunnerMode.WRITE:
            if not new_commit_shas and not changed_files:
                # No changes at all - possible failure
                if result.inspection_status == "passed":
                    result.inspection_status = "review"
                result.violation_details = result.violation_details or {}
                result.violation_details["reason"] = "No changes detected"
                logger.warning("No changes detected in write task")

        return result


async def inspect_task_result(
    worktree_path: str,
    commit_sha_before: str | None,
    runner_mode: RunnerMode,
    allowed_paths: list[str] | None = None,
) -> InspectionResult:
    """Convenience function to inspect task result.

    Args:
        worktree_path: Path to task worktree
        commit_sha_before: Baseline commit SHA
        runner_mode: Read-only or write mode
        allowed_paths: Optional list of allowed paths

    Returns:
        InspectionResult
    """
    inspector = ResultInspector(
        worktree_path=worktree_path,
        commit_sha_before=commit_sha_before,
        allowed_paths=allowed_paths,
        runner_mode=runner_mode,
    )
    return inspector.inspect()
