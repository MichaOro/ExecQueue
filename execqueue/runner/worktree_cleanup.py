"""Worktree cleanup service for REQ-021.

This module provides automated worktree cleanup after successful commit adoption
and orphaned worktree cleanup as specified in REQ-021 Section 6.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from execqueue.db.models import WorktreeMetadata, WorktreeStatus
from execqueue.db.session import get_db_session
from execqueue.runner.worktree_manager import GitWorktreeManager

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class WorktreeCleanupService:
    """Handles worktree cleanup after successful adoption.

    Implements REQ-021 Section 6:
    - Automatic cleanup after successful adoption
    - Retry mechanism (3 attempts)
    - Force flag for dirty worktrees
    - Orphaned cleanup job (TTL-based)

    Usage:
        cleanup = WorktreeCleanupService(
            worktree_root="/path/to/worktrees",
            max_retries=3
        )
        success = await cleanup.cleanup_after_adoption(execution)
    """

    def __init__(
        self,
        worktree_root: str,
        max_retries: int = 3,
        force_cleanup: bool = False,
    ):
        """Initialize cleanup service.

        Args:
            worktree_root: Root directory for worktrees
            max_retries: Maximum retry attempts for cleanup
            force_cleanup: If True, force cleanup even with dirty worktree
        """
        self.worktree_root = Path(worktree_root).resolve()
        self.max_retries = max_retries
        self.force_cleanup = force_cleanup
        self._worktree_manager = GitWorktreeManager(worktree_root=worktree_root)

    async def cleanup_after_adoption(
        self,
        task_id: UUID,
        worktree_path: str | None = None,
        session: Session | None = None,
    ) -> bool:
        """Cleanup worktree after successful adoption.

        Args:
            task_id: Task UUID
            worktree_path: Optional explicit worktree path
            session: Optional database session

        Returns:
            True if cleanup succeeded, False otherwise
        """
        # Get worktree metadata
        if session is None:
            async with get_db_session() as db:
                metadata = db.query(WorktreeMetadata).filter(
                    WorktreeMetadata.task_id == task_id,
                    WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
                ).first()

                if not metadata:
                    logger.warning(f"No active worktree found for task {task_id}")
                    return False

                path = Path(worktree_path) if worktree_path else Path(metadata.path)

                # Retry loop
                for attempt in range(self.max_retries):
                    try:
                        success = await self._cleanup_worktree(path, force=self.force_cleanup)

                        if success:
                            # Update metadata
                            metadata.status = WorktreeStatus.CLEANED.value
                            metadata.cleaned_at = datetime.now(timezone.utc)
                            db.commit()

                            logger.info(
                                f"Successfully cleaned up worktree for task {task_id}",
                                extra={"task_id": str(task_id), "attempt": attempt + 1}
                            )
                            return True

                        logger.warning(
                            f"Cleanup attempt {attempt + 1} failed for task {task_id}",
                            extra={"task_id": str(task_id)}
                        )

                    except Exception as e:
                        logger.error(
                            f"Cleanup exception attempt {attempt + 1}: {e}",
                            extra={"task_id": str(task_id)},
                            exc_info=True,
                        )

                    if attempt < self.max_retries - 1:
                        # Wait before retry (exponential backoff)
                        import asyncio
                        await asyncio.sleep(2 ** attempt)

                # All retries failed
                metadata.status = WorktreeStatus.ERROR.value
                metadata.error_message = f"Cleanup failed after {self.max_retries} attempts"
                db.commit()

                logger.error(
                    f"Cleanup failed after {self.max_retries} attempts for task {task_id}",
                    extra={"task_id": str(task_id)}
                )
                return False
        else:
            # Use provided session
            metadata = session.query(WorktreeMetadata).filter(
                WorktreeMetadata.task_id == task_id,
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
            ).first()

            if not metadata:
                logger.warning(f"No active worktree found for task {task_id}")
                return False

            path = Path(worktree_path) if worktree_path else Path(metadata.path)

            # Retry loop
            for attempt in range(self.max_retries):
                try:
                    success = await self._cleanup_worktree(path, force=self.force_cleanup)

                    if success:
                        # Update metadata
                        metadata.status = WorktreeStatus.CLEANED.value
                        metadata.cleaned_at = datetime.now(timezone.utc)
                        session.commit()

                        logger.info(
                            f"Successfully cleaned up worktree for task {task_id}",
                            extra={"task_id": str(task_id), "attempt": attempt + 1}
                        )
                        return True

                    logger.warning(
                        f"Cleanup attempt {attempt + 1} failed for task {task_id}",
                        extra={"task_id": str(task_id)}
                    )

                except Exception as e:
                    logger.error(
                        f"Cleanup exception attempt {attempt + 1}: {e}",
                        extra={"task_id": str(task_id)},
                        exc_info=True,
                    )

                if attempt < self.max_retries - 1:
                    # Wait before retry (exponential backoff)
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

            # All retries failed
            metadata.status = WorktreeStatus.ERROR.value
            metadata.error_message = f"Cleanup failed after {self.max_retries} attempts"
            session.commit()

            logger.error(
                f"Cleanup failed after {self.max_retries} attempts for task {task_id}",
                extra={"task_id": str(task_id)}
            )
            return False

    async def _cleanup_worktree(
        self,
        path: Path,
        force: bool = False,
    ) -> bool:
        """Actually remove the worktree.

        Args:
            path: Path to worktree directory
            force: If True, force removal even if dirty

        Returns:
            True if successful
        """
        if not path.exists():
            logger.debug(f"Worktree path does not exist: {path}")
            return True

        try:
            # Check if worktree is clean
            is_clean = self._is_worktree_clean(path)

            if not is_clean and not force:
                logger.warning(f"Worktree has uncommitted changes: {path}")
                return False

            # Try git worktree remove first
            result = subprocess.run(
                ["git", "worktree", "remove", str(path), "--force"],
                cwd=str(path.parent),  # Run from parent directory
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.debug(f"Git worktree removed: {path}")
                return True

            # Fall back to recursive delete
            logger.warning(f"Using force delete for worktree: {path}")
            shutil.rmtree(path, ignore_errors=True)

            # Verify removal
            if not path.exists():
                return True

            # Last resort: rm -rf
            subprocess.run(
                ["rm", "-rf", str(path)],
                capture_output=True,
                timeout=60,
            )
            return not path.exists()

        except subprocess.TimeoutExpired:
            logger.error(f"Cleanup timeout for worktree: {path}")
            return False
        except Exception as e:
            logger.error(f"Cleanup error for worktree {path}: {e}")
            return False

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

    async def orphaned_cleanup_job(
        self,
        ttl_hours: int = 24,
        force: bool = False,
        session: Session | None = None,
    ) -> int:
        """Remove worktrees older than TTL.

        This is a scheduled job that cleans up orphaned worktrees.

        Args:
            ttl_hours: Age threshold in hours
            force: If True, force removal even if dirty
            session: Optional database session

        Returns:
            Number of worktrees cleaned
        """
        if session is None:
            async with get_db_session() as db:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

                # Get old active worktrees
                old_worktrees = db.query(WorktreeMetadata).filter(
                    WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
                    WorktreeMetadata.created_at < cutoff_time,
                ).all()

                cleaned_count = 0
                for metadata in old_worktrees:
                    try:
                        worktree_path = Path(metadata.path)

                        if worktree_path.exists():
                            # Check if dirty
                            is_clean = self._is_worktree_clean(worktree_path)

                            if not is_clean and not force:
                                logger.warning(
                                    f"Orphaned worktree {metadata.id} is dirty, marking as error",
                                    extra={"task_id": str(metadata.task_id)}
                                )
                                metadata.status = WorktreeStatus.ERROR.value
                                metadata.error_message = "Orphaned cleanup skipped: dirty worktree"
                                db.commit()
                                continue

                            # Remove worktree
                            success = await self._cleanup_worktree(worktree_path, force=force)

                            if not success:
                                metadata.status = WorktreeStatus.ERROR.value
                                metadata.error_message = "Orphaned cleanup failed"
                                db.commit()
                                continue

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
                            f"Failed to clean orphaned worktree {metadata.id}: {e}",
                            extra={"task_id": str(metadata.task_id)},
                            exc_info=True,
                        )
                        metadata.status = WorktreeStatus.ERROR.value
                        metadata.error_message = f"Orphaned cleanup failed: {str(e)}"
                        db.commit()

                if cleaned_count > 0:
                    logger.info(
                        f"Orphaned cleanup completed: {cleaned_count} worktrees removed",
                        extra={"ttl_hours": ttl_hours, "force": force}
                    )

                return cleaned_count
        else:
            # Use provided session
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

            # Get old active worktrees
            old_worktrees = session.query(WorktreeMetadata).filter(
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
                WorktreeMetadata.created_at < cutoff_time,
            ).all()

            cleaned_count = 0
            for metadata in old_worktrees:
                try:
                    worktree_path = Path(metadata.path)

                    if worktree_path.exists():
                        # Check if dirty
                        is_clean = self._is_worktree_clean(worktree_path)

                        if not is_clean and not force:
                            logger.warning(
                                f"Orphaned worktree {metadata.id} is dirty, marking as error",
                                extra={"task_id": str(metadata.task_id)}
                            )
                            metadata.status = WorktreeStatus.ERROR.value
                            metadata.error_message = "Orphaned cleanup skipped: dirty worktree"
                            session.commit()
                            continue

                        # Remove worktree
                        success = await self._cleanup_worktree(worktree_path, force=force)

                        if not success:
                            metadata.status = WorktreeStatus.ERROR.value
                            metadata.error_message = "Orphaned cleanup failed"
                            session.commit()
                            continue

                    # Update metadata
                    metadata.status = WorktreeStatus.CLEANED.value
                    metadata.cleaned_at = datetime.now(timezone.utc)
                    session.commit()

                    cleaned_count += 1
                    logger.info(
                        f"Cleaned up orphaned worktree: {metadata.id}",
                        extra={"task_id": str(metadata.task_id)}
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to clean orphaned worktree {metadata.id}: {e}",
                        extra={"task_id": str(metadata.task_id)},
                        exc_info=True,
                    )
                    metadata.status = WorktreeStatus.ERROR.value
                    metadata.error_message = f"Orphaned cleanup failed: {str(e)}"
                    session.commit()

            if cleaned_count > 0:
                logger.info(
                    f"Orphaned cleanup completed: {cleaned_count} worktrees removed",
                    extra={"ttl_hours": ttl_hours, "force": force}
                )

            return cleaned_count

    async def get_orphaned_count(
        self,
        ttl_hours: int = 24,
        session: Session | None = None,
    ) -> int:
        """Get count of worktrees that would be cleaned.

        Args:
            ttl_hours: Age threshold in hours
            session: Optional database session

        Returns:
            Number of orphaned worktrees
        """
        async with (get_db_session() if session is None else session) as db:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

            return db.query(WorktreeMetadata).filter(
                WorktreeMetadata.status == WorktreeStatus.ACTIVE.value,
                WorktreeMetadata.created_at < cutoff_time,
            ).count()
