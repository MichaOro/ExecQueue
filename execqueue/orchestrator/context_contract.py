"""Prepared context contract builder for REQ-011.

This module builds the PreparedExecutionContext DTO that serves as the
handoff contract to downstream execution runners.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from execqueue.orchestrator.models import (
    PreparedExecutionContext,
    RunnerMode,
    PreparationError,
    PreparationErrorType,
)

logger = logging.getLogger(__name__)


class PreparedContextBuilder:
    """Builds PreparedExecutionContext for handoff to execution runner.
    
    This builder creates the versioned context contract (v1) that contains
    all information needed by a downstream runner to start execution.
    
    Important: This module does NOT start execution - it only prepares
    the context for execution.
    """
    
    CONTEXT_VERSION = "v1"
    
    # Fields that must not appear in context (security)
    SECRET_FIELDS = frozenset([
        "api_key",
        "secret",
        "token",
        "password",
        "credential",
        "private_key",
    ])
    
    def __init__(self, base_repo_path: str):
        """Initialize context builder.
        
        Args:
            base_repo_path: Path to base repository
        """
        self.base_repo_path = base_repo_path
    
    def _sanitize_details(self, details: dict[str, Any] | None) -> dict[str, Any]:
        """Remove potential secrets from details.
        
        Args:
            details: Original details dict
            
        Returns:
            Sanitized details
        """
        if not details:
            return {}
        
        sanitized = {}
        for key, value in details.items():
            key_lower = key.lower()
            # Check if key contains any secret patterns
            is_secret = any(
                secret in key_lower 
                for secret in self.SECRET_FIELDS
            )
            if not is_secret:
                sanitized[key] = value
        
        return sanitized
    
    def build_read_only_context(
        self,
        task_id: UUID,
        task_number: int,
        task_type: str,
        batch_id: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> PreparedExecutionContext:
        """Build context for a read-only task.
        
        Args:
            task_id: Task UUID
            task_number: Task number
            task_type: Task type
            batch_id: Optional batch ID
            correlation_id: Optional correlation ID
            details: Optional task details
            
        Returns:
            PreparedExecutionContext for read-only execution
        """
        return PreparedExecutionContext(
            version=self.CONTEXT_VERSION,
            task_id=task_id,
            task_number=task_number,
            task_type=task_type,
            requires_write_access=False,
            parallelization_mode=details.get("parallelization_mode", "parallel") if details else "parallel",
            runner_mode=RunnerMode.READ_ONLY,
            base_repo_path=self.base_repo_path,
            branch_name=None,
            worktree_path=None,
            commit_sha_before=None,
            correlation_id=correlation_id,
            batch_id=batch_id,
            prepared_at=datetime.utcnow(),
        )
    
    def build_write_context(
        self,
        task_id: UUID,
        task_number: int,
        task_type: str,
        branch_name: str,
        worktree_path: str,
        commit_sha_before: str,
        batch_id: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> PreparedExecutionContext:
        """Build context for a write task.
        
        Args:
            task_id: Task UUID
            task_number: Task number
            task_type: Task type
            branch_name: Branch name
            worktree_path: Worktree path
            commit_sha_before: Pre-execution commit SHA
            batch_id: Optional batch ID
            correlation_id: Optional correlation ID
            details: Optional task details
            
        Returns:
            PreparedExecutionContext for write execution
        """
        return PreparedExecutionContext(
            version=self.CONTEXT_VERSION,
            task_id=task_id,
            task_number=task_number,
            task_type=task_type,
            requires_write_access=True,
            parallelization_mode=details.get("parallelization_mode", "sequential") if details else "sequential",
            runner_mode=RunnerMode.WRITE,
            base_repo_path=self.base_repo_path,
            branch_name=branch_name,
            worktree_path=worktree_path,
            commit_sha_before=commit_sha_before,
            correlation_id=correlation_id,
            batch_id=batch_id,
            prepared_at=datetime.utcnow(),
        )
    
    def validate_context(self, context: PreparedExecutionContext) -> list[str]:
        """Validate a prepared context.
        
        Args:
            context: Context to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Check version
        if context.version != self.CONTEXT_VERSION:
            errors.append(f"Unsupported context version: {context.version}")
        
        # Check required fields
        if not context.task_id:
            errors.append("task_id is required")
        if not context.task_number:
            errors.append("task_number is required")
        if not context.task_type:
            errors.append("task_type is required")
        if not context.base_repo_path:
            errors.append("base_repo_path is required")
        
        # Mode-specific validation
        if context.runner_mode == RunnerMode.WRITE:
            if not context.branch_name:
                errors.append("WRITE mode requires branch_name")
            if not context.worktree_path:
                errors.append("WRITE mode requires worktree_path")
            if not context.commit_sha_before:
                errors.append("WRITE mode requires commit_sha_before")
        
        # Check for potential secrets (log warning if found)
        context_dict = context.to_dict()
        for key, value in context_dict.items():
            if isinstance(value, str):
                key_lower = key.lower()
                for secret in self.SECRET_FIELDS:
                    if secret in key_lower and value:
                        logger.warning(
                            "Potential secret field detected: %s in context for task %s",
                            key,
                            context.task_number,
                        )
        
        return errors
    
    def build_context(
        self,
        task_id: UUID,
        task_number: int,
        task_type: str,
        requires_write: bool,
        branch_name: str | None = None,
        worktree_path: str | None = None,
        commit_sha_before: str | None = None,
        batch_id: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> PreparedExecutionContext:
        """Build context based on task requirements.
        
        Args:
            task_id: Task UUID
            task_number: Task number
            task_type: Task type
            requires_write: Whether task requires write access
            branch_name: Optional branch name
            worktree_path: Optional worktree path
            commit_sha_before: Optional commit SHA
            batch_id: Optional batch ID
            correlation_id: Optional correlation ID
            details: Optional task details
            
        Returns:
            PreparedExecutionContext
            
        Raises:
            PreparationError: If context cannot be built
        """
        if requires_write:
            if not branch_name or not worktree_path or not commit_sha_before:
                raise PreparationError(
                    error_type=PreparationErrorType.NON_RECOVERABLE,
                    message="WRITE mode requires branch_name, worktree_path, and commit_sha_before",
                    task_id=task_id,
                    details={
                        "branch_name": branch_name,
                        "worktree_path": worktree_path,
                        "commit_sha_before": commit_sha_before,
                    },
                )
            return self.build_write_context(
                task_id=task_id,
                task_number=task_number,
                task_type=task_type,
                branch_name=branch_name,
                worktree_path=worktree_path,
                commit_sha_before=commit_sha_before,
                batch_id=batch_id,
                correlation_id=correlation_id,
                details=details,
            )
        else:
            return self.build_read_only_context(
                task_id=task_id,
                task_number=task_number,
                task_type=task_type,
                batch_id=batch_id,
                correlation_id=correlation_id,
                details=details,
            )
