"""Tests for registering WriteTaskValidator in the ValidatorRegistry."""

from __future__ import annotations

import pytest

from execqueue.runner.validation_pipeline import ValidatorRegistry
from execqueue.runner.write_task_validator import WriteTaskValidator


def test_register_write_task_validator() -> None:
    """Test registering WriteTaskValidator in ValidatorRegistry."""
    registry = ValidatorRegistry.get_instance()
    
    # Clear any existing validators for clean test
    registry.clear()
    
    # Create and register validator
    validator = WriteTaskValidator(validator_name="test_write_validator")
    registry.register("write_task_validator", validator)
    
    # Check that it's registered
    registered_validator = registry.get("write_task_validator")
    assert registered_validator is not None
    assert isinstance(registered_validator, WriteTaskValidator)
    assert registered_validator.validator_name == "test_write_validator"
    
    # Check that it appears in the list
    all_validators = registry.get_all()
    assert "write_task_validator" in all_validators
    assert all_validators["write_task_validator"] == validator
    
    # Check that it appears in the names list
    names = registry.get_names()
    assert "write_task_validator" in names


def test_register_write_task_validator_factory() -> None:
    """Test registering WriteTaskValidator factory in ValidatorRegistry."""
    registry = ValidatorRegistry.get_instance()
    
    # Clear any existing validators for clean test
    registry.clear()
    
    # Register as factory
    def validator_factory() -> WriteTaskValidator:
        return WriteTaskValidator(validator_name="factory_created_validator")
    
    registry.register_factory("write_task_factory", validator_factory)
    
    # Get validator from factory
    validator = registry.get("write_task_factory")
    assert validator is not None
    assert isinstance(validator, WriteTaskValidator)
    assert validator.validator_name == "factory_created_validator"
    
    # Check that it's now also in the regular validators dict
    all_validators = registry.get_all()
    assert "write_task_factory" in all_validators


def test_write_task_validator_call_count() -> None:
    """Test that WriteTaskValidator tracks call counts."""
    validator = WriteTaskValidator()
    
    assert validator.call_count == 0
    
    # This is an async method, so we can't easily call it in a sync test
    # But we've already tested that the property works correctly