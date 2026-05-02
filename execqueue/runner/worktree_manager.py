"""Git worktree management for REQ-021.

This module provides centralized worktree management with metadata persistence,
lifecycle tracking, and orphaned cleanup as specified in REQ-021 Section 3.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from execqueue.db.models import WorktreeMetadata, WorktreeStatus
from execqueue.db.session import get_db_session
from execqueue.observability import (
    record_worktree_created,
    record_worktree_cleaned,
    record_worktree_error,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


@dataclass
class WorktreeMetadataResult:
    """Result of worktree creation or lookup.

    Attributes:
        metadata: The worktree metadata record
        was_created: Whether this was a new worktree or existing one
        error_message: Error message if creation failed
    """
    metadata: WorktreeMetadata | None = None
    was_created: bool = False
    error_message: str | None = None


class GitWorktreeManager:
    """Centralized worktree management with metadata persistence.

    This class implements REQ-021 Section 3:
    - Unique worktree identification via workflow_id + task_id
    - Persistent metadata tracking
    - Lifecycle status management (ACTIVE, CLEANED, ERROR)
    - Orphaned worktree cleanup (TTL-based)

    Usage:
        manager = GitWorktreeManager(worktree_root="/path/to/worktrees")
        result = await manager.create_or_get_worktree(
            workflow_id=workflow_id,
            task_id=task_id,
            branch="main"
        )
        if result.was_created:
            # Create actual git worktree
            subprocess.run(["git", "worktree", "add", result.metadata.path, ...])
    """

    def __init__(
        self,
        worktree_root: str,
        branch_prefix: str = "task",
        max_concurrent: int = 10,
    ):
        """Initialize the worktree manager.

        Args:
            worktree_root: Root directory for all worktrees
            branch_prefix: Prefix for task branch names
            max_concurrent: Maximum concurrent worktrees allowed
        """
        self.worktree_root = Path(worktree_root).resolve()
        self.branch_prefix = branch_prefix
        self.max_concurrent = max_concurrent

    def _generate_worktree_path(
        self, workflow_id: UUID, task_id: UUID
    ) -> Path:
        """Generate unique worktree path.

        Args:
            workflow_id: Workflow UUID
            task_id: Task UUID

        Returns:
            Absolute path for the worktree
        """
        # Use short IDs for path readability
        workflow_short = str(workflow_id)[:8]
        task_short = str(task_id)[:8]
        return self.worktree_root / f"{self.branch_prefix}_{workflow_short}_{task_short}"

    def _generate_branch_name(
        self, workflow_id: UUID, task_id: UUID, base_branch: str = "main"
    ) -> str:
        """Generate unique branch name for worktree.

        Args:
            workflow_id: Workflow UUID
            task_id: Task UUID
            base_branch: Base branch to branch from

        Returns:
            Unique branch name
        """
        task_short = str(task_id)[:8]
        return f"{self.branch_prefix}/{base_branch}-{task_short}"

    async def create_or_get_worktree(
        self,
        workflow_id: UUID,
        task_id: UUID,
        base_branch: str = "main",
        session: Session | None = None,
    ) -> WorktreeMetadataResult:
        """Create or retrieve worktree metadata.

        Args:
            workflow_id: Workflow UUID
            task_id: Task UUID
            base_branch: Base branch to branch from
            session: Optional database session

        Returns:
            WorktreeMetadataResult with metadata and creation status
        """
        async with (get_db_session() if session is None else session) as db:
            path = self._generate_worktree_path(workflow_id, task_id)
            branch = self._generate_branch_name(workflow_id, task_id, base_branch)

            # Check if worktree already exists
            existing = db.query(WorktreeMetadata).filter(
                WorktreeMetadata.task_id == task_id,
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
            ).first()

            if existing:
                logger.info(
                    f"Worktree already exists for task {task_id}",
                    extra={"workflow_id": str(workflow_id), "task_id": str(task_id)}
                )
                return WorktreeMetadataResult(
                    metadata=existing,
                    was_created=False,
                )

            # Check max concurrent worktrees
            active_count = db.query(WorktreeMetadata).filter(
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
            ).count()

            if active_count >= self.max_concurrent:
                return WorktreeMetadataResult(
                    metadata=None,
                    error_message=f"Max concurrent worktrees ({self.max_concurrent}) reached",
                )

            # Create metadata record
            metadata = WorktreeMetadata(
                id=uuid4(),
                workflow_id=workflow_id,
                task_id=task_id,
                path=str(path),
                branch=branch,
                status=WorktreeStatus.ACTIVE.value,
            )

            db.add(metadata)
            db.commit()
            db.refresh(metadata)

            logger.info(
                f"Created worktree metadata: {metadata.id} for task {task_id}",
                extra={"workflow_id": str(workflow_id), "task_id": str(task_id)}
            )
            
            # Record metrics
            record_worktree_created()

            return WorktreeMetadataResult(
                metadata=metadata,
                was_created=True,
            )

    async def mark_cleaned(
        self,
        task_id: UUID,
        session: Session | None = None,
    ) -> bool:
        """Mark worktree as cleaned.

        Args:
            task_id: Task UUID
            session: Optional database session

        Returns:
            True if successfully marked, False if not found
        """
        async with (get_db_session() if session is None else session) as db:
            metadata = db.query(WorktreeMetadata).filter(
                WorktreeMetadata.task_id == task_id,
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
            ).first()

            if not metadata:
                logger.warning(f"No active worktree found for task {task_id}")
                return False

            metadata.status = WorktreeStatus.CLEANED.value
            metadata.cleaned_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(
                f"Marked worktree as cleaned: {metadata.id}",
                extra={"task_id": str(task_id)}
            )
            
            # Record metrics
            record_worktree_cleaned()
            
            return True

    async def mark_error(
        self,
        task_id: UUID,
        error_message: str,
        session: Session | None = None,
    ) -> bool:
        """Mark worktree as in error state.

        Args:
            task_id: Task UUID
            error_message: Error description
            session: Optional database session

        Returns:
            True if successfully marked, False if not found
        """
        async with (get_db_session() if session is None else session) as db:
            metadata = db.query(WorktreeMetadata).filter(
                WorktreeMetadata.task_id == task_id,
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
            ).first()

            if not metadata:
                logger.warning(f"No active worktree found for task {task_id}")
                return False

            metadata.status = WorktreeStatus.ERROR.value
            metadata.error_message = error_message
            db.commit()

            logger.error(
                f"Marked worktree as error: {metadata.id} - {error_message}",
                extra={"task_id": str(task_id)}
            )
            
            # Record metrics
            record_worktree_error()
            
            return True

    async def get_active_count(self, session: Session | None = None) -> int:
        """Get count of active worktrees.

        Args:
            session: Optional database session

        Returns:
            Number of active worktrees
        """
        async with (get_db_session() if session is None else session) as db:
            return db.query(WorktreeMetadata).filter(
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
            ).count()

    async def cleanup_orphaned(
        self,
        ttl_hours: int = 24,
        force: bool = False,
        session: Session | None = None,
    ) -> int:
        """Clean up orphaned worktrees older than TTL.

        Args:
            ttl_hours: Age threshold in hours
            force: If True, force removal even if worktree has uncommitted changes
            session: Optional database session

        Returns:
            Number of worktrees cleaned
        """
        async with (get_db_session() if session is None else session) as db:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

            # Get old active worktrees
            old_worktrees = db.query(WorktreeMetadata).filter(
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
                WorktreeMetadata.created_at < cutoff_time,
            ).all()

            cleaned_count = 0
            for metadata in old_worktrees:
                try:
                    # Check if worktree directory exists
                    worktree_path = Path(metadata.path)
                    if worktree_path.exists():
                        # Check if worktree is clean
                        if not force and not self._is_worktree_clean(worktree_path):
                            logger.warning(
                                f"Worktree {metadata.id} has uncommitted changes, skipping",
                                extra={"task_id": str(metadata.task_id)}
                            )
                            # Mark as error instead
                            metadata.status = WorktreeStatus.ERROR.value
                            metadata.error_message = "Orphaned cleanup skipped: dirty worktree"
                            continue

                        # Remove worktree
                        self._remove_worktree(worktree_path)

                    # Update metadata
                    metadata.status = WorktreeStatus.CLEANED.value
                    metadata.cleaned_at = datetime.now(timezone.utc)
                    db.commit()

                    cleaned_count += 1
                    logger.info(
                        f"Cleaned up orphaned worktree: {metadata.id}",
                        extra={"task_id": str(metadata.task_id)}
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to clean up worktree {metadata.id}: {e}",
                        extra={"task_id": str(metadata.task_id)},
                        exc_info=True,
                    )
                    metadata.status = WorktreeStatus.ERROR.value
                    metadata.error_message = f"Cleanup failed: {str(e)}"
                    db.commit()

            return cleaned_count

    def _is_worktree_clean(self, path: Path) -> bool:
        """Check if worktree has no uncommitted changes.

        Args:
            path: Path to worktree directory

        Returns:
            True if worktree is clean
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return not result.stdout.strip()
        except Exception:
            return False

    def _remove_worktree(self, path: Path) -> None:
        """Remove worktree directory.

        Args:
            path: Path to worktree directory
        """
        try:
            # Try git worktree remove first
            result = subprocess.run(
                ["git", "worktree", "remove", str(path), "--force"],
                cwd=str(path.parent),  # Run from parent directory
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return

            # Fall back to recursive delete
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to remove worktree {path}: {e}")
            # Force remove anyway
            import shutil
            shutil.rmtree(path, ignore_errors=True)

    async def get_worktree_info(
        self,
        task_id: UUID,
        session: Session | None = None,
    ) -> WorktreeMetadata | None:
        """Get worktree metadata for a task.

        Args:
            task_id: Task UUID
            session: Optional database session

        Returns:
            Worktree metadata or None
        """
        async with (get_db_session() if session is None else session) as db:
            return db.query(WorktreeMetadata).filter(
                WorktreeMetadata.task_id == task_id,
            ).order_by(WorktreeMetadata.created_at.desc()).first()
