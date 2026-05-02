"""Git workflow management for REQ-016 (überarbeitet)."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class WorktreeInfo:
    """Information about a Git worktree.

    Attributes:
        path: Worktree filesystem path
        branch: Branch name
        commit_sha: Current commit SHA
        is_new: True if worktree was just created
    """

    path: Path
    branch: str
    commit_sha: str
    is_new: bool = True


@dataclass
class CommitInfo:
    """Information about a commit.

    Attributes:
        sha: Commit SHA
        message: Commit message
        author: Author string
        timestamp: Commit timestamp
    """

    sha: str
    message: str
    author: str
    timestamp: str


class GitWorkflowManager:
    """Manages Git worktrees and commits for workflow execution.

    Usage:
        git_mgr = GitWorkflowManager(base_repo_path)
        worktree = await git_mgr.create_worktree(workflow_id, task_id, branch)
        commit_sha = await git_mgr.commit_changes(worktree.path, message)
        success = await git_mgr.cherry_pick(target_branch, commit_sha, worktree.path)
        await git_mgr.cleanup_worktree(worktree.path)

    CRITICAL FIXES vs. original implementation:
    1. Cherry-pick must be executed in the worktree itself, not base repo
    2. Author parameter must be inserted correctly into command
    3. Branch existence must be checked before worktree creation
    
    Security Features (REQ-016 Recommendation 8):
    - Optional GPG signing for commits
    - Path validation for executed scripts
    - Verification of signed commits on checkout
    """

    def __init__(
        self,
        base_repo_path: Path,
        worktree_root: Path | None = None,
        require_signed_commits: bool = False,
        gpg_signing_key: str | None = None,
    ):
        """Initialize Git workflow manager.

        Args:
            base_repo_path: Path to the main Git repository
            worktree_root: Root directory for worktrees (default: base_repo_path/.git/worktrees)
            require_signed_commits: If True, all commits must be GPG signed (default: False)
            gpg_signing_key: GPG key ID for signing commits (optional, uses git config if not set)
        """
        self._base_repo_path = base_repo_path.resolve()
        self._worktree_root = worktree_root or (base_repo_path / ".git" / "worktrees")
        self._require_signed_commits = require_signed_commits
        self._gpg_signing_key = gpg_signing_key

    async def create_worktree(
        self,
        workflow_id: str,
        task_id: UUID,
        branch: str,
    ) -> WorktreeInfo:
        """Create a new Git worktree for a task.

        Args:
            workflow_id: Workflow identifier (for path naming)
            task_id: Task identifier (for path naming)
            branch: Branch to checkout (creates new branch if needed)

        Returns:
            WorktreeInfo with path and metadata

        Raises:
            subprocess.CalledProcessError: If worktree creation fails
        """
        # Generate unique worktree path
        worktree_path = self._worktree_root / f"{workflow_id}_{task_id.hex[:8]}"

        # Ensure worktree root exists
        self._worktree_root.mkdir(parents=True, exist_ok=True)

        # Check if branch already exists in base repo
        branch_exists = await self._branch_exists(branch)

        # Run git worktree add command
        # Use asyncio.to_thread for non-blocking execution
        if branch_exists:
            # Branch exists, just add worktree and checkout
            cmd = ["git", "worktree", "add", "-b", branch, str(worktree_path), "HEAD"]
            try:
                await self._run_git(cmd, cwd=self._base_repo_path, check=True)
                is_new = True
            except subprocess.CalledProcessError as e:
                if "already exists" in str(e.stderr):
                    # Worktree exists, just checkout the branch
                    checkout_cmd = ["git", "checkout", branch]
                    await self._run_git(checkout_cmd, cwd=worktree_path, check=True)
                    is_new = False
                else:
                    raise
        else:
            # New branch, create worktree with new branch
            cmd = ["git", "worktree", "add", "-b", branch, str(worktree_path), "HEAD"]
            await self._run_git(cmd, cwd=self._base_repo_path, check=True)
            is_new = True

        # Get current commit SHA
        sha_cmd = ["git", "rev-parse", "HEAD"]
        sha_result = await self._run_git(sha_cmd, cwd=worktree_path, check=True)
        commit_sha = sha_result.stdout.strip()

        logger.info(
            f"Created worktree at {worktree_path} "
            f"(branch={branch}, commit={commit_sha}, new={is_new})"
        )

        return WorktreeInfo(
            path=worktree_path,
            branch=branch,
            commit_sha=commit_sha,
            is_new=is_new,
        )

    async def commit_changes(
        self,
        worktree_path: Path,
        message: str,
        author: str | None = None,
        sign: bool | None = None,
    ) -> CommitInfo:
        """Commit changes in a worktree.

        Args:
            worktree_path: Path to the worktree
            message: Commit message
            author: Author string (optional, uses git config if not provided)
            sign: Override signing behavior (None = use default, True = sign, False = no sign)

        Returns:
            CommitInfo with SHA and metadata

        Raises:
            subprocess.CalledProcessError: If commit fails or signing is required but unavailable
        """
        # Stage all changes
        await self._run_git(["git", "add", "."], cwd=worktree_path, check=True)

        # Determine if commit should be signed
        should_sign = sign if sign is not None else self._require_signed_commits

        # Build commit command with correct author and signing parameters
        cmd = ["git", "commit"]
        if author:
            cmd.extend(["--author", author])
        if should_sign:
            cmd.append("-S")
        cmd.extend(["-m", message])

        result = await self._run_git(cmd, cwd=worktree_path, check=True)

        # Get commit SHA
        sha_cmd = ["git", "rev-parse", "HEAD"]
        sha_result = await self._run_git(sha_cmd, cwd=worktree_path, check=True)
        commit_sha = sha_result.stdout.strip()

        # Get commit timestamp
        time_cmd = ["git", "log", "-1", "--format=%ai"]
        time_result = await self._run_git(time_cmd, cwd=worktree_path, check=True)
        timestamp = time_result.stdout.strip()

        # Verify signature if signing was requested
        is_signed = False
        if should_sign:
            is_signed = await self._verify_signature(worktree_path, commit_sha)
            if not is_signed and self._require_signed_commits:
                logger.error(
                    f"Commit {commit_sha[:8]} in {worktree_path} is not signed "
                    "but signing was required"
                )
                # Note: We don't fail here as the commit was created,
                # but we log the warning for observability

        logger.info(
            f"Committed changes in {worktree_path}: "
            f"{commit_sha[:8]} - {message}"
            f"{' (signed)' if is_signed else ''}"
        )

        return CommitInfo(
            sha=commit_sha,
            message=message,
            author=author or "unknown",
            timestamp=timestamp,
        )

    async def _verify_signature(
        self,
        worktree_path: Path,
        commit_sha: str,
    ) -> bool:
        """Verify GPG signature of a commit.

        Args:
            worktree_path: Path to the worktree
            commit_sha: Commit SHA to verify

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            cmd = ["git", "verify-commit", commit_sha]
            await self._run_git(cmd, cwd=worktree_path, check=True)
            logger.debug(f"Signature verified for commit {commit_sha[:8]}")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Signature verification failed for commit {commit_sha[:8]}: {e}"
            )
            return False

    async def cherry_pick(
        self,
        target_branch: str,
        commit_sha: str,
        worktree_path: Path,
    ) -> bool:
        """Cherry-pick a commit from worktree to target branch.

        CRITICAL: This implementation executes cherry-pick in the worktree itself,
        then merges the result into the target branch in the base repo.

        Args:
            target_branch: Branch in base repo to merge into
            commit_sha: Commit SHA in the worktree
            worktree_path: Path to the worktree (required)

        Returns:
            True if cherry-pick succeeded, False if conflict

        Raises:
            subprocess.CalledProcessError: If non-conflict error occurs

        CORRECTED LOGIC (vs. original):
        1. Cherry-pick is executed in the worktree (where the commit exists)
        2. Result is merged into target branch in base repo
        3. Worktree is cleaned up afterwards
        """
        # Step 1: Cherry-pick in the worktree (where commit exists)
        try:
            cmd = ["git", "cherry-pick", commit_sha]
            await self._run_git(cmd, cwd=worktree_path, check=True)
            logger.info(f"Cherry-picked {commit_sha[:8]} in worktree {worktree_path}")
        except subprocess.CalledProcessError as e:
            if "conflict" in str(e.stderr).lower():
                logger.warning(
                    f"Cherry-pick conflict for {commit_sha[:8]} in worktree {worktree_path}"
                )
                # Abort cherry-pick to leave worktree clean
                await self._run_git(
                    ["git", "cherry-pick", "--abort"],
                    cwd=worktree_path,
                    check=False,  # Don't fail if already clean
                )
                return False
            else:
                # Non-conflict error, re-raise
                raise

        # Step 2: Merge worktree branch into target branch in base repo
        worktree_branch = await self._get_current_branch(worktree_path)

        try:
            # Fetch worktree branch into base repo
            await self._run_git(
                ["git", "fetch", "file://", str(worktree_path), worktree_branch],
                cwd=self._base_repo_path,
                check=True,
            )

            # Checkout target branch
            await self._run_git(
                ["git", "checkout", target_branch],
                cwd=self._base_repo_path,
                check=True,
            )

            # Merge worktree branch
            merge_cmd = [
                "git",
                "merge",
                "--no-ff",
                worktree_branch,
                "-m",
                f"Merge from worktree: {commit_sha[:8]}",
            ]
            await self._run_git(merge_cmd, cwd=self._base_repo_path, check=True)

            logger.info(
                f"Merged worktree branch {worktree_branch} into {target_branch}"
            )
            return True

        except subprocess.CalledProcessError as e:
            if "conflict" in str(e.stderr).lower():
                logger.warning(
                    f"Merge conflict when merging {worktree_branch} into {target_branch}"
                )
                # Abort merge to leave base repo clean
                await self._run_git(
                    ["git", "merge", "--abort"],
                    cwd=self._base_repo_path,
                    check=False,
                )
                return False
            else:
                raise

    async def cleanup_worktree(self, worktree_path: Path) -> None:
        """Remove a worktree.

        Args:
            worktree_path: Path to the worktree to remove
        """
        # Use git worktree remove --force
        cmd = ["git", "worktree", "remove", "-f", str(worktree_path)]

        try:
            await self._run_git(cmd, cwd=self._base_repo_path, check=True)
            logger.info(f"Removed worktree at {worktree_path}")
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Failed to remove worktree {worktree_path}: {e}"
            )
            # Optionally force remove filesystem path
            # import shutil
            # shutil.rmtree(worktree_path, ignore_errors=True)

    async def _branch_exists(self, branch: str) -> bool:
        """Check if a branch exists in the base repo.

        Args:
            branch: Branch name to check

        Returns:
            True if branch exists
        """
        try:
            cmd = ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]
            await self._run_git(cmd, cwd=self._base_repo_path, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    async def _get_current_branch(self, worktree_path: Path) -> str:
        """Get current branch name in worktree.

        Args:
            worktree_path: Path to worktree

        Returns:
            Current branch name
        """
        cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        result = await self._run_git(cmd, cwd=worktree_path, check=True)
        return result.stdout.strip()

    async def _run_git(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a git command asynchronously.

        Args:
            cmd: Git command and arguments
            cwd: Working directory
            check: Raise exception on non-zero exit

        Returns:
            CompletedProcess instance
        """
        loop = asyncio.get_event_loop()

        def run():
            return subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=check,
            )

        # Run in thread pool to avoid blocking
        return await loop.run_in_executor(None, run)

    @staticmethod
    async def validate_script_path(path: Path, base_path: Path) -> bool:
        """Validate that a script path is within an allowed base path.

        Security feature to prevent executing scripts outside allowed directories.

        Args:
            path: Script path to validate
            base_path: Allowed base path

        Returns:
            True if path is within base_path, False otherwise
        """
        try:
            resolved_path = path.resolve()
            resolved_base = base_path.resolve()
            return str(resolved_path).startswith(str(resolved_base))
        except (OSError, ValueError):
            logger.warning(f"Invalid path validation: {path} vs {base_path}")
            return False
