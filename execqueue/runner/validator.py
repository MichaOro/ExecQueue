"""Validator interface for task execution result validation.

This module provides an abstract validator interface and implementations
for task execution validation. Validators inspect task execution results
without blocking the runner lifecycle.

The validator returns structured ValidationResult objects for:
- Clear status transitions (PASSED/FAILED/REQUIRES_REVIEW)
- Detailed issue reporting
- Metrics and observability
- Manual intervention support
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from execqueue.models.task_execution import TaskExecution
from execqueue.runner.validation_models import (
    ValidationIssue,
    ValidationStatus,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class Validator(ABC):
    """Abstract base class for task execution validators.

    Validators inspect TaskExecution results and return a structured
    ValidationResult with status, issues, and metadata.

    Note:
        The validator result can affect execution status depending on
        the Runner/WorkflowRunner configuration.

    Important:
        Implementations must not mutate the passed TaskExecution and should
        avoid I/O beyond logging (which is the caller's responsibility).
        The validate() method should be side-effect free regarding the
        execution state.
    """

    @abstractmethod
    async def validate(self, execution: TaskExecution) -> ValidationResult:
        """Validate a task execution.

        Args:
            execution: The TaskExecution to validate. Must not be mutated.

        Returns:
            ValidationResult with status, issues, and metadata

        Note:
            This method should not have side effects on the execution.
            Any logging or metrics should be handled internally or by the caller.
    """
        pass


class MockValidator(Validator):
    """Mock validator for testing purposes.

    This validator can be configured to always pass, always fail, or
    require review, making it useful for testing the validator integration
    in the Runner.

    Attributes:
        always_pass: If True, validate() returns PASSED.
        call_count: Number of times validate() has been called.
    """

    def __init__(
        self,
        always_pass: bool = True,
        validator_name: str = "mock_validator",
    ):
        """Initialize the mock validator.

        Args:
            always_pass: If True (default), validate() returns PASSED.
                        If False, validate() returns FAILED.
            validator_name: Name for the validator (for logging/metrics)
        """
        self.always_pass = always_pass
        self.validator_name = validator_name
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return the number of times validate() has been called."""
        return self._call_count

    async def validate(self, execution: TaskExecution) -> ValidationResult:
        """Validate a task execution.

        This mock implementation ignores the execution and returns
        a deterministic result based on the always_pass configuration.

        Args:
            execution: The TaskExecution to validate (ignored)

        Returns:
            ValidationResult with PASSED or FAILED status
        """
        self._call_count += 1
        logger.debug(
            f"MockValidator.validate() called (call #{self._call_count})"
        )

        if self.always_pass:
            return ValidationResult(
                status=ValidationStatus.PASSED,
                validator_name=self.validator_name,
                metadata={"call_count": self._call_count},
            )
        else:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                validator_name=self.validator_name,
                issues=[
                    ValidationIssue(
                        code="MOCK_FAILURE",
                        message="Mock validator configured to fail",
                        severity="critical",
                    )
                ],
                metadata={"call_count": self._call_count},
            )


class MockReviewValidator(Validator):
    """Mock validator that returns REQUIRES_REVIEW status.

    Useful for testing manual intervention flows in the orchestrator.
    """

    def __init__(
        self,
        validator_name: str = "mock_review_validator",
        review_message: str = "Manual review required",
    ):
        """Initialize the review validator.

        Args:
            validator_name: Name for the validator
            review_message: Message to include in the result
        """
        self.validator_name = validator_name
        self.review_message = review_message
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return the number of times validate() has been called."""
        return self._call_count

    async def validate(self, execution: TaskExecution) -> ValidationResult:
        """Validate a task execution.

        This mock implementation always returns REQUIRES_REVIEW status.

        Args:
            execution: The TaskExecution to validate (ignored)

        Returns:
            ValidationResult with REQUIRES_REVIEW status
        """
        self._call_count += 1
        logger.debug(
            f"MockReviewValidator.validate() called (call #{self._call_count})"
        )

        return ValidationResult(
            status=ValidationStatus.REQUIRES_REVIEW,
            validator_name=self.validator_name,
            issues=[
                ValidationIssue(
                    code="REQUIRES_REVIEW",
                    message=self.review_message,
                    severity="warning",
                )
            ],
            metadata={"call_count": self._call_count},
        )
