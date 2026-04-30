"""Unit tests for the Watchdog class.

These tests verify the Watchdog behavior without requiring a real OpenCode
session. HTTP requests are mocked using httpx.MockTransport or MagicMock.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import httpx

from execqueue.runner.config import RunnerConfig
from execqueue.runner.watchdog import Watchdog


def test_watchdog_disabled_by_default():
    """Test that watchdog does not start when disabled."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = False
    config.watchdog_session_id = "test-session"

    watchdog = Watchdog(config, poll_interval=1)

    # Should not raise, should be no-op
    asyncio.run(watchdog.start())

    assert not watchdog.is_running
    assert watchdog.continues_sent == 0


@pytest.mark.asyncio
async def test_watchdog_requires_session_id():
    """Test that watchdog does not start without session_id."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = None

    watchdog = Watchdog(config, poll_interval=1)

    # Should log warning and not start
    await watchdog.start()

    assert not watchdog.is_running
    assert watchdog.continues_sent == 0


@pytest.mark.asyncio
async def test_watchdog_starts_and_stops():
    """Test basic watchdog start/stop lifecycle."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session-123"

    watchdog = Watchdog(config, poll_interval=1)

    await watchdog.start()
    assert watchdog.is_running

    await watchdog.stop()
    assert not watchdog.is_running


@pytest.mark.asyncio
async def test_watchdog_stop_idempotent():
    """Test that stop() can be called multiple times safely."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    watchdog = Watchdog(config, poll_interval=1)

    await watchdog.start()
    await watchdog.stop()
    await watchdog.stop()  # Should not raise

    assert not watchdog.is_running


@pytest.mark.asyncio
async def test_watchdog_record_activity():
    """Test that activity recording works."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    watchdog = Watchdog(config, poll_interval=1)

    # Record activity
    watchdog.record_activity()

    assert watchdog._last_activity_time is not None


@pytest.mark.asyncio
async def test_watchdog_max_continues_limit():
    """Test that watchdog respects max_continues limit."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"
    config.watchdog_max_continues = 2
    config.watchdog_idle_seconds = 1  # Short idle time for testing

    # Mock HTTP client to avoid real requests
    async def mock_post(url, json=None):
        return httpx.Response(200, json={"status": "ok"})

    watchdog = Watchdog(config, poll_interval=1)
    watchdog._http_client = httpx.AsyncClient(timeout=1.0)
    watchdog._http_client.post = mock_post  # type: ignore

    # Manually set activity time to trigger pings
    watchdog._last_activity_time = 0  # Use monotonic time directly

    # Send pings manually (simulating loop behavior)
    await watchdog._send_continue_ping()
    await watchdog._send_continue_ping()

    assert watchdog.continues_sent == 2

    # Third ping should not increment due to max_continues
    # (though _should_send_ping would prevent it in the loop)
    await watchdog.stop()


@pytest.mark.asyncio
async def test_watchdog_http_error_logged():
    """Test that HTTP errors are logged but don't crash the watchdog."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    # Mock HTTP client that returns error
    async def mock_post_error(url, json=None):
        return httpx.Response(500, text="Internal Server Error")

    watchdog = Watchdog(config, poll_interval=1)
    watchdog._http_client = httpx.AsyncClient(timeout=1.0)
    watchdog._http_client.post = mock_post_error  # type: ignore

    # Manually trigger ping (use monotonic time)
    watchdog._last_activity_time = 0
    watchdog._continues_sent = 0

    # Should not raise
    await watchdog._send_continue_ping()

    # continues_sent should not increment on error
    assert watchdog.continues_sent == 0

    await watchdog.stop()


@pytest.mark.asyncio
async def test_watchdog_request_error_handled():
    """Test that request errors are handled gracefully."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    # Mock HTTP client that raises request error
    async def mock_post_error(url, json=None):
        raise httpx.RequestError("Connection failed")

    watchdog = Watchdog(config, poll_interval=1)
    watchdog._http_client = httpx.AsyncClient(timeout=1.0)
    watchdog._http_client.post = mock_post_error  # type: ignore

    watchdog._last_activity_time = 0

    # Should not raise
    await watchdog._send_continue_ping()

    assert watchdog.continues_sent == 0

    await watchdog.stop()


def test_watchdog_should_send_ping_no_activity():
    """Test that ping is not sent without recorded activity."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    watchdog = Watchdog(config, poll_interval=1)

    # No activity recorded
    assert watchdog._should_send_ping() is False


