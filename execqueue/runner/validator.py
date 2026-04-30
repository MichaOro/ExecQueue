"""Validator interface for task execution result validation.

This module provides an abstract validator interface and a mock implementation
for testing purposes. Validators can be used to inspect task execution results
without blocking the runner lifecycle.

The validator is intentionally minimal - it only validates and returns a boolean.
Any side effects (logging, metrics, etc.) are handled by the caller.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from execqueue.models.task_execution import TaskExecution

logger = logging.getLogger(__name__)


class Validator(ABC):
    """Abstract base class for task execution validators.

    Validators inspect TaskExecution results and return a boolean indicating
    whether the execution passed validation.

    Note:
        This is a minimal interface. The validator result is currently only
        logged by the Runner and does not affect execution status.

    Important:
        Implementations must not mutate the passed TaskExecution and should
        avoid I/O beyond logging (which is the caller's responsibility).
        The validate() method should be side-effect free regarding the
        execution state.
    """

    @abstractmethod
    async def validate(self, execution: TaskExecution) -> bool:
        """Validate a task execution.

        Args:
            execution: The TaskExecution to validate. Must not be mutated.

        Returns:
            True if validation passed, False otherwise

        Note:
            This method should not have side effects on the execution.
            Any logging or metrics should be handled internally or by the caller.
        """
        pass


class MockValidator(Validator):
    """Mock validator for testing purposes.

    This validator can be configured to always pass or always fail,
    making it useful for testing the validator integration in the Runner.

    Attributes:
        always_pass: If True, validate() always returns True.
        call_count: Number of times validate() has been called.
    """

    def __init__(self, always_pass: bool = True):
        """Initialize the mock validator.

        Args:
            always_pass: If True (default), validate() always returns True.
                        If False, validate() always returns False.
        """
        self.always_pass = always_pass
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return the number of times validate() has been called."""
        return self._call_count

    async def validate(self, execution: TaskExecution) -> bool:
        """Validate a task execution.

        This mock implementation ignores the execution and returns
        a deterministic result based on the always_pass configuration.

        Args:
            execution: The TaskExecution to validate (ignored)

        Returns:
            True if always_pass is True, False otherwise
        """
        self._call_count += 1
        logger.debug(f"MockValidator.validate() called (call #{self._call_count})")
        return self.always_pass
