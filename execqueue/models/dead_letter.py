from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeadLetterQueue(SQLModel, table=True):
    """
    Dead Letter Queue model for storing failed tasks.
    
    This model stores a snapshot of tasks that have exceeded their maximum
    retry count, enabling debugging, manual reprocessing, and failure analysis.
    
    Attributes:
        id: Primary key
        task_id: ID of the failed task (may reference deleted tasks)
        source_type: Type of source ("requirement" or "work_package")
        source_id: ID of the source entity
        task_title: Snapshot of task title at failure time
        task_prompt: Snapshot of task prompt at failure time
        verification_prompt: Snapshot of verification prompt
        final_status: Final status ("failed" or "max_retries_exceeded")
        failure_reason: Brief description of failure reason
        failure_details: Detailed error message or stacktrace
        last_execution_output: Output from last execution attempt
        retry_count: Number of retry attempts made
        max_retries: Configured maximum retries
        failed_at: Timestamp when task permanently failed
        created_at: Timestamp when DLQ entry was created
    """
    __tablename__ = "dead_letter_queue"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    task_id: int = Field(index=True, description="ID of the failed task")
    source_type: str = Field(index=True, description="Source type: requirement or work_package")
    source_id: int = Field(index=True, description="Source entity ID")
    
    task_title: str = Field(description="Snapshot of task title")
    task_prompt: str = Field(description="Snapshot of task prompt")
    verification_prompt: Optional[str] = Field(default=None, description="Snapshot of verification prompt")
    
    final_status: str = Field(default="max_retries_exceeded", description="Final status: failed or max_retries_exceeded")
    failure_reason: str = Field(description="Brief failure reason")
    failure_details: str = Field(description="Detailed error information")
    last_execution_output: Optional[str] = Field(default=None, description="Last execution output")
    
    retry_count: int = Field(description="Number of retry attempts")
    max_retries: int = Field(description="Configured max retries")
    
    failed_at: datetime = Field(default_factory=utcnow, index=True, description="When task failed")
    created_at: datetime = Field(default_factory=utcnow, index=True, description="When DLQ entry created")
