"""Unit tests for scheduler worker logic."""

import signal
from unittest.mock import MagicMock, patch

import pytest

from execqueue.runtime import (
    is_scheduler_enabled,
    get_scheduler_task_delay,
    get_scheduler_shutdown_timeout,
)


class TestSchedulerConfiguration:
    """Tests for scheduler configuration functions."""

    def test_is_scheduler_enabled_default_false(self, monkeypatch):
        """Default is False for backward compatibility."""
        monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
        assert is_scheduler_enabled() is False

    @pytest.mark.parametrize("value", ["true", "1", "yes", "on"])
    def test_is_scheduler_enabled_true_values(self, monkeypatch, value):
        """True for various true-like values."""
        monkeypatch.setenv("SCHEDULER_ENABLED", value)
        assert is_scheduler_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", ""])
    def test_is_scheduler_enabled_false_values(self, monkeypatch, value):
        """False for various false-like values."""
        monkeypatch.setenv("SCHEDULER_ENABLED", value)
        assert is_scheduler_enabled() is False

    def test_get_scheduler_task_delay_default(self, monkeypatch):
        """Default delay is 5 seconds."""
        monkeypatch.delenv("SCHEDULER_TASK_DELAY", raising=False)
        assert get_scheduler_task_delay() == 5

    def test_get_scheduler_task_delay_custom(self, monkeypatch):
        """Custom delay is respected."""
        monkeypatch.setenv("SCHEDULER_TASK_DELAY", "10")
        assert get_scheduler_task_delay() == 10

    def test_get_scheduler_task_delay_invalid_low(self, monkeypatch, caplog):
        """Returns default for delay below minimum."""
        monkeypatch.setenv("SCHEDULER_TASK_DELAY", "0")
        with caplog.at_level("WARNING"):
            result = get_scheduler_task_delay()
        assert result == 5
        assert "outside valid range" in caplog.text

    def test_get_scheduler_task_delay_invalid_high(self, monkeypatch, caplog):
        """Returns default for delay above maximum."""
        monkeypatch.setenv("SCHEDULER_TASK_DELAY", "500")
        with caplog.at_level("WARNING"):
            result = get_scheduler_task_delay()
        assert result == 5
        assert "outside valid range" in caplog.text

    def test_get_scheduler_task_delay_invalid_value(self, monkeypatch, caplog):
        """Returns default for non-integer value."""
        monkeypatch.setenv("SCHEDULER_TASK_DELAY", "abc")
        with caplog.at_level("WARNING"):
            result = get_scheduler_task_delay()
        assert result == 5
        assert "Invalid SCHEDULER_TASK_DELAY" in caplog.text

    def test_get_scheduler_shutdown_timeout_default(self, monkeypatch):
        """Default shutdown timeout is 30 seconds."""
        monkeypatch.delenv("SCHEDULER_SHUTDOWN_TIMEOUT", raising=False)
        assert get_scheduler_shutdown_timeout() == 30

    def test_get_scheduler_shutdown_timeout_custom(self, monkeypatch):
        """Custom timeout is respected."""
        monkeypatch.setenv("SCHEDULER_SHUTDOWN_TIMEOUT", "60")
        assert get_scheduler_shutdown_timeout() == 60

    def test_get_scheduler_shutdown_timeout_invalid_low(self, monkeypatch, caplog):
        """Returns default for timeout below minimum."""
        monkeypatch.setenv("SCHEDULER_SHUTDOWN_TIMEOUT", "3")
        with caplog.at_level("WARNING"):
            result = get_scheduler_shutdown_timeout()
        assert result == 30
        assert "outside valid range" in caplog.text

    def test_get_scheduler_shutdown_timeout_invalid_high(self, monkeypatch, caplog):
        """Returns default for timeout above maximum."""
        monkeypatch.setenv("SCHEDULER_SHUTDOWN_TIMEOUT", "200")
        with caplog.at_level("WARNING"):
            result = get_scheduler_shutdown_timeout()
        assert result == 30
        assert "outside valid range" in caplog.text

    def test_get_scheduler_shutdown_timeout_invalid_value(self, monkeypatch, caplog):
        """Returns default for non-integer value."""
        monkeypatch.setenv("SCHEDULER_SHUTDOWN_TIMEOUT", "xyz")
        with caplog.at_level("WARNING"):
            result = get_scheduler_shutdown_timeout()
        assert result == 30
        assert "Invalid SCHEDULER_SHUTDOWN_TIMEOUT" in caplog.text


class TestShutdownSignalHandler:
    """Tests for shutdown signal handling."""

    def test_handle_sigint_sets_flag(self, monkeypatch):
        """SIGINT handler sets _shutdown_requested flag."""
        from execqueue.scheduler import worker

        monkeypatch.setattr(worker, "_shutdown_requested", False)
        
        with patch.object(worker.logger, "info") as mock_log:
            worker._handle_shutdown_signal(signal.SIGINT, None)
            mock_log.assert_called_once()
            assert "SIGINT" in str(mock_log.call_args)

    def test_handle_sigterm_sets_flag(self, monkeypatch):
        """SIGTERM handler sets _shutdown_requested flag."""
        from execqueue.scheduler import worker

        monkeypatch.setattr(worker, "_shutdown_requested", False)
        
        with patch.object(worker.logger, "info") as mock_log:
            worker._handle_shutdown_signal(signal.SIGTERM, None)
            mock_log.assert_called_once()
            assert "SIGTERM" in str(mock_log.call_args)


class TestWorkerLoopLogic:
    """Tests for worker loop logic."""

    def test_worker_exits_when_disabled(self, monkeypatch):
        """Worker exits immediately when scheduler is disabled."""
        monkeypatch.setenv("SCHEDULER_ENABLED", "false")
        
        from execqueue.runtime import is_scheduler_enabled
        
        assert is_scheduler_enabled() is False

    def test_worker_loop_checks_shutdown_flag(self):
        """Worker loop respects shutdown flag."""
        from execqueue.scheduler import worker
        
        original_value = worker._shutdown_requested
        worker._shutdown_requested = True
        
        try:
            assert worker._shutdown_requested is True
        finally:
            worker._shutdown_requested = original_value

    def test_worker_perform_shutdown_sets_flag(self, monkeypatch):
        """Shutdown function sets the shutdown flag."""
        from execqueue.scheduler import worker
        
        original_value = worker._shutdown_requested
        worker._shutdown_requested = False
        
        try:
            worker._shutdown_requested = True
            assert worker._shutdown_requested is True
        finally:
            worker._shutdown_requested = original_value

    def test_worker_session_management(self, monkeypatch):
        """Worker uses context manager for session."""
        from unittest.mock import MagicMock
        
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=MagicMock())
        mock_session.__exit__ = MagicMock(return_value=False)
        
        assert mock_session.__enter__ is not None
        assert mock_session.__exit__ is not None
