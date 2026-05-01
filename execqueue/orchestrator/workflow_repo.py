"""Workflow repository for REQ-015 persistence layer.

Provides CRUD operations for Workflow entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from execqueue.orchestrator.workflow_models import WorkflowContext, WorkflowStatus, Workflow


class WorkflowRepository:
    """Repository for Workflow data access.
    
    Provides CRUD operations for workflow persistence.
    """
    
    def __init__(self):
        """Initialize the repository."""
        pass
    
    def create_workflow(
        self,
        session: Session,
        ctx: "WorkflowContext",
    ) -> "Workflow":
        """Insert a new workflow record.
        
        Args:
            session: Database session
            ctx: WorkflowContext to create workflow from
            
        Returns:
            Created Workflow ORM instance
        """
        from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus
        from uuid import uuid4
        
        wf = Workflow(
            id=uuid4(),
            epic_id=ctx.epic_id,
            requirement_id=ctx.requirement_id,
            status=WorkflowStatus.RUNNING.value,
        )
        session.add(wf)
        session.flush()  # obtain PK
        return wf
    
    def get_workflow(
        self,
        session: Session,
        workflow_id: UUID,
    ) -> "Workflow | None":
        """Get a workflow by ID.
        
        Args:
            session: Database session
            workflow_id: Workflow UUID
            
        Returns:
            Workflow or None if not found
        """
        from execqueue.orchestrator.workflow_models import Workflow
        
        return session.get(Workflow, workflow_id)
    
    def update_status(
        self,
        session: Session,
        workflow_id: UUID,
        new_status: "WorkflowStatus",
    ) -> None:
        """Update workflow status.
        
        Args:
            session: Database session
            workflow_id: Workflow UUID
            new_status: New status to set
            
        Raises:
            ValueError: If workflow not found
        """
        from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus
        
        wf = session.get(Workflow, workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")
        wf.status = new_status.value
        session.commit()
    
    def set_runner_uuid(
        self,
        session: Session,
        workflow_id: UUID,
        runner_uuid: str,
    ) -> None:
        """Store runner_uuid in workflow record.
        
        Args:
            session: Database session
            workflow_id: Workflow UUID
            runner_uuid: Runner identifier to store
        """
        from execqueue.orchestrator.workflow_models import Workflow
        
        wf = session.get(Workflow, workflow_id)
        if wf:
            wf.runner_uuid = runner_uuid
            session.commit()
    
    def get_running_workflows(
        self,
        session: Session,
    ) -> list["Workflow"]:
        """Get all workflows with running status.
        
        Args:
            session: Database session
            
        Returns:
            List of running workflows
        """
        from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus
        
        stmt = select(Workflow).where(
            Workflow.status == WorkflowStatus.RUNNING.value
        )
        return session.execute(stmt).scalars().all()
    
    def update_workflow(
        self,
        session: Session,
        workflow_id: UUID,
        **kwargs,
    ) -> "Workflow":
        """Update workflow fields.
        
        Args:
            session: Database session
            workflow_id: Workflow UUID
            **kwargs: Fields to update
            
        Returns:
            Updated Workflow instance
            
        Raises:
            ValueError: If workflow not found
        """
        from execqueue.orchestrator.workflow_models import Workflow
        
        wf = session.get(Workflow, workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        for key, value in kwargs.items():
            if hasattr(wf, key):
                setattr(wf, key, value)
        
        session.commit()
        return wf
