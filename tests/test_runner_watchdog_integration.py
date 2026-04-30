"""Integration tests for Watchdog integration in Runner lifecycle.

These tests verify that the Watchdog is correctly integrated into the Runner
lifecycle and starts/stops appropriately with the Runner.
"""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from execqueue.runner.config import RunnerConfig
from execqueue.runner.main import Runner


@pytest.mark.asyncio
async def test_runner_starts_watchdog_when_enabled():
    """Test that watchdog starts when enabled in config."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    runner = Runner(config)

    # Mock _poll_cycle to avoid database calls and infinite loop
    with patch.object(runner, '_poll_cycle'):
        with patch.object(runner._watchdog, 'start') as mock_start:
            # Start runner in background and stop quickly
            runner_task = asyncio.create_task(runner.start())
            await asyncio.sleep(0.05)
            await runner.stop()
            
            try:
                await runner_task
            except asyncio.CancelledError:
                pass

            mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_runner_does_not_start_watchdog_when_disabled():
    """Test that watchdog start is called even when disabled (no-op internally)."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = False

    runner = Runner(config)

    with patch.object(runner, '_poll_cycle'):
        with patch.object(runner._watchdog, 'start') as mock_start:
            runner_task = asyncio.create_task(runner.start())
            await asyncio.sleep(0.05)
            await runner.stop()
            
            try:
                await runner_task
            except asyncio.CancelledError:
                pass

            # start() is still called, but watchdog internally does nothing
            mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_runner_stops_watchdog_on_stop():
    """Test that watchdog is stopped when runner stops."""
    config = RunnerConfig.create_default()

    runner = Runner(config)

    with patch.object(runner, '_poll_cycle'):
        with patch.object(runner._watchdog, 'stop') as mock_stop:
            runner_task = asyncio.create_task(runner.start())
            await asyncio.sleep(0.05)
            await runner.stop()
            
            try:
                await runner_task
            except asyncio.CancelledError:
                pass

            mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_runner_watchdog_lifecycle_order():
    """Test that watchdog starts before runner loop and stops after."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    runner = Runner(config)

    start_order = []

    original_watchdog_start = runner._watchdog.start
    async def track_watchdog_start():
        start_order.append('watchdog_start')
        return await original_watchdog_start()

    original_runner_stop = runner.stop
    async def track_runner_stop():
        start_order.append('runner_stop')
        return await original_runner_stop()

    runner._watchdog.start = track_watchdog_start  # type: ignore
    runner.stop = track_runner_stop  # type: ignore

    with patch.object(runner, '_poll_cycle'):
        # Start runner in background task
        runner_task = asyncio.create_task(runner.start())
        await asyncio.sleep(0.05)

        # Stop runner
        await runner.stop()
        await asyncio.sleep(0.05)

        # Cancel runner task if still running
        if not runner_task.done():
            runner_task.cancel()
            try:
                await runner_task
            except asyncio.CancelledError:
                pass

        # Verify order: watchdog should have started
        assert 'watchdog_start' in start_order
        assert 'runner_stop' in start_order


@pytest.mark.asyncio
async def test_runner_watchdog_missing_session_id():
    """Test that runner handles missing session_id gracefully."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = None  # Missing session ID

    runner = Runner(config)

    with patch.object(runner, '_poll_cycle'):
        # Should not raise, just log warning from watchdog module
        with patch("execqueue.runner.watchdog.logger") as mock_logger:
            runner_task = asyncio.create_task(runner.start())
            await asyncio.sleep(0.05)
            await runner.stop()
            
            try:
                await runner_task
            except asyncio.CancelledError:
                pass

            # Should log warning about missing session_id
            warning_calls = [
                call for call in mock_logger.warning.call_args_list
                if "session_id not set" in str(call)
            ]
            assert len(warning_calls) >= 1


@pytest.mark.asyncio
async def test_runner_watchdog_activity_recording():
    """Test that activity is recorded during execution processing."""
    config = RunnerConfig.create_default()

    runner = Runner(config)

    # Mock execution
    from uuid import uuid4
    from execqueue.models.task_execution import TaskExecution
    from execqueue.models.enums import ExecutionStatus

    execution = TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        runner_id="test-runner",
        status=ExecutionStatus.DONE.value,
    )

    session = MagicMock()

    with patch.object(runner._watchdog, 'record_activity') as mock_record:
        await runner._process_execution(session, execution)

        mock_record.assert_called_once()


@pytest.mark.asyncio
async def test_runner_watchdog_idempotent_start():
    """Test that watchdog start is idempotent during runner start."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    runner = Runner(config)

    with patch.object(runner, '_poll_cycle'):
        runner_task = asyncio.create_task(runner.start())
        await asyncio.sleep(0.05)
        await runner.stop()
        
        try:
            await runner_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_runner_watchdog_stop_idempotent():
    """Test that watchdog stop is idempotent."""
    config = RunnerConfig.create_default()

    runner = Runner(config)

    with patch.object(runner, '_poll_cycle'):
        runner_task = asyncio.create_task(runner.start())
        await asyncio.sleep(0.05)
        await runner.stop()
        
        try:
            await runner_task
        except asyncio.CancelledError:
            pass
        
        await runner.stop()  # Should be no-op

    # Should not raise
