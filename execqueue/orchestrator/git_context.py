"""Git context preparation for REQ-011 write tasks.

This module handles branch and worktree preparation for write tasks.
It implements safety guards against destructive operations and ensures
proper isolation between tasks.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from execqueue.orchestrator.models import PreparationError, PreparationErrorType

logger = logging.getLogger(__name__)


@dataclass
class GitContext:
    """Git context for a write task.
    
    Attributes:
        branch_name: Branch name for the task
        worktree_path: Path to worktree directory
        commit_sha_before: Commit SHA before preparation
        created: Whether this is a new context or reused
    """
    branch_name: str
    worktree_path: Path
    commit_sha_before: str
    created: bool = True


class GitContextPreparer:
    """Prepares Git context (branch/worktree) for write tasks.
    
    Safety invariants:
    - No destructive Git commands
    - No overwriting existing branches
    - No worktree outside configured root
    - Reuse only if worktree belongs to this task and is clean
    """
    
    # Default branch naming pattern
    BRANCH_PREFIX = "execqueue/task"
    
    # Valid ref character pattern (simplified Git ref rules)
    VALID_REF_PATTERN = re.compile(r'^[a-zA-Z0-9_\-/]+$')
    
    def __init__(
        self,
        worktree_root: Path,
        base_repo_path: Path,
        timeout_seconds: int = 30,
    ):
        """Initialize Git context preparer.
        
        Args:
            worktree_root: Root directory for worktrees
            base_repo_path: Path to base repository
            timeout_seconds: Timeout for Git commands
        """
        self.worktree_root = worktree_root.resolve()
        self.base_repo_path = base_repo_path.resolve()
        self.timeout_seconds = timeout_seconds
        
        # Ensure worktree root exists
        self.worktree_root.mkdir(parents=True, exist_ok=True)
    
    def _run_git_command(
        self,
        args: list[str],
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a Git command with timeout.
        
        Args:
            args: Git command arguments (without 'git')
            cwd: Working directory
            check: Raise on non-zero exit
            
        Returns:
            Completed process
            
        Raises:
            PreparationError: On command failure
        """
        cmd = ["git"] + args
        cwd = cwd or self.base_repo_path
        
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=check,
            )
            return result
        except subprocess.TimeoutExpired as e:
            raise PreparationError(
                error_type=PreparationErrorType.RECOVERABLE,
                message=f"Git command timed out: {' '.join(cmd)}",
                task_id=UUID(int=0),  # Will be set by caller
                details={"command": cmd, "timeout": self.timeout_seconds},
            )
        except subprocess.CalledProcessError as e:
            if check:
                raise PreparationError(
                    error_type=PreparationErrorType.NON_RECOVERABLE,
                    message=f"Git command failed: {' '.join(cmd)}",
                    task_id=UUID(int=0),
                    details={
                        "command": cmd,
                        "returncode": e.returncode,
                        "stderr": e.stderr,
                    },
                )
            return e
    
    def _validate_ref_name(self, name: str) -> bool:
        """Validate Git ref name.
        
        Args:
            name: Ref name to validate
            
        Returns:
            True if valid
        """
        if not name or len(name) > 255:
            return False
        if not self.VALID_REF_PATTERN.match(name):
            return False
        if name.startswith("/") or name.endswith("/"):
            return False
        if ".." in name:
            return False
        return True
    
    def _validate_path_within_root(self, path: Path) -> bool:
        """Validate path is within worktree root.
        
        Args:
            path: Path to validate
            
        Returns:
            True if within root
        """
        try:
            resolved = path.resolve()
            return str(resolved).startswith(str(self.worktree_root))
        except (OSError, ValueError):
            return False
    
    def _generate_branch_name(self, task_number: int, task_id: UUID) -> str:
        """Generate deterministic branch name for task.
        
        Args:
            task_number: Task number
            task_id: Task UUID
            
        Returns:
            Valid branch name
        """
        short_id = task_id.hex[:8]
        branch_name = f"{self.BRANCH_PREFIX}-{task_number}-{short_id}"
        
        # Validate and sanitize
        if not self._validate_ref_name(branch_name):
            # Fallback to safer name
            branch_name = f"{self.BRANCH_PREFIX}-{task_number}"
        
        return branch_name
    
    def _get_current_commit(self) -> str:
        """Get current commit SHA.
        
        Returns:
            Commit SHA
            
        Raises:
            PreparationError: On failure
        """
        result = self._run_git_command(["rev-parse", "HEAD"])
        return result.stdout.strip()
    
    def _branch_exists(self, branch_name: str) -> bool:
        """Check if branch exists.
        
        Args:
            branch_name: Branch name
            
        Returns:
            True if exists
        """
        try:
            self._run_git_command(["rev-parse", "--verify", branch_name])
            return True
        except PreparationError:
            return False
    
    def _worktree_exists(self, path: Path) -> bool:
        """Check if worktree exists and is valid.
        
        Args:
            path: Worktree path
            
        Returns:
            True if valid worktree
        """
        if not path.exists():
            return False
        
        # Check if it's a valid git worktree
        git_dir = path / ".git"
        return git_dir.exists() or (path / ".git").is_file()
    
    def _is_worktree_clean(self, path: Path) -> bool:
        """Check if worktree has no uncommitted changes.
        
        Args:
            path: Worktree path
            
        Returns:
            True if clean
        """
        try:
            result = self._run_git_command(
                ["status", "--porcelain"],
                cwd=path,
                check=False,
            )
            return not result.stdout.strip()
        except PreparationError:
            return False
    
    def prepare_context(
        self,
        task_id: UUID,
        task_number: int,
        explicit_branch: str | None = None,
        reuse_existing: bool = True,
    ) -> GitContext:
        """Prepare Git context for a write task.
        
        Args:
            task_id: Task UUID
            task_number: Task number
            explicit_branch: Optional explicit branch name
            reuse_existing: Whether to reuse existing worktree
            
        Returns:
            GitContext with branch/worktree info
            
        Raises:
            PreparationError: On failure
        """
        # Determine branch name
        if explicit_branch:
            if not self._validate_ref_name(explicit_branch):
                raise PreparationError(
                    error_type=PreparationErrorType.NON_RECOVERABLE,
                    message=f"Invalid branch name: {explicit_branch}",
                    task_id=task_id,
                )
            branch_name = explicit_branch
        else:
            branch_name = self._generate_branch_name(task_number, task_id)
        
        # Check branch exists
        if self._branch_exists(branch_name):
            logger.info("Branch %s already exists, using it", branch_name)
        else:
            # Create branch from current HEAD
            try:
                self._run_git_command(["checkout", "-b", branch_name])
                logger.info("Created branch %s", branch_name)
            except PreparationError as e:
                # Try checking out existing branch if creation fails
                try:
                    self._run_git_command(["checkout", branch_name])
                    logger.info("Checked out existing branch %s", branch_name)
                except PreparationError:
                    raise PreparationError(
                        error_type=PreparationErrorType.CONFLICT,
                        message=f"Cannot create or checkout branch {branch_name}",
                        task_id=task_id,
                    )
        
        # Get commit SHA
        commit_sha = self._get_current_commit()
        
        # Determine worktree path
        worktree_name = f"task-{task_number}-{task_id.hex[:8]}"
        worktree_path = self.worktree_root / worktree_name
        
        # Handle worktree
        created_worktree = True
        if worktree_path.exists() and reuse_existing:
            # Check if it belongs to this task (by naming convention)
            # and is clean
            if self._is_worktree_clean(worktree_path):
                logger.info("Reusing existing worktree %s", worktree_path)
                created_worktree = False
            else:
                # Worktree is dirty - this is a conflict
                raise PreparationError(
                    error_type=PreparationErrorType.CONFLICT,
                    message=f"Worktree {worktree_path} exists but is dirty",
                    task_id=task_id,
                    details={"path": str(worktree_path)},
                )
        
        if created_worktree or not worktree_path.exists():
            # Create new worktree
            try:
                self._run_git_command(
                    ["worktree", "add", str(worktree_path), branch_name],
                )
                logger.info("Created worktree %s for branch %s", worktree_path, branch_name)
            except PreparationError as e:
                # Worktree might exist - try to use it
                if worktree_path.exists():
                    logger.warning("Worktree exists, attempting to use it: %s", worktree_path)
                else:
                    raise
        
        # Validate worktree path is within root
        if not self._validate_path_within_root(worktree_path):
            raise PreparationError(
                error_type=PreparationErrorType.NON_RECOVERABLE,
                message=f"Worktree path {worktree_path} is outside root {self.worktree_root}",
                task_id=task_id,
            )
        
        return GitContext(
            branch_name=branch_name,
            worktree_path=worktree_path,
            commit_sha_before=commit_sha,
            created=created_worktree,
        )
    
    def cleanup_worktree(self, task_id: UUID, worktree_path: Path) -> bool:
        """Clean up a worktree.
        
        Args:
            task_id: Task UUID (for logging)
            worktree_path: Path to worktree
            
        Returns:
            True if successful
        """
        if not worktree_path.exists():
            return True
        
        try:
            # Remove worktree
            self._run_git_command(
                ["worktree", "remove", "--force", str(worktree_path)],
                check=False,
            )
            logger.info("Removed worktree %s", worktree_path)
            return True
        except PreparationError as e:
            logger.warning("Failed to remove worktree %s: %s", worktree_path, e)
            return False
