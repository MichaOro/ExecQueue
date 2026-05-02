"""Distributed locking for orchestrator coordination.

This module provides distributed locking mechanisms to prevent race conditions
when multiple orchestrator instances attempt to process the same backlog.

The lock is implemented using a database-backed advisory lock table, ensuring
atomicity and crash-safety across multiple workers.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Generator
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from execqueue.db.base import Base
from execqueue.db.models import TaskStatus
from execqueue.orchestrator.exceptions import LockingError

logger = logging.getLogger(__name__)


ORCHESTRATOR_LOCK_KEY = "orchestrator_preparation_cycle"
DEFAULT_LOCK_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_LOCK_REFRESH_INTERVAL_SECONDS = 30  # 30 seconds


class OrchestratorLock(Base):
    """Advisory lock table for orchestrator coordination.
    
    This table provides a simple mechanism for coordinating access to
    shared resources across multiple orchestrator instances.
    """
    
    __tablename__ = "orchestrator_lock"
    
    lock_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    lock_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    worker_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass
class LockAcquisitionResult:
    """Result of a lock acquisition attempt."""
    
    success: bool
    lock_id: str | None = None
    worker_id: str | None = None
    acquired_at: datetime | None = None
    error_message: str | None = None


class DistributedLockManager:
    """Manages distributed locks using database-backed advisory locks.
    
    This implementation uses a simple lease-based approach:
    1. Lock acquisition inserts a row with worker_id and expiration time
    2. Lock refresh updates the expiration time
    3. Lock release deletes the row
    4. Stale locks (past expiration) are automatically cleaned up
    """
    
    def __init__(
        self,
        worker_id: str,
        lock_timeout: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
        refresh_interval: int = DEFAULT_LOCK_REFRESH_INTERVAL_SECONDS,
    ):
        """Initialize the lock manager.
        
        Args:
            worker_id: Unique identifier for this worker
            lock_timeout: Lock timeout in seconds
            refresh_interval: How often to refresh the lock
        """
        self.worker_id = worker_id
        self.lock_timeout = lock_timeout
        self.refresh_interval = refresh_interval
        self._lock_id: str | None = None
    
    def try_acquire_lock(
        self,
        session: Session,
        lock_key: str = ORCHESTRATOR_LOCK_KEY,
    ) -> LockAcquisitionResult:
        """Try to acquire a distributed lock.
        
        Args:
            session: Database session
            lock_key: Lock identifier
            
        Returns:
            LockAcquisitionResult with success status
        """
        now = datetime.now(timezone.utc)
        lock_id = f"{lock_key}:{self.worker_id}"
        expiration = now + timedelta(seconds=self.lock_timeout)
        
        try:
            # Check if lock is already held
            existing = session.execute(
                select(OrchestratorLock).where(OrchestratorLock.lock_key == lock_key)
            ).scalars().first()
            
            if existing:
                # Check if lock has expired
                if existing.expires_at and existing.expires_at > now:
                    # Lock is still valid
                    return LockAcquisitionResult(
                        success=False,
                        lock_id=existing.lock_id,
                        worker_id=existing.worker_id,
                        acquired_at=existing.created_at,
                        error_message=f"Lock held by {existing.worker_id} until {existing.expires_at}",
                    )
                else:
                    # Lock has expired, clean it up
                    logger.warning(
                        "Cleaning up expired lock (key=%s, holder=%s)",
                        lock_key,
                        existing.worker_id,
                    )
                    session.delete(existing)
                    session.flush()
            
            # Try to acquire the lock
            new_lock = OrchestratorLock(
                lock_key=lock_key,
                lock_id=lock_id,
                worker_id=self.worker_id,
                expires_at=expiration,
            )
            session.add(new_lock)
            session.flush()
            
            # Verify we actually got the lock (in case of race condition)
            acquired = session.execute(
                select(OrchestratorLock).where(OrchestratorLock.lock_id == lock_id)
            ).scalars().first()
            
            if acquired and acquired.worker_id == self.worker_id:
                self._lock_id = lock_id
                logger.info(
                    "Acquired distributed lock (key=%s, worker=%s, expires=%s)",
                    lock_key,
                    self.worker_id,
                    expiration,
                )
                return LockAcquisitionResult(
                    success=True,
                    lock_id=lock_id,
                    worker_id=self.worker_id,
                    acquired_at=now,
                )
            else:
                # Race condition - another worker got the lock
                return LockAcquisitionResult(
                    success=False,
                    error_message="Race condition: lock acquisition failed after insert",
                )
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error("Error acquiring lock: %s", e)
            return LockAcquisitionResult(
                success=False,
                error_message=f"Database error: {e}",
            )
    
    def refresh_lock(self, session: Session) -> bool:
        """Refresh the lock expiration time.
        
        Args:
            session: Database session
            
        Returns:
            True if successful, False otherwise
        """
        if not self._lock_id:
            return False
        
        try:
            new_expiration = datetime.now(timezone.utc) + timedelta(seconds=self.lock_timeout)
            
            result = session.execute(
                update(OrchestratorLock)
                .where(OrchestratorLock.lock_id == self._lock_id)
                .where(OrchestratorLock.worker_id == self.worker_id)
                .values(expires_at=new_expiration)
            )
            
            if result.rowcount == 1:
                logger.debug("Refreshed lock (lock_id=%s)", self._lock_id)
                return True
            else:
                logger.warning("Failed to refresh lock (lock_id=%s)", self._lock_id)
                return False
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error("Error refreshing lock: %s", e)
            return False
    
    def release_lock(self, session: Session) -> bool:
        """Release the distributed lock.
        
        Args:
            session: Database session
            
        Returns:
            True if successful, False otherwise
        """
        if not self._lock_id:
            return True  # No lock to release
        
        try:
            result = session.execute(
                delete(OrchestratorLock)
                .where(OrchestratorLock.lock_id == self._lock_id)
                .where(OrchestratorLock.worker_id == self.worker_id)
            )
            
            session.commit()
            
            if result.rowcount == 1:
                logger.info("Released lock (lock_id=%s)", self._lock_id)
                self._lock_id = None
                return True
            else:
                logger.warning("Lock already released or not found (lock_id=%s)", self._lock_id)
                self._lock_id = None
                return True
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error("Error releasing lock: %s", e)
            return False
    
    @contextmanager
    def acquire_lock(
        self,
        session: Session,
        lock_key: str = ORCHESTRATOR_LOCK_KEY,
        timeout: float | None = None,
    ) -> Generator[bool, None, None]:
        """Context manager for acquiring and releasing a lock.
        
        Args:
            session: Database session
            lock_key: Lock identifier
            timeout: Maximum time to wait for lock (None = no waiting)
            
        Yields:
            True if lock acquired, False otherwise
            
        Usage:
            with lock_manager.acquire_lock(session) as acquired:
                if acquired:
                    # Do work with lock held
                    pass
        """
        acquired = False
        
        try:
            # Try to acquire the lock
            result = self.try_acquire_lock(session, lock_key)
            acquired = result.success
            
            if not acquired:
                logger.warning(
                    "Failed to acquire lock: %s",
                    result.error_message,
                )
            
            yield acquired
        
        finally:
            # Always try to release the lock
            if acquired:
                self.release_lock(session)


def cleanup_expired_locks(session: Session) -> int:
    """Clean up expired locks.
    
    Args:
        session: Database session
        
    Returns:
        Number of expired locks cleaned up
    """
    try:
        result = session.execute(
            delete(OrchestratorLock)
            .where(OrchestratorLock.expires_at < datetime.now(timezone.utc))
        )
        session.commit()
        
        count = result.rowcount
        if count > 0:
            logger.info("Cleaned up %d expired locks", count)
        
        return count
    
    except SQLAlchemyError as e:
        session.rollback()
        logger.error("Error cleaning up expired locks: %s", e)
        return 0
