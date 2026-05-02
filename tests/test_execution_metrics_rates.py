"""Tests for ExecutionMetrics rate properties."""

from __future__ import annotations

import pytest

from execqueue.observability import ExecutionMetrics, reset_metrics


class TestExecutionMetricsRates:
    """Tests for ExecutionMetrics rate properties."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_metrics()

    def test_cherry_pick_success_rate_property(self):
        """Test cherry-pick success rate property."""
        metrics = ExecutionMetrics()
        metrics.cherry_pick_success = 3
        metrics.cherry_pick_attempts = 5
        
        # Should be 3/5 = 0.6
        assert metrics.cherry_pick_success_rate == 0.6

    def test_cherry_pick_success_rate_zero_attempts(self):
        """Test cherry-pick success rate with zero attempts."""
        metrics = ExecutionMetrics()
        
        # Should be 0.0 when no attempts
        assert metrics.cherry_pick_success_rate == 0.0

    def test_cherry_pick_success_rate_no_failures(self):
        """Test cherry-pick success rate with all successes."""
        metrics = ExecutionMetrics()
        metrics.cherry_pick_success = 5
        metrics.cherry_pick_attempts = 5
        
        # Should be 5/5 = 1.0
        assert metrics.cherry_pick_success_rate == 1.0

    def test_validation_success_rate_property(self):
        """Test validation success rate property."""
        metrics = ExecutionMetrics()
        metrics.validations_passed = 4
        metrics.validations_failed = 1
        metrics.validations_review = 1
        
        # Should be 4/(4+1+1) = 4/6 = 0.666...
        assert abs(metrics.validation_success_rate - 0.6666666666666666) < 1e-10

    def test_validation_success_rate_zero_validations(self):
        """Test validation success rate with zero validations."""
        metrics = ExecutionMetrics()
        
        # Should be 0.0 when no validations
        assert metrics.validation_success_rate == 0.0

    def test_validation_success_rate_all_passed(self):
        """Test validation success rate with all passed."""
        metrics = ExecutionMetrics()
        metrics.validations_passed = 5
        metrics.validations_failed = 0
        metrics.validations_review = 0
        
        # Should be 5/5 = 1.0
        assert metrics.validation_success_rate == 1.0

    def test_rates_integration_with_existing_to_dict(self):
        """Test that rate properties match calculated values in to_dict()."""
        metrics = ExecutionMetrics()
        metrics.cherry_pick_success = 2
        metrics.cherry_pick_attempts = 4
        metrics.validations_passed = 3
        metrics.validations_failed = 1
        metrics.validations_review = 1
        
        result = metrics.to_dict()
        
        # Properties should match values in to_dict()
        assert metrics.cherry_pick_success_rate == result["cherry_pick_success_rate"]
        assert metrics.validation_success_rate == result["validation_success_rate"]
        
        # Check specific values
        assert metrics.cherry_pick_success_rate == 0.5  # 2/4
        assert abs(metrics.validation_success_rate - 0.6) < 1e-10  # 3/5