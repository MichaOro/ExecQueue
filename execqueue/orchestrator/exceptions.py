"""Exception hierarchy for the orchestrator package.

This module defines a structured exception hierarchy to enable reliable
differentiation between transient and permanent failures in orchestration.
"""

from __future__ import annotations

from typing import Any


class OrchestratorError(Exception):
    """Base exception for all orchestrator errors.
    
    All orchestrator-specific exceptions should inherit from this class
    to enable unified error handling and classification.
    """
    
    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        workflow_id: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the exception.
        
        Args:
            message: Human-readable error message
            task_id: Optional task identifier where the error occurred
            workflow_id: Optional workflow identifier where the error occurred
            details: Optional structured details about the error
        """
        super().__init__(message)
        self.message = message
        self.task_id = task_id
        self.workflow_id = workflow_id
        self.details = details or {}
    
    def __str__(self) -> str:
        """Return a string representation of the error."""
        parts = [self.message]
        if self.task_id:
            parts.append(f" (task={self.task_id})")
        if self.workflow_id:
            parts.append(f" (workflow={self.workflow_id})")
        return "".join(parts)


class DependencyError(OrchestratorError):
    """Raised when dependency extraction or validation fails.
    
    This error indicates problems with task dependencies such as:
    - Unknown task references in depends_on
    - Malformed dependency data
    - Invalid dependency structure
    """
    
    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        workflow_id: str | None = None,
        unknown_dependencies: list[str] | None = None,
        malformed_entries: list[Any] | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the dependency error.
        
        Args:
            message: Human-readable error message
            task_id: Task identifier where the error occurred
            workflow_id: Workflow identifier where the error occurred
            unknown_dependencies: List of unknown dependency IDs found
            malformed_entries: List of malformed dependency entries
            details: Additional structured details
        """
        super().__init__(
            message=message,
            task_id=task_id,
            workflow_id=workflow_id,
            details=details,
        )
        self.unknown_dependencies = unknown_dependencies or []
        self.malformed_entries = malformed_entries or []


class CycleError(OrchestratorError):
    """Raised when a cycle is detected in task dependencies.
    
    This error indicates circular dependencies that would prevent
    proper execution ordering.
    """
    
    def __init__(
        self,
        message: str,
        cycles: list[list[str]] | None = None,
        workflow_id: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the cycle error.
        
        Args:
            message: Human-readable error message
            cycles: List of detected cycles (each cycle is a list of task IDs)
            workflow_id: Workflow identifier where the cycle was found
            details: Additional structured details
        """
        super().__init__(
            message=message,
            workflow_id=workflow_id,
            details=details,
        )
        self.cycles = cycles or []
    
    def format_cycles(self) -> str:
        """Format cycles as a human-readable string."""
        if not self.cycles:
            return "No cycles detected"
        
        formatted = []
        for i, cycle in enumerate(self.cycles, 1):
            formatted.append(f"Cycle {i}: {' -> '.join(cycle)}")
        
        return "\n".join(formatted)


class ValidationError(OrchestratorError):
    """Raised when workflow context validation fails.
    
    This error indicates that the workflow context does not meet
    the required invariants for execution.
    """
    
    def __init__(
        self,
        message: str,
        errors: list[str] | None = None,
        workflow_id: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the validation error.
        
        Args:
            message: Human-readable error message
            errors: List of specific validation error messages
            workflow_id: Workflow identifier that failed validation
            details: Additional structured details
        """
        super().__init__(
            message=message,
            workflow_id=workflow_id,
            details=details,
        )
        self.errors = errors or []
    
    def format_errors(self) -> str:
        """Format errors as a human-readable string."""
        if not self.errors:
            return "No validation errors"
        return "\n".join(f"  - {err}" for err in self.errors)


class CandidateDiscoveryError(OrchestratorError):
    """Raised when candidate discovery fails.
    
    This error indicates problems when loading executable backlog tasks
    from the database.
    """
    
    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the candidate discovery error.
        
        Args:
            message: Human-readable error message
            task_id: Task identifier where the error occurred
            details: Additional structured details
        """
        super().__init__(
            message=message,
            task_id=task_id,
            details=details,
        )


class LockingError(OrchestratorError):
    """Raised when task locking operations fail.
    
    This error indicates problems when attempting to atomically lock
    tasks for execution.
    """
    
    def __init__(
        self,
        message: str,
        task_ids: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the locking error.
        
        Args:
            message: Human-readable error message
            task_ids: List of task IDs that failed to lock
            details: Additional structured details
        """
        super().__init__(
            message=message,
            details=details,
        )
        self.task_ids = task_ids or []


class ContextBuildingError(OrchestratorError):
    """Raised when workflow context building fails.
    
    This error indicates problems when preparing execution contexts
    for tasks or workflows.
    """
    
    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        workflow_id: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the context building error.
        
        Args:
            message: Human-readable error message
            task_id: Task identifier where the error occurred
            workflow_id: Workflow identifier where the error occurred
            details: Additional structured details
        """
        super().__init__(
            message=message,
            task_id=task_id,
            workflow_id=workflow_id,
            details=details,
        )
