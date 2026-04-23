import pytest
from unittest.mock import patch

from execqueue.scheduler.runner import _calculate_backoff_delay


class TestBackoffCalculation:
    """Tests for exponential backoff calculation."""

    def test_first_retry_min_delay(self, monkeypatch):
        """Test: First retry uses minimum delay."""
        monkeypatch.setenv("SCHEDULER_BACKOFF_MIN_DELAY", "10")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MULTIPLIER", "2.0")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MAX_DELAY", "300")
        
        delay = _calculate_backoff_delay(0)
        assert delay == 10.0

    def test_exponential_growth(self, monkeypatch):
        """Test: Backoff delay grows exponentially."""
        monkeypatch.setenv("SCHEDULER_BACKOFF_MIN_DELAY", "10")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MULTIPLIER", "2.0")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MAX_DELAY", "300")
        
        delay_0 = _calculate_backoff_delay(0)
        delay_1 = _calculate_backoff_delay(1)
        delay_2 = _calculate_backoff_delay(2)
        delay_3 = _calculate_backoff_delay(3)
        
        assert delay_0 == 10.0
        assert delay_1 == 20.0
        assert delay_2 == 40.0
        assert delay_3 == 80.0

    def test_max_delay_cap(self, monkeypatch):
        """Test: Backoff delay is capped at maximum."""
        monkeypatch.setenv("SCHEDULER_BACKOFF_MIN_DELAY", "10")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MULTIPLIER", "2.0")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MAX_DELAY", "60")
        
        delay_0 = _calculate_backoff_delay(0)
        delay_1 = _calculate_backoff_delay(1)
        delay_2 = _calculate_backoff_delay(2)
        delay_3 = _calculate_backoff_delay(3)
        delay_10 = _calculate_backoff_delay(10)
        
        assert delay_0 == 10.0
        assert delay_1 == 20.0
        assert delay_2 == 40.0
        assert delay_3 == 60.0  # Capped at max
        assert delay_10 == 60.0  # Stays at max

    def test_custom_multiplier(self, monkeypatch):
        """Test: Custom multiplier is respected."""
        monkeypatch.setenv("SCHEDULER_BACKOFF_MIN_DELAY", "10")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MULTIPLIER", "1.5")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MAX_DELAY", "300")
        
        delay_0 = _calculate_backoff_delay(0)
        delay_1 = _calculate_backoff_delay(1)
        delay_2 = _calculate_backoff_delay(2)
        
        assert delay_0 == 10.0
        assert delay_1 == 15.0
        assert delay_2 == 22.5

    def test_high_retry_count(self, monkeypatch):
        """Test: High retry count stays at max."""
        monkeypatch.setenv("SCHEDULER_BACKOFF_MIN_DELAY", "10")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MULTIPLIER", "2.0")
        monkeypatch.setenv("SCHEDULER_BACKOFF_MAX_DELAY", "300")
        
        delay = _calculate_backoff_delay(20)
        assert delay == 300.0
