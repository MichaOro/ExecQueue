"""Tests for validation pipeline (REQ-020/REQ-021 Sections 4)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from execqueue.models.task_execution import TaskExecution
from execqueue.runner.validation_models import (
    ValidationIssue,
    ValidationStatus,
    ValidationResult,
)
from execqueue.runner.validator import MockValidator, MockReviewValidator, Validator
from execqueue.runner.validation_pipeline import (
    AggregationStrategy,
    ValidationPipeline,
    ValidatorRegistry,
)


class TestValidatorRegistry:
    """Test ValidatorRegistry functionality."""

    def test_singleton_pattern(self):
        """Test that ValidatorRegistry follows singleton pattern."""
        registry1 = ValidatorRegistry.get_instance()
        registry2 = ValidatorRegistry.get_instance()
        
        assert registry1 is registry2

    def test_register_and_get(self):
        """Test registering and getting validators."""
        registry = ValidatorRegistry()
        validator = MockValidator()
        
        registry.register("test_validator", validator)
        
        retrieved = registry.get("test_validator")
        assert retrieved is validator

    def test_register_duplicate_raises(self):
        """Test that registering duplicate validator raises ValueError."""
        registry = ValidatorRegistry()
        validator1 = MockValidator()
        validator2 = MockValidator()
        
        registry.register("test_validator", validator1)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register("test_validator", validator2)

    def test_get_nonexistent_returns_none(self):
        """Test that getting nonexistent validator returns None."""
        registry = ValidatorRegistry()
        
        validator = registry.get("nonexistent")
        assert validator is None

    def test_get_all(self):
        """Test getting all validators."""
        registry = ValidatorRegistry()
        validator1 = MockValidator()
        validator2 = MockValidator()
        
        registry.register("validator1", validator1)
        registry.register("validator2", validator2)
        
        all_validators = registry.get_all()
        assert len(all_validators) == 2
        assert all_validators["validator1"] is validator1
        assert all_validators["validator2"] is validator2

    def test_get_names(self):
        """Test getting validator names."""
        registry = ValidatorRegistry()
        validator1 = MockValidator()
        validator2 = MockValidator()
        
        registry.register("validator1", validator1)
        registry.register("validator2", validator2)
        
        names = registry.get_names()
        assert len(names) == 2
        assert "validator1" in names
        assert "validator2" in names

    def test_clear(self):
        """Test clearing registry."""
        registry = ValidatorRegistry()
        validator = MockValidator()
        
        registry.register("test_validator", validator)
        assert len(registry.get_all()) == 1
        
        registry.clear()
        assert len(registry.get_all()) == 0


class TestAggregationStrategy:
    """Test AggregationStrategy methods."""

    def test_first_failure_with_failure(self):
        """Test first_failure strategy with failure."""
        results = [
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v1"),
            ValidationResult(status=ValidationStatus.FAILED, validator_name="v2"),
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v3"),
        ]
        
        status = AggregationStrategy.first_failure(results)
        assert status == ValidationStatus.FAILED

    def test_first_failure_all_passed(self):
        """Test first_failure strategy with all passed."""
        results = [
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v1"),
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v2"),
        ]
        
        status = AggregationStrategy.first_failure(results)
        assert status == ValidationStatus.PASSED

    def test_any_requires_review_with_failure(self):
        """Test any_requires_review strategy with failure."""
        results = [
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v1"),
            ValidationResult(status=ValidationStatus.FAILED, validator_name="v2"),
            ValidationResult(status=ValidationStatus.REQUIRES_REVIEW, validator_name="v3"),
        ]
        
        status = AggregationStrategy.any_requires_review(results)
        assert status == ValidationStatus.FAILED

    def test_any_requires_review_with_review(self):
        """Test any_requires_review strategy with requires_review."""
        results = [
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v1"),
            ValidationResult(status=ValidationStatus.REQUIRES_REVIEW, validator_name="v2"),
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v3"),
        ]
        
        status = AggregationStrategy.any_requires_review(results)
        assert status == ValidationStatus.REQUIRES_REVIEW

    def test_any_requires_review_all_passed(self):
        """Test any_requires_review strategy with all passed."""
        results = [
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v1"),
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v2"),
        ]
        
        status = AggregationStrategy.any_requires_review(results)
        assert status == ValidationStatus.PASSED

    def test_all_passed_with_failure(self):
        """Test all_passed strategy with failure."""
        results = [
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v1"),
            ValidationResult(status=ValidationStatus.FAILED, validator_name="v2"),
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v3"),
        ]
        
        status = AggregationStrategy.all_passed(results)
        assert status == ValidationStatus.FAILED

    def test_all_passed_with_review(self):
        """Test all_passed strategy with requires_review."""
        results = [
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v1"),
            ValidationResult(status=ValidationStatus.REQUIRES_REVIEW, validator_name="v2"),
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v3"),
        ]
        
        status = AggregationStrategy.all_passed(results)
        assert status == ValidationStatus.REQUIRES_REVIEW

    def test_all_passed_all_passed(self):
        """Test all_passed strategy with all passed."""
        results = [
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v1"),
            ValidationResult(status=ValidationStatus.PASSED, validator_name="v2"),
        ]
        
        status = AggregationStrategy.all_passed(results)
        assert status == ValidationStatus.PASSED


class TestValidationPipeline:
    """Test ValidationPipeline functionality."""

    @pytest.fixture
    def mock_execution(self):
        """Create a mock TaskExecution."""
        execution = MagicMock(spec=TaskExecution)
        execution.id = "test-execution-id"
        return execution

    @pytest.mark.asyncio
    async def test_validate_single_validator_pass(self, mock_execution):
        """Test validation with single passing validator."""
        validator = MockValidator(always_pass=True)
        pipeline = ValidationPipeline(validators=[validator])
        
        result = await pipeline.validate(mock_execution)
        
        assert result.status == ValidationStatus.PASSED
        assert result.validator_name == "validation_pipeline"
        assert len(result.issues) == 0
        assert validator.call_count == 1

    @pytest.mark.asyncio
    async def test_validate_single_validator_fail(self, mock_execution):
        """Test validation with single failing validator."""
        validator = MockValidator(always_pass=False)
        pipeline = ValidationPipeline(validators=[validator])
        
        result = await pipeline.validate(mock_execution)
        
        assert result.status == ValidationStatus.FAILED
        assert result.validator_name == "validation_pipeline"
        assert len(result.issues) == 1
        assert result.issues[0].code == "MOCK_FAILURE"
        assert validator.call_count == 1

    @pytest.mark.asyncio
    async def test_validate_multiple_validators_all_pass(self, mock_execution):
        """Test validation with multiple passing validators."""
        validator1 = MockValidator(always_pass=True)
        validator2 = MockValidator(always_pass=True)
        pipeline = ValidationPipeline(validators=[validator1, validator2])
        
        result = await pipeline.validate(mock_execution)
        
        assert result.status == ValidationStatus.PASSED
        assert len(result.issues) == 0
        assert validator1.call_count == 1
        assert validator2.call_count == 1

    @pytest.mark.asyncio
    async def test_validate_multiple_validators_one_fail(self, mock_execution):
        """Test validation with multiple validators where one fails."""
        validator1 = MockValidator(always_pass=True)
        validator2 = MockValidator(always_pass=False)
        pipeline = ValidationPipeline(validators=[validator1, validator2])
        
        result = await pipeline.validate(mock_execution)
        
        assert result.status == ValidationStatus.FAILED
        assert len(result.issues) == 1
        assert validator1.call_count == 1
        assert validator2.call_count == 1

    @pytest.mark.asyncio
    async def test_validate_with_requires_review(self, mock_execution):
        """Test validation with requires_review validator."""
        validator = MockReviewValidator()
        pipeline = ValidationPipeline(validators=[validator])
        
        result = await pipeline.validate(mock_execution)
        
        assert result.status == ValidationStatus.REQUIRES_REVIEW
        assert len(result.issues) == 1
        assert result.issues[0].code == "REQUIRES_REVIEW"
        assert validator.call_count == 1

    @pytest.mark.asyncio
    async def test_validate_fail_fast_enabled(self, mock_execution):
        """Test validation with fail_fast enabled."""
        validator1 = MockValidator(always_pass=True)
        validator2 = MockValidator(always_pass=False)  # Will fail
        validator3 = MockValidator(always_pass=True)   # Should not be called
        pipeline = ValidationPipeline(validators=[validator1, validator2, validator3], fail_fast=True)
        
        result = await pipeline.validate(mock_execution)
        
        assert result.status == ValidationStatus.FAILED
        assert validator1.call_count == 1
        assert validator2.call_count == 1
        assert validator3.call_count == 0  # Should not be called due to fail_fast

    @pytest.mark.asyncio
    async def test_validate_validator_exception(self, mock_execution):
        """Test validation when validator raises exception."""
        validator = MagicMock(spec=Validator)
        validator.validate = AsyncMock(side_effect=Exception("Test exception"))
        validator.validator_name = "exception_validator"
        
        pipeline = ValidationPipeline(validators=[validator])
        
        result = await pipeline.validate(mock_execution)
        
        assert result.status == ValidationStatus.FAILED
        assert len(result.issues) == 1
        assert result.issues[0].code == "VALIDATOR_EXCEPTION"
        assert "Test exception" in result.issues[0].message

    @pytest.mark.asyncio
    async def test_validate_no_validators(self, mock_execution):
        """Test validation with no validators."""
        pipeline = ValidationPipeline(validators=[])
        
        result = await pipeline.validate(mock_execution)
        
        assert result.status == ValidationStatus.FAILED
        assert len(result.issues) == 1
        assert result.issues[0].code == "NO_RESULTS"

    def test_validator_count(self):
        """Test validator_count property."""
        validator1 = MockValidator()
        validator2 = MockValidator()
        pipeline = ValidationPipeline(validators=[validator1, validator2])
        
        assert pipeline.validator_count == 2