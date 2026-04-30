"""Unit tests for RunnerConfig including Watchdog configuration.

These tests verify that the RunnerConfig dataclass has the correct defaults
and can be configured with custom values.
"""

from execqueue.runner.config import RunnerConfig


def test_runner_config_defaults():
    """Test that RunnerConfig has correct default values."""
    config = RunnerConfig(runner_id="test-runner")

    assert config.runner_id == "test-runner"
    assert config.poll_interval_seconds == 5
    assert config.batch_size == 1
    assert config.max_attempts == 3
    # Watchdog defaults
    assert config.watchdog_enabled is False
    assert config.watchdog_idle_seconds == 90
    assert config.watchdog_max_continues == 50
    assert config.watchdog_base_url == "http://127.0.0.1:4096"
    assert config.watchdog_session_id is None


def test_runner_config_create_default():
    """Test that create_default() creates a valid config with disabled watchdog."""
    config = RunnerConfig.create_default()

    # Runner ID should be auto-generated
    assert config.runner_id is not None
    assert len(config.runner_id) > 0

    # Watchdog should be disabled by default
    assert config.watchdog_enabled is False
    assert config.watchdog_session_id is None

    # Other defaults should be correct
    assert config.poll_interval_seconds == 5
    assert config.batch_size == 1
    assert config.max_attempts == 3
    assert config.watchdog_idle_seconds == 90
    assert config.watchdog_max_continues == 50
    assert config.watchdog_base_url == "http://127.0.0.1:4096"


def test_runner_config_explicit_watchdog():
    """Test that RunnerConfig can be configured with explicit watchdog values."""
    config = RunnerConfig(
        runner_id="test-runner",
        watchdog_enabled=True,
        watchdog_idle_seconds=60,
        watchdog_max_continues=100,
        watchdog_base_url="http://opencode.local:4096",
        watchdog_session_id="session-123",
    )

    assert config.watchdog_enabled is True
    assert config.watchdog_idle_seconds == 60
    assert config.watchdog_max_continues == 100
    assert config.watchdog_base_url == "http://opencode.local:4096"
    assert config.watchdog_session_id == "session-123"


def test_runner_config_backward_compatibility():
    """Test that existing RunnerConfig usage remains compatible."""
    # Old-style instantiation without watchdog fields should still work
    config = RunnerConfig(
        runner_id="old-style",
        poll_interval_seconds=10,
        batch_size=5,
        max_attempts=5,
    )

    assert config.runner_id == "old-style"
    assert config.poll_interval_seconds == 10
    assert config.batch_size == 5
    assert config.max_attempts == 5
    # Watchdog should use defaults
    assert config.watchdog_enabled is False
    assert config.watchdog_session_id is None


def test_runner_config_minimal():
    """Test that RunnerConfig can be created with only runner_id."""
    config = RunnerConfig(runner_id="minimal")

    assert config.runner_id == "minimal"
    # All other fields should have defaults
    assert config.poll_interval_seconds == 5
    assert config.batch_size == 1
    assert config.max_attempts == 3
    assert config.watchdog_enabled is False
    assert config.watchdog_idle_seconds == 90
    assert config.watchdog_max_continues == 50
    assert config.watchdog_base_url == "http://127.0.0.1:4096"
    assert config.watchdog_session_id is None