def test_watchdog_should_send_ping_not_idle():
    """Test that ping is not sent before idle threshold."""
    import time
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"
    config.watchdog_idle_seconds = 90

    watchdog = Watchdog(config, poll_interval=1)

    # Activity recorded recently (use monotonic time)
    watchdog._last_activity_time = time.monotonic() - 10

    assert watchdog._should_send_ping() is False


def test_watchdog_should_send_ping_idle():
    """Test that ping is sent when idle threshold exceeded."""
    import time
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"
    config.watchdog_idle_seconds = 30

    watchdog = Watchdog(config, poll_interval=1)

    # Activity recorded long ago (use monotonic time)
    watchdog._last_activity_time = time.monotonic() - 120

    assert watchdog._should_send_ping() is True


def test_watchdog_should_send_ping_max_reached():
    """Test that ping is not sent after max_continues reached."""
    import time
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"
    config.watchdog_idle_seconds = 10
    config.watchdog_max_continues = 5

    watchdog = Watchdog(config, poll_interval=1)

    # Activity recorded long ago (use monotonic time)
    watchdog._last_activity_time = time.monotonic() - 120
    watchdog._continues_sent = 5

    assert watchdog._should_send_ping() is False


@pytest.mark.asyncio
async def test_watchdog_idempotent_start():
    """Test that start() is idempotent."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    watchdog = Watchdog(config, poll_interval=1)

    await watchdog.start()
    first_task = watchdog._task

    # Start again
    await watchdog.start()

    # Should be the same task
    assert watchdog._task is first_task
    assert watchdog.is_running

    await watchdog.stop()


@pytest.mark.asyncio
async def test_watchdog_cancelled_error_handling():
    """Test that CancelledError is handled gracefully."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    watchdog = Watchdog(config, poll_interval=1)

    await watchdog.start()

    # Cancel the task directly
    watchdog._task.cancel()

    try:
        await watchdog._task
    except asyncio.CancelledError:
        pass

    # Stop should handle this gracefully
    await watchdog.stop()

    assert not watchdog.is_running


def test_watchdog_custom_poll_interval_from_config():
    """Test that watchdog uses custom poll interval from config."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"
    config.watchdog_poll_interval_seconds = 30

    watchdog = Watchdog(config)

    assert watchdog._poll_interval == 30


def test_watchdog_custom_poll_interval_override():
    """Test that constructor poll_interval overrides config."""
    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"
    config.watchdog_poll_interval_seconds = 30

    # Override with constructor
    watchdog = Watchdog(config, poll_interval=5)

    assert watchdog._poll_interval == 5


@pytest.mark.asyncio
async def test_watchdog_custom_continue_prompt():
    """Test that watchdog uses custom continue prompt from config."""
    import httpx

    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"
    config.watchdog_continue_prompt = "keep-alive"

    captured_payload = {}

    async def mock_post(url, json=None):
        captured_payload.update(json or {})
        return httpx.Response(200, json={"status": "ok"})

    watchdog = Watchdog(config, poll_interval=1)
    watchdog._http_client = httpx.AsyncClient(timeout=1.0)
    watchdog._http_client.post = mock_post  # type: ignore

    # Manually trigger ping
    watchdog._last_activity_time = 0

    await watchdog._send_continue_ping()

    assert captured_payload.get("content") == "keep-alive"
    await watchdog.stop()


@pytest.mark.asyncio
async def test_watchdog_metrics_hook():
    """Test that on_continue_sent callback is invoked after successful ping."""
    import httpx

    config = RunnerConfig.create_default()
    config.watchdog_enabled = True
    config.watchdog_session_id = "test-session"

    callback_calls = []

    def on_continue_sent(count: int):
        callback_calls.append(count)

    async def mock_post(url, json=None):
        return httpx.Response(200, json={"status": "ok"})

    watchdog = Watchdog(config, poll_interval=1, on_continue_sent=on_continue_sent)
    watchdog._http_client = httpx.AsyncClient(timeout=1.0)
    watchdog._http_client.post = mock_post  # type: ignore

    watchdog._last_activity_time = 0

    await watchdog._send_continue_ping()

    assert callback_calls == [1]
    await watchdog.stop()
