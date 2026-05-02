"""Integration tests for Validator integration in Runner.

These tests verify that the Validator is correctly integrated into the Runner
and that validation results are logged appropriately without affecting
execution status.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.runner.config import RunnerConfig
from execqueue.runner.main import Runner
from execqueue.runner.validator import MockValidator, Validator
from execqueue.runner.validation_models import ValidationResult, ValidationStatus


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
    """Test that successful validation runs the execution chain."""
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

    # The execution chain should be invoked
    # Note: ExecutionChain is imported locally in _process_execution,
    # so we patch at the module level
    with patch("execqueue.runner.execution_chain.ExecutionChain") as mock_chain_class:
        mock_chain_instance = MagicMock()
        mock_chain_instance.execute = AsyncMock(return_value=True)
        mock_chain_class.return_value = mock_chain_instance

        await runner._process_execution(session, execution)

        # Verify ExecutionChain was created and executed
        mock_chain_class.assert_called_once()
        mock_chain_instance.execute.assert_called_once()


@pytest.mark.asyncio
async def test_runner_validator_always_fail():
    """Test that failed validation still runs the execution chain (handles result)."""
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

    with patch("execqueue.runner.execution_chain.ExecutionChain") as mock_chain_class:
        mock_chain_instance = MagicMock()
        mock_chain_instance.execute = AsyncMock(return_value=False)
        mock_chain_class.return_value = mock_chain_instance

        await runner._process_execution(session, execution)

        # Verification pipeline is always constructed; execution chain handles the result
        mock_chain_class.assert_called_once()
        mock_chain_instance.execute.assert_called_once()


@pytest.mark.asyncio
async def test_runner_validator_exception():
    """Test that validator exceptions are handled by the pipeline."""
    config = RunnerConfig.create_default()

    # Create a validator that raises
    class FailingValidator(Validator):
        async def validate(self, execution: TaskExecution) -> ValidationResult:
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

    with patch("execqueue.runner.execution_chain.ExecutionChain") as mock_chain_class:
        mock_chain_instance = MagicMock()
        mock_chain_instance.execute = AsyncMock(return_value=False)
        mock_chain_class.return_value = mock_chain_instance

        # Should not raise - the pipeline catches exceptions
        await runner._process_execution(session, execution)

        mock_chain_class.assert_called_once()
        mock_chain_instance.execute.assert_called_once()


@pytest.mark.asyncio
async def test_runner_validator_pipeline_passed_to_execution_chain():
    """Test that validator pipeline is passed to execution chain."""
    config = RunnerConfig.create_default()
    runner = Runner(config)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    session = MagicMock()

    with patch("execqueue.runner.execution_chain.ExecutionChain") as mock_chain_class:
        mock_chain_instance = MagicMock()
        mock_chain_instance.execute = AsyncMock(return_value=True)
        mock_chain_class.return_value = mock_chain_instance

        await runner._process_execution(session, execution)

    # Verify the validation pipeline was passed to the execution chain
    mock_chain_instance.execute.assert_called_once()
    call_kwargs = mock_chain_instance.execute.call_args.kwargs
    assert "validation_pipeline" in call_kwargs
    assert call_kwargs["validation_pipeline"] is runner._validation_pipeline


@pytest.mark.asyncio
async def test_runner_validator_does_not_affect_status():
    """Test that validator result does not change execution status directly."""
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

    with patch("execqueue.runner.execution_chain.ExecutionChain") as mock_chain_class:
        mock_chain_instance = MagicMock()
        mock_chain_instance.execute = AsyncMock(return_value=False)
        mock_chain_class.return_value = mock_chain_instance

        await runner._process_execution(session, execution)

    # Status should remain DONE (ExecutionChain handles status changes internally)
    assert execution.status == ExecutionStatus.DONE.value


@pytest.mark.asyncio
async def test_runner_without_validation_pipeline():
    """Test that Runner works without validation pipeline."""
    config = RunnerConfig.create_default()
    config.validation_enabled = False
    runner = Runner(config, validator=None)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    session = MagicMock()

    with patch("execqueue.runner.main.logger") as mock_logger:
        await runner._process_execution(session, execution)

        # Should log that no validation pipeline is configured
        info_calls = [
            call for call in mock_logger.info.call_args_list
            if "No validation pipeline configured" in str(call)
        ]
        assert len(info_calls) >= 1


@pytest.mark.asyncio
async def test_runner_skips_non_done_executions():
    """Test that only DONE executions trigger the execution chain."""
    config = RunnerConfig.create_default()
    runner = Runner(config)

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.IN_PROGRESS.value,
    )

    session = MagicMock()

    with patch("execqueue.runner.execution_chain.ExecutionChain") as mock_chain_class:
        await runner._process_execution(session, execution)

        # ExecutionChain should NOT be created for in-progress executions
        mock_chain_class.assert_not_called()
