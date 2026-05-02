"""Validator registry and pipeline for REQ-020.

This module provides:
- ValidatorRegistry: Central registry for validator discovery
- ValidationPipeline: Orchestrates multiple validators with aggregation

Implements WP02: Registry & Pipeline - multiple validators orchestration.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from execqueue.models.task_execution import TaskExecution
from execqueue.runner.validation_models import (
    ValidationStatus,
    ValidationResult,
)
from execqueue.runner.validator import Validator
from execqueue.observability import (
    record_validation_passed,
    record_validation_failed,
    record_validation_review,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class ValidatorRegistry:
    """Central registry for validator discovery and management.

    Usage:
        registry = ValidatorRegistry()
        registry.register("my_validator", MyValidator())
        validator = registry.get("my_validator")
        all_validators = registry.get_all()

    Thread safety:
        Registration is not thread-safe. Register all validators during
        initialization before concurrent access.
    """

    _instance: ValidatorRegistry | None = None

    def __init__(self) -> None:
        """Initialize the registry."""
        self._validators: dict[str, Validator] = {}
        self._factories: dict[str, Callable[[], Validator]] = {}

    @classmethod
    def get_instance(cls) -> ValidatorRegistry:
        """Get the singleton registry instance.

        Returns:
            The global ValidatorRegistry instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, name: str, validator: Validator) -> None:
        """Register a validator instance.

        Args:
            name: Unique validator name
            validator: Validator instance to register

        Raises:
            ValueError: If validator with name already exists
        """
        if name in self._validators:
            raise ValueError(f"Validator '{name}' is already registered")
        self._validators[name] = validator
        logger.debug(f"Registered validator '{name}'")

    def register_factory(
        self, name: str, factory: Callable[[], Validator]
    ) -> None:
        """Register a validator factory.

        Use this for lazy instantiation or validators that need
        runtime configuration.

        Args:
            name: Unique validator name
            factory: Callable that creates validator instances

        Raises:
            ValueError: If validator with name already exists
        """
        if name in self._factories:
            raise ValueError(f"Validator factory '{name}' is already registered")
        self._factories[name] = factory
        logger.debug(f"Registered validator factory '{name}'")

    def get(self, name: str) -> Validator | None:
        """Get a validator by name.

        Args:
            name: Validator name

        Returns:
            Validator instance or None if not found
        """
        if name in self._validators:
            return self._validators[name]

        if name in self._factories:
            validator = self._factories[name]()
            self._validators[name] = validator
            logger.debug(f"Created validator '{name}' from factory")
            return validator

        logger.warning(f"Validator '{name}' not found")
        return None

    def get_all(self) -> dict[str, Validator]:
        """Get all registered validators.

        Returns:
            Dictionary of name -> validator
        """
        return dict(self._validators)

    def get_names(self) -> list[str]:
        """Get all registered validator names.

        Returns:
            List of validator names
        """
        return list(self._validators.keys())

    def clear(self) -> None:
        """Clear all registered validators.

        Warning:
            This should only be used in testing scenarios.
        """
        self._validators.clear()
        logger.debug("Cleared validator registry")


class AggregationStrategy:
    """Strategies for aggregating multiple validation results."""

    @staticmethod
    def first_failure(results: Sequence[ValidationResult]) -> ValidationStatus:
        """Return FAILED if any validator failed, else PASSED.

        This is a fail-fast strategy - first failure determines result.
        """
        for result in results:
            if result.failed:
                return ValidationStatus.FAILED
        return ValidationStatus.PASSED

    @staticmethod
    def any_requires_review(results: Sequence[ValidationResult]) -> ValidationStatus:
        """Return REQUIRES_REVIEW if any validator requires review.

        Priority: FAILED > REQUIRES_REVIEW > PASSED
        """
        has_failure = False
        for result in results:
            if result.failed:
                return ValidationStatus.FAILED
            if result.requires_review:
                has_failure = True
        return ValidationStatus.REQUIRES_REVIEW if has_failure else ValidationStatus.PASSED

    @staticmethod
    def all_passed(results: Sequence[ValidationResult]) -> ValidationStatus:
        """Return PASSED only if ALL validators passed.

        Any failure or review requirement downgrades the result.
        Priority: FAILED > REQUIRES_REVIEW > PASSED
        """
        has_failure = False
        has_review = False

        for result in results:
            if result.failed:
                has_failure = True
            elif result.requires_review:
                has_review = True

        if has_failure:
            return ValidationStatus.FAILED
        if has_review:
            return ValidationStatus.REQUIRES_REVIEW
        return ValidationStatus.PASSED


