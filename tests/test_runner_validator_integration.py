"""Integration tests for Validator integration in Runner.

These tests verify that the Validator is correctly integrated into the Runner
and that validation results are logged appropriately without affecting
execution status.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.runner.config import RunnerConfig
from execqueue.runner.main import Runner
from execqueue.runner.validator import MockValidator, Validator


@pytest.mark.asyncio
async def test_runner_without_validator():
    """Test that Runner works without a validator."""
    config = RunnerConfig.create_default()
    runner = Runner(config)

    # Should not raise
    assert runner._validator is None


@pytest.mark.asyncio
async def test_runner_with_validator():
    """Test that Runner accepts a validator."""
    config = RunnerConfig.create_default()
    validator = MockValidator(always_pass=True)
    runner = Runner(config, validator=validator)

    assert runner._validator is validator


@pytest.mark.asyncio
async def test_runner_validator_always_pass():
    """Test that successful validation is logged."""
    config = RunnerConfig.create_default()
    validator = MockValidator(always_pass=True)
    runner = Runner(config, validator=validator)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    # Mock session
    session = MagicMock()

    # Patch logger to capture output
    with patch("execqueue.runner.main.logger") as mock_logger:
        await runner._process_execution(session, execution)

        # Verify validation passed was logged
        # The INFO log for validation passed should have been called
        info_calls = [
            call for call in mock_logger.info.call_args_list
            if "Validation passed" in str(call)
        ]
        assert len(info_calls) >= 1


@pytest.mark.asyncio
async def test_runner_validator_always_fail():
    """Test that failed validation is logged as warning."""
    config = RunnerConfig.create_default()
    validator = MockValidator(always_pass=False)
    runner = Runner(config, validator=validator)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    session = MagicMock()

    with patch("execqueue.runner.main.logger") as mock_logger:
        await runner._process_execution(session, execution)

        # Verify validation failed was logged as warning
        warning_calls = [
            call for call in mock_logger.warning.call_args_list
            if "Validation failed" in str(call)
        ]
        assert len(warning_calls) >= 1


@pytest.mark.asyncio
async def test_runner_validator_exception():
    """Test that validator exceptions are logged but don't block."""
    config = RunnerConfig.create_default()

    # Create a validator that raises
    class FailingValidator(Validator):
        async def validate(self, execution: TaskExecution) -> bool:
            raise ValueError("Validation error")

    validator = FailingValidator()
    runner = Runner(config, validator=validator)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    session = MagicMock()

    with patch("execqueue.runner.main.logger") as mock_logger:
        # Should not raise
        await runner._process_execution(session, execution)

        # Verify exception was logged as warning
        warning_calls = [
            call for call in mock_logger.warning.call_args_list
            if "Validator exception" in str(call)
        ]
        assert len(warning_calls) >= 1


@pytest.mark.asyncio
async def test_runner_validator_called_once_per_execution():
    """Test that validator is called exactly once per execution."""
    config = RunnerConfig.create_default()
    validator = MockValidator(always_pass=True)
    runner = Runner(config, validator=validator)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    session = MagicMock()

    initial_count = validator.call_count
    await runner._process_execution(session, execution)

    assert validator.call_count == initial_count + 1


@pytest.mark.asyncio
async def test_runner_validator_does_not_affect_status():
    """Test that validator result does not change execution status."""
    config = RunnerConfig.create_default()
    validator = MockValidator(always_pass=False)  # Will fail validation
    runner = Runner(config, validator=validator)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    initial_status = execution.status

    session = MagicMock()
    await runner._process_execution(session, execution)

    # Status should be unchanged
    assert execution.status == initial_status
