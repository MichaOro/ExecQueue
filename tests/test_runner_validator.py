"""Unit tests for the Validator interface and MockValidator.

These tests verify the basic validator functionality without integrating
it into the Runner lifecycle.
"""

import pytest
from uuid import uuid4

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.runner.validator import MockValidator, Validator


def test_validator_is_abstract():
    """Test that Validator is an abstract base class."""
    with pytest.raises(TypeError):
        Validator()  # type: ignore


@pytest.mark.asyncio
async def test_mock_validator_always_pass():
    """Test MockValidator with always_pass=True."""
    validator = MockValidator(always_pass=True)

    # Create a mock execution
    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    result = await validator.validate(execution)
    assert result is True
    assert validator.call_count == 1


@pytest.mark.asyncio
async def test_mock_validator_always_fail():
    """Test MockValidator with always_pass=False."""
    validator = MockValidator(always_pass=False)

    # Create a mock execution
    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    result = await validator.validate(execution)
    assert result is False
    assert validator.call_count == 1


@pytest.mark.asyncio
async def test_mock_validator_call_count():
    """Test that call_count increments correctly."""
    validator = MockValidator(always_pass=True)

    assert validator.call_count == 0

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    # Call validate multiple times
    for i in range(1, 6):
        await validator.validate(execution)
        assert validator.call_count == i


@pytest.mark.asyncio
async def test_mock_validator_independent_instances():
    """Test that multiple validator instances are independent."""
    validator1 = MockValidator(always_pass=True)
    validator2 = MockValidator(always_pass=False)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    result1 = await validator1.validate(execution)
    result2 = await validator2.validate(execution)

    assert result1 is True
    assert result2 is False
    assert validator1.call_count == 1
    assert validator2.call_count == 1


@pytest.mark.asyncio
async def test_mock_validator_execution_ignored():
    """Test that the execution parameter is ignored by MockValidator."""
    validator = MockValidator(always_pass=True)

    # Create different executions
    execution1 = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="runner-1",
        status=ExecutionStatus.DONE.value,
    )

    execution2 = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="runner-2",
        status=ExecutionStatus.FAILED.value,
    )

    # Both should return True regardless of execution state
    result1 = await validator.validate(execution1)
    result2 = await validator.validate(execution2)

    assert result1 is True
    assert result2 is True