class ValidationPipeline:
    """Orchestrates multiple validators with aggregation.

    Usage:
        pipeline = ValidationPipeline(
            validators=[validator1, validator2],
            aggregation=AggregationStrategy.any_requires_review,
            fail_fast=True
        )
        result = await pipeline.validate(execution)

    Features:
        - Sequential validator execution
        - Fail-fast support (stop on first failure)
        - Configurable aggregation strategy
        - Aggregated result with all issues
    """

    def __init__(
        self,
        validators: list[Validator],
        aggregation: Callable[[list[ValidationResult]], ValidationStatus] = (
            AggregationStrategy.all_passed
        ),
        fail_fast: bool = False,
        pipeline_name: str = "validation_pipeline",
    ):
        """Initialize the validation pipeline.

        Args:
            validators: List of validators to execute
            aggregation: Strategy for aggregating results
            fail_fast: If True, stop on first failure
            pipeline_name: Name for logging/metrics
        """
        self.validators = validators
        self.aggregation = aggregation
        self.fail_fast = fail_fast
        self.pipeline_name = pipeline_name
        self._logger = logging.getLogger(f"{__name__}.{pipeline_name}")

    async def validate(
        self,
        execution: TaskExecution,
    ) -> ValidationResult:
        """Validate an execution using all registered validators.

        Args:
            execution: The TaskExecution to validate

        Returns:
            Aggregated ValidationResult
        """
        self._logger.info(
            f"Starting validation pipeline '{self.pipeline_name}' "
            f"for execution {execution.id} with {len(self.validators)} validators"
        )

        results: list[ValidationResult] = []
        execution_id = execution.id

        for i, validator in enumerate(self.validators):
            validator_name = getattr(validator, "validator_name", f"validator_{i}")

            try:
                result = await validator.validate(execution)
                results.append(result)

                self._logger.info(
                    f"Validator '{validator_name}' completed: "
                    f"{result.status.value} ({result.issue_count} issues)"
                )

                # Fail-fast: stop on first failure
                if self.fail_fast and result.failed:
                    self._logger.warning(
                        f"Fail-fast triggered by validator '{validator_name}'"
                    )
                    break

            except Exception as e:
                self._logger.error(
                    f"Validator '{validator_name}' raised exception: {e}",
                    exc_info=True,
                )
                # Treat exceptions as failures
                from execqueue.runner.validation_models import ValidationIssue

                results.append(
                    ValidationResult(
                        status=ValidationStatus.FAILED,
                        validator_name=validator_name,
                        issues=[
                            ValidationIssue(
                                code="VALIDATOR_EXCEPTION",
                                message=f"Validator raised exception: {e}",
                                severity="critical",
                            )
                        ],
                    )
                )
                
                # Record metrics for the failed validator
                record_validation_failed()

                if self.fail_fast:
                    break

        # Aggregate results
        if not results:
            self._logger.warning("No validation results produced")
            result = ValidationResult(
                status=ValidationStatus.FAILED,
                validator_name=self.pipeline_name,
                issues=[
                    ValidationIssue(
                        code="NO_RESULTS",
                        message="No validators produced results",
                        severity="critical",
                    )
                ],
            )
            # Record metrics
            record_validation_failed()
            return result

        aggregated_status = self.aggregation(results)
        
        # Record metrics based on aggregated status
        if aggregated_status == ValidationStatus.PASSED:
            record_validation_passed()
        elif aggregated_status == ValidationStatus.FAILED:
            record_validation_failed()
        elif aggregated_status == ValidationStatus.REQUIRES_REVIEW:
            record_validation_review()

        # Merge all issues
        all_issues: list = []
        for result in results:
            all_issues.extend(result.issues)

        # Create aggregated result
        aggregated_result = ValidationResult(
            status=aggregated_status,
            validator_name=self.pipeline_name,
            issues=all_issues,
            metadata={
                "validator_count": len(results),
                "validator_results": [r.status.value for r in results],
                "fail_fast": self.fail_fast,
            },
        )

        self._logger.info(
            f"Validation pipeline '{self.pipeline_name}' completed: "
            f"{aggregated_status.value} ({len(all_issues)} total issues)"
        )

        return aggregated_result

    @property
    def validator_count(self) -> int:
        """Return the number of validators in the pipeline."""
        return len(self.validators)
