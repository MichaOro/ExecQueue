"""
OpenCode Session Management Service.

This service orchestrates OpenCode ACP sessions for task execution,
providing lifecycle management, monitoring, and result export.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from execqueue.models.task import OpenCodeSessionStatus, Task
from execqueue.workers.opencode_adapter import OpenCodeACPClient

if TYPE_CHECKING:
    from sqlmodel import Session

logger = logging.getLogger(__name__)


class OpenCodeSessionService:
    """
    Service für die Verwaltung von OpenCode ACP Sessions.
    
    Verantwortlichkeiten:
    - Session-Erstellung und -Start
    - Status-Monitoring
    - Wake-up bei Timeout
    - Ergebnis-Export
    - Cleanup von abgelaufenen Sessions
    """
    
    def __init__(self, acp_client: OpenCodeACPClient):
        """
        Initialisiere den Session-Service.
        
        Args:
            acp_client: ACP-Client für die Kommunikation mit OpenCode
        """
        self.client = acp_client
        logger.info("OpenCodeSessionService initialized")
    
    def create_session(self, db: Session, task: Task) -> Task:
        """
        Startet eine neue OpenCode Session für einen Task.
        
        Args:
            db: Database session
            task: Task to execute
            
        Returns:
            Updated task with session_id
        """
        if not task.opencode_project_path:
            raise ValueError("Task has no opencode_project_path configured")
        
        logger.info(
            "Creating OpenCode session for task %d: project=%s",
            task.id,
            task.opencode_project_path
        )
        
        # Start session via ACP client
        session_id = self.client.start_session(
            prompt=task.prompt,
            cwd=task.opencode_project_path,
            title=task.title
        )
        
        # Update task
        task.opencode_session_id = session_id
        task.opencode_status = OpenCodeSessionStatus.RUNNING
        task.opencode_last_ping = datetime.now(timezone.utc)
        task.status = "processing"
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        logger.info(
            "Session created: task_id=%d, session_id=%s",
            task.id,
            session_id
        )
        
        return task
    
    def monitor_sessions(self, db: Session) -> list[Task]:
        """
        Prüft den Status aller aktiven Sessions.
        
        Args:
            db: Database session
            
        Returns:
            List of updated tasks
        """
        # Get all running or waiting tasks
        tasks = db.query(Task).filter(
            Task.opencode_status.in_([
                OpenCodeSessionStatus.RUNNING,
                OpenCodeSessionStatus.WAITING
            ])
        ).all()
        
        updated_tasks = []
        
        for task in tasks:
            if not task.opencode_session_id:
                continue
            
            try:
                # Check session status
                status_result = self.client.get_session_status(task.opencode_session_id)
                
                # Update last ping
                task.opencode_last_ping = datetime.now(timezone.utc)
                
                # Map status
                acp_status = status_result.get("status", "unknown").lower()
                if acp_status in ["completed", "success"]:
                    task.opencode_status = OpenCodeSessionStatus.COMPLETED
                    task.status = "completed"
                elif acp_status in ["failed", "error"]:
                    task.opencode_status = OpenCodeSessionStatus.FAILED
                    task.status = "failed"
                elif acp_status == "waiting":
                    task.opencode_status = OpenCodeSessionStatus.WAITING
                else:
                    task.opencode_status = OpenCodeSessionStatus.RUNNING
                
                db.add(task)
                updated_tasks.append(task)
                
                logger.debug(
                    "Session status: task_id=%d, session_id=%s, status=%s",
                    task.id,
                    task.opencode_session_id,
                    task.opencode_status
                )
                
            except Exception as e:
                logger.warning(
                    "Failed to monitor session for task %d: %s",
                    task.id,
                    e
                )
        
        if updated_tasks:
            db.commit()
        
        return updated_tasks
    
    def wake_up_session(self, db: Session, task: Task, prompt: str | None = None) -> Task:
        """
        Setzt eine Session fort (Wake-up).
        
        Args:
            db: Database session
            task: Task to wake up
            prompt: Optional prompt to send
            
        Returns:
            Updated task
        """
        if not task.opencode_session_id:
            raise ValueError("Task has no session_id")
        
        logger.info(
            "Waking up session for task %d: session_id=%s",
            task.id,
            task.opencode_session_id
        )
        
        try:
            # Continue session
            result = self.client.continue_session(
                session_id=task.opencode_session_id,
                prompt=prompt
            )
            
            # Update task
            task.opencode_status = OpenCodeSessionStatus.RUNNING
            task.opencode_last_ping = datetime.now(timezone.utc)
            task.status = "processing"
            
            db.add(task)
            db.commit()
            db.refresh(task)
            
            logger.info(
                "Session woken up: task_id=%d, session_id=%s",
                task.id,
                task.opencode_session_id
            )
            
            return task
            
        except Exception as e:
            logger.error(
                "Failed to wake up session for task %d: %s",
                task.id,
                e
            )
            raise
    
    def complete_session(self, db: Session, task: Task) -> Task:
        """
        Schließt eine Session und exportiert das Ergebnis.
        
        Args:
            db: Database session
            task: Completed task
            
        Returns:
            Updated task with result
        """
        if not task.opencode_session_id:
            raise ValueError("Task has no session_id")
        
        logger.info(
            "Completing session for task %d: session_id=%s",
            task.id,
            task.opencode_session_id
        )
        
        try:
            # Export session result
            result = self.client.export_session(task.opencode_session_id)
            
            # Store result
            output = result.get("output", "")
            task.last_result = output
            task.opencode_status = OpenCodeSessionStatus.COMPLETED
            task.status = "completed"
            task.opencode_last_ping = datetime.now(timezone.utc)
            
            db.add(task)
            db.commit()
            db.refresh(task)
            
            logger.info(
                "Session completed: task_id=%d, output_length=%d",
                task.id,
                len(output)
            )
            
            return task
            
        except Exception as e:
            logger.error(
                "Failed to complete session for task %d: %s",
                task.id,
                e
            )
            # Don't raise - mark as failed instead
            return self.fail_session(db, task, str(e))
    
    def fail_session(self, db: Session, task: Task, error: str) -> Task:
        """
        Markiert eine Session als fehlgeschlagen.
        
        Args:
            db: Database session
            task: Task to fail
            error: Error message
            
        Returns:
            Updated task
        """
        logger.error(
            "Failing session for task %d: error=%s",
            task.id,
            error[:100]
        )
        
        task.opencode_status = OpenCodeSessionStatus.FAILED
        task.status = "failed"
        task.last_result = f"OpenCode error: {error}"
        task.opencode_last_ping = datetime.now(timezone.utc)
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        return task
    
    def cleanup_expired_sessions(self, db: Session, timeout_seconds: int = 300) -> int:
        """
        Beendet Sessions die länger als timeout_seconds inaktiv sind.
        
        Args:
            db: Database session
            timeout_seconds: Timeout in seconds
            
        Returns:
            Number of cleaned up sessions
        """
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        cutoff = now - timedelta(seconds=timeout_seconds)
        
        # Find expired sessions
        expired_tasks = db.query(Task).filter(
            Task.opencode_status.in_([
                OpenCodeSessionStatus.RUNNING,
                OpenCodeSessionStatus.WAITING
            ]),
            Task.opencode_last_ping < cutoff
        ).all()
        
        cleaned_count = 0
        
        for task in expired_tasks:
            logger.warning(
                "Cleaning up expired session: task_id=%d, session_id=%s, last_ping=%s",
                task.id,
                task.opencode_session_id,
                task.opencode_last_ping
            )
            
            # Try to close session gracefully
            try:
                self.client.close_session(task.opencode_session_id)
            except Exception as e:
                logger.warning(
                    "Failed to close session %s: %s",
                    task.opencode_session_id,
                    e
                )
            
            # Mark as failed
            task.opencode_status = OpenCodeSessionStatus.FAILED
            task.status = "failed"
            task.last_result = f"Session timeout after {timeout_seconds}s"
            
            db.add(task)
            cleaned_count += 1
        
        if cleaned_count > 0:
            db.commit()
        
        logger.info("Cleaned up %d expired sessions", cleaned_count)
        return cleaned_count
