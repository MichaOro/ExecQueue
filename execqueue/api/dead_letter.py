from __future__ import annotations

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import func

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from execqueue.db.session import get_session
from execqueue.models.dead_letter import DeadLetterQueue
from execqueue.models.task import Task


router = APIRouter()


class DeadLetterEntryResponse(BaseModel):
    """Response model for DLQ entry."""
    id: int
    task_id: int
    source_type: str
    source_id: int
    task_title: str
    failure_reason: str
    failure_details: str
    retry_count: int
    max_retries: int
    failed_at: datetime
    created_at: datetime


class DeadLetterListResponse(BaseModel):
    """Paginated list response for DLQ entries."""
    total: int
    page: int
    page_size: int
    entries: list[DeadLetterEntryResponse]


class RequeueRequest(BaseModel):
    """Request model for requeuing tasks."""
    task_ids: list[int]


class RequeueResponse(BaseModel):
    """Response model for requeue operations."""
    requeued_count: int
    new_task_ids: list[int]


@router.get("/dead-letter", response_model=DeadLetterListResponse)
def list_dead_letter_queue(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    failure_reason: Optional[str] = Query(None, description="Filter by failure reason"),
    session: Session = Depends(get_session),
):
    """
    List failed tasks in the Dead Letter Queue.
    
    Supports pagination and filtering by source type and failure reason.
    """
    statement = select(DeadLetterQueue)
    
    if source_type:
        statement = statement.where(DeadLetterQueue.source_type == source_type)
    
    if failure_reason:
        statement = statement.where(DeadLetterQueue.failure_reason.contains(failure_reason))
    
    # Get total count
    count_statement = select(func.count(DeadLetterQueue.id))
    if source_type:
        count_statement = count_statement.where(DeadLetterQueue.source_type == source_type)
    if failure_reason:
        count_statement = count_statement.where(DeadLetterQueue.failure_reason.contains(failure_reason))
    
    total = session.exec(count_statement).one()
    
    # Get paginated results
    statement = statement.order_by(DeadLetterQueue.failed_at.desc())
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    
    entries = session.exec(statement).all()
    
    return DeadLetterListResponse(
        total=total,
        page=page,
        page_size=page_size,
        entries=[
            DeadLetterEntryResponse(
                id=entry.id,
                task_id=entry.task_id,
                source_type=entry.source_type,
                source_id=entry.source_id,
                task_title=entry.task_title,
                failure_reason=entry.failure_reason,
                failure_details=entry.failure_details,
                retry_count=entry.retry_count,
                max_retries=entry.max_retries,
                failed_at=entry.failed_at,
                created_at=entry.created_at,
            )
            for entry in entries
        ],
    )


@router.get("/dead-letter/{dlq_id}", response_model=DeadLetterEntryResponse)
def get_dead_letter_entry(
    dlq_id: int,
    session: Session = Depends(get_session),
):
    """Get details of a specific Dead Letter Queue entry."""
    entry = session.get(DeadLetterQueue, dlq_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Dead letter entry not found")
    
    return DeadLetterEntryResponse(
        id=entry.id,
        task_id=entry.task_id,
        source_type=entry.source_type,
        source_id=entry.source_id,
        task_title=entry.task_title,
        failure_reason=entry.failure_reason,
        failure_details=entry.failure_details,
        retry_count=entry.retry_count,
        max_retries=entry.max_retries,
        failed_at=entry.failed_at,
        created_at=entry.created_at,
    )


@router.post("/dead-letter/{dlq_id}/requeue", response_model=RequeueResponse)
def requeue_dead_letter_entry(
    dlq_id: int,
    session: Session = Depends(get_session),
):
    """
    Requeue a failed task from the Dead Letter Queue.
    
    Creates a new task with reset retry count.
    """
    entry = session.get(DeadLetterQueue, dlq_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Dead letter entry not found")
    
    # Create new task from snapshot
    new_task = Task(
        source_type=entry.source_type,
        source_id=entry.source_id,
        title=entry.task_title,
        prompt=entry.task_prompt,
        verification_prompt=entry.verification_prompt,
        status="queued",
        execution_order=0,
        retry_count=0,
        max_retries=entry.max_retries,
        is_test=entry.source_type == "requirement",  # Simplified test detection
    )
    
    session.add(new_task)
    session.commit()
    session.refresh(new_task)
    
    return RequeueResponse(
        requeued_count=1,
        new_task_ids=[new_task.id],
    )


@router.post("/dead-letter/bulk-requeue", response_model=RequeueResponse)
def bulk_requeue_dead_letter_entries(
    request: RequeueRequest,
    session: Session = Depends(get_session),
):
    """
    Requeue multiple failed tasks from the Dead Letter Queue.
    
    Creates new tasks with reset retry count for all specified entries.
    """
    new_tasks = []
    
    for dlq_id in request.task_ids:
        entry = session.get(DeadLetterQueue, dlq_id)
        if not entry:
            continue
        
        new_task = Task(
            source_type=entry.source_type,
            source_id=entry.source_id,
            title=entry.task_title,
            prompt=entry.task_prompt,
            verification_prompt=entry.verification_prompt,
            status="queued",
            execution_order=0,
            retry_count=0,
            max_retries=entry.max_retries,
            is_test=entry.source_type == "requirement",
        )
        
        session.add(new_task)
        new_tasks.append(new_task)
    
    session.commit()
    
    # Get IDs after commit
    new_task_ids = [task.id for task in new_tasks if task.id is not None]
    
    return RequeueResponse(
        requeued_count=len(new_task_ids),
        new_task_ids=new_task_ids,
    )


@router.delete("/dead-letter/{dlq_id}")
def delete_dead_letter_entry(
    dlq_id: int,
    session: Session = Depends(get_session),
):
    """
    Delete a Dead Letter Queue entry.
    
    Note: This does not affect the original failed task.
    """
    entry = session.get(DeadLetterQueue, dlq_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Dead letter entry not found")
    
    session.delete(entry)
    session.commit()
    
    return {"message": "Dead letter entry deleted"}
