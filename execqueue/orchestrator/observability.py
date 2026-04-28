"""Observability and E2E tests for REQ-011 (AP 08).

This module provides:
1. Structured logging utilities
2. Preparation-only E2E test
3. Negative assertions against execution start
"""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class StructuredLogger:
    """Structured logger for orchestrator events."""
    
    def __init__(self, logger_name: str = "execqueue.orchestrator"):
        """Initialize structured logger.
        
        Args:
            logger_name: Logger name
        """
        self.logger = logging.getLogger(logger_name)
    
    def _log(
        self,
        level: int,
        event: str,
        task_id: UUID | None = None,
        task_number: int | None = None,
        task_type: str | None = None,
        requirement_id: UUID | None = None,
        correlation_id: str | None = None,
        batch_id: str | None = None,
        batch_type: str | None = None,
        status_from: str | None = None,
        status_to: str | None = None,
        runner_mode: str | None = None,
        branch_name: str | None = None,
        worktree_path: str | None = None,
        error_code: str | None = None,
        error_class: str | None = None,
        **extra: Any,
    ) -> None:
        """Log a structured event.
        
        Args:
            level: Log level
            event: Event name
            task_id: Task UUID
            task_number: Task number
            task_type: Task type
            requirement_id: Requirement ID
            correlation_id: Correlation ID
            batch_id: Batch ID
            batch_type: Batch type
            status_from: Previous status
            status_to: New status
            runner_mode: Runner mode
            branch_name: Branch name
            worktree_path: Worktree path
            error_code: Error code
            error_class: Error class
            **extra: Additional fields
        """
        log_data = {
            "event": event,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if task_id:
            log_data["task_id"] = str(task_id)
        if task_number:
            log_data["task_number"] = task_number
        if task_type:
            log_data["task_type"] = task_type
        if requirement_id:
            log_data["requirement_id"] = str(requirement_id)
        if correlation_id:
            log_data["correlation_id"] = correlation_id
        if batch_id:
            log_data["batch_id"] = batch_id
        if batch_type:
            log_data["batch_type"] = batch_type
        if status_from:
            log_data["status_from"] = status_from
        if status_to:
            log_data["status_to"] = status_to
        if runner_mode:
            log_data["runner_mode"] = runner_mode
        if branch_name:
            log_data["branch_name"] = branch_name
        if worktree_path:
            log_data["worktree_path"] = worktree_path
        if error_code:
            log_data["error_code"] = error_code
        if error_class:
            log_data["error_class"] = error_class
        
        log_data.update(extra)
        
        # Log as JSON for structured logging
        self.logger.log(level, json.dumps(log_data))
    
    def task_discovered(
        self,
        task_id: UUID,
        task_number: int,
        task_type: str,
        correlation_id: str,
    ) -> None:
        """Log task discovery."""
        self._log(
            logging.INFO,
            "task_discovered",
            task_id=task_id,
            task_number=task_number,
            task_type=task_type,
            correlation_id=correlation_id,
        )
    
    def task_classified(
        self,
        task_id: UUID,
        task_number: int,
        runner_mode: str,
        batch_id: str,
    ) -> None:
        """Log task classification."""
        self._log(
            logging.INFO,
            "task_classified",
            task_id=task_id,
            task_number=task_number,
            runner_mode=runner_mode,
            batch_id=batch_id,
        )
    
    def task_locked(
        self,
        task_id: UUID,
        task_number: int,
        batch_id: str,
        worker_id: str,
    ) -> None:
        """Log task locking."""
        self._log(
            logging.INFO,
            "task_locked",
            task_id=task_id,
            task_number=task_number,
            batch_id=batch_id,
            worker_id=worker_id,
        )
    
    def context_prepared(
        self,
        task_id: UUID,
        task_number: int,
        runner_mode: str,
        branch_name: str | None,
        worktree_path: str | None,
        batch_id: str,
    ) -> None:
        """Log context preparation."""
        self._log(
            logging.INFO,
            "context_prepared",
            task_id=task_id,
            task_number=task_number,
            runner_mode=runner_mode,
            branch_name=branch_name,
            worktree_path=worktree_path,
            batch_id=batch_id,
        )
    
    def preparation_failed(
        self,
        task_id: UUID,
        task_number: int,
        error_code: str,
        error_class: str,
        status_to: str,
    ) -> None:
        """Log preparation failure."""
        self._log(
            logging.ERROR,
            "preparation_failed",
            task_id=task_id,
            task_number=task_number,
            error_code=error_code,
            error_class=error_class,
            status_to=status_to,
        )
    
    def recovery_executed(
        self,
        task_id: UUID,
        task_number: int,
        status_from: str,
        status_to: str,
        reason: str,
    ) -> None:
        """Log recovery execution."""
        self._log(
            logging.INFO,
            "recovery_executed",
            task_id=task_id,
            task_number=task_number,
            status_from=status_from,
            status_to=status_to,
            reason=reason,
        )


# E2E Test Helper
@dataclass
class E2EValidationResult:
    """Result of E2E validation."""
    
    passed: bool
    write_path_valid: bool
    readonly_path_valid: bool
    negative_assertions_passed: bool
    errors: list[str]
    
    def __bool__(self) -> bool:
        return self.passed


class E2EValidator:
    """Validates REQ-011 preparation flow without starting execution."""
    
    def __init__(self):
        """Initialize validator."""
        self.errors: list[str] = []
        self.write_path_valid = False
        self.readonly_path_valid = False
        self.negative_assertions_passed = False
        
        # Negative assertion flags
        self.opcode_started = False
        self.prompt_dispatched = False
        self.task_execution_started = False
        self.status_in_progress = False
        self.commit_created = False
    
    def validate_write_path(
        self,
        task_number: int,
        branch_name: str,
        worktree_path: str,
        commit_sha_before: str,
        context: Any,
    ) -> bool:
        """Validate write path preparation.
        
        Args:
            task_number: Task number
            branch_name: Branch name
            worktree_path: Worktree path
            commit_sha_before: Commit SHA
            context: Prepared context
            
        Returns:
            True if valid
        """
        try:
            # Check context has required fields
            if context.runner_mode.value != "write":
                self.errors.append(f"Task {task_number}: runner_mode should be 'write'")
                return False
            
            if not context.branch_name:
                self.errors.append(f"Task {task_number}: branch_name is required for write")
                return False
            
            if not context.worktree_path:
                self.errors.append(f"Task {task_number}: worktree_path is required for write")
                return False
            
            if not context.commit_sha_before:
                self.errors.append(f"Task {task_number}: commit_sha_before is required for write")
                return False
            
            # Validate branch name format
            if not branch_name.startswith("execqueue/task"):
                self.errors.append(f"Task {task_number}: invalid branch name format")
                return False
            
            self.write_path_valid = True
            return True
        
        except Exception as e:
            self.errors.append(f"Task {task_number}: write path validation failed: {e}")
            return False
    
    def validate_readonly_path(
        self,
        task_number: int,
        context: Any,
    ) -> bool:
        """Validate read-only path preparation.
        
        Args:
            task_number: Task number
            context: Prepared context
            
        Returns:
            True if valid
        """
        try:
            # Check context has correct mode
            if context.runner_mode.value != "read_only":
                self.errors.append(f"Task {task_number}: runner_mode should be 'read_only'")
                return False
            
            # Read-only should NOT have branch/worktree
            if context.branch_name:
                self.errors.append(f"Task {task_number}: branch_name should be None for read-only")
                return False
            
            if context.worktree_path:
                self.errors.append(f"Task {task_number}: worktree_path should be None for read-only")
                return False
            
            self.readonly_path_valid = True
            return True
        
        except Exception as e:
            self.errors.append(f"Task {task_number}: read-only path validation failed: {e}")
            return False
    
    def assert_no_execution_started(self) -> bool:
        """Assert that no execution was started.
        
        Returns:
            True if all negative assertions pass
        """
        if self.opcode_started:
            self.errors.append("Negative assertion failed: OpenCode session was started")
        
        if self.prompt_dispatched:
            self.errors.append("Negative assertion failed: Prompt was dispatched")
        
        if self.task_execution_started:
            self.errors.append("Negative assertion failed: TaskExecution was created")
        
        if self.status_in_progress:
            self.errors.append("Negative assertion failed: Status changed to in_progress")
        
        if self.commit_created:
            self.errors.append("Negative assertion failed: Commit was created")
        
        self.negative_assertions_passed = len(self.errors) == 0
        return self.negative_assertions_passed
    
    def result(self) -> E2EValidationResult:
        """Get validation result.
        
        Returns:
            E2EValidationResult
        """
        passed = (
            self.write_path_valid and
            self.readonly_path_valid and
            self.negative_assertions_passed and
            len(self.errors) == 0
        )
        
        return E2EValidationResult(
            passed=passed,
            write_path_valid=self.write_path_valid,
            readonly_path_valid=self.readonly_path_valid,
            negative_assertions_passed=self.negative_assertions_passed,
            errors=self.errors.copy(),
        )


def create_e2e_validator() -> E2EValidator:
    """Create a new E2E validator.
    
    Returns:
        E2EValidator instance
    """
    return E2EValidator()
