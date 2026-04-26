"""Tests for health aggregation logic."""

import pytest

from execqueue.health.models import HealthCheckResult
from execqueue.health.service import (
    aggregate_system_status,
    render_health_report,
    status_to_emoji,
)


class TestAggregateSystemStatus:
    """Tests for the aggregate_system_status function."""

    def test_all_ok_returns_ok(self):
        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="OK", detail="OK"),
            HealthCheckResult(component="telegram_bot", status="OK", detail="OK"),
        ]
        assert aggregate_system_status(components) == "OK"

    def test_one_degraded_returns_degraded(self):
        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="DEGRADED", detail="Slow"),
            HealthCheckResult(component="telegram_bot", status="OK", detail="OK"),
        ]
        assert aggregate_system_status(components) == "DEGRADED"

    def test_one_error_returns_error(self):
        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="ERROR", detail="Down"),
            HealthCheckResult(component="telegram_bot", status="OK", detail="OK"),
        ]
        assert aggregate_system_status(components) == "ERROR"

    def test_multiple_errors_returns_error(self):
        components = [
            HealthCheckResult(component="api", status="ERROR", detail="Down"),
            HealthCheckResult(component="database", status="ERROR", detail="Down"),
            HealthCheckResult(component="telegram_bot", status="DEGRADED", detail="Slow"),
        ]
        assert aggregate_system_status(components) == "ERROR"

    def test_error_takes_priority_over_degraded(self):
        components = [
            HealthCheckResult(component="api", status="DEGRADED", detail="Slow"),
            HealthCheckResult(component="database", status="ERROR", detail="Down"),
            HealthCheckResult(component="telegram_bot", status="DEGRADED", detail="Slow"),
        ]
        assert aggregate_system_status(components) == "ERROR"

    def test_no_components_returns_error_fail_safe(self):
        assert aggregate_system_status([]) == "ERROR"

    def test_invalid_status_rejected_by_model(self):
        with pytest.raises(Exception):
            HealthCheckResult(component="api", status="UNKNOWN", detail="Unknown")

    def test_single_ok_component(self):
        components = [HealthCheckResult(component="api", status="OK", detail="OK")]
        assert aggregate_system_status(components) == "OK"

    def test_single_error_component(self):
        components = [HealthCheckResult(component="api", status="ERROR", detail="Down")]
        assert aggregate_system_status(components) == "ERROR"

    def test_single_degraded_component(self):
        components = [HealthCheckResult(component="api", status="DEGRADED", detail="Slow")]
        assert aggregate_system_status(components) == "DEGRADED"


class TestStatusToEmoji:
    """Tests for the status_to_emoji function."""

    def test_ok_maps_to_green(self):
        assert status_to_emoji("OK") == "🟢"

    def test_degraded_maps_to_yellow(self):
        assert status_to_emoji("DEGRADED") == "🟡"

    def test_error_maps_to_red(self):
        assert status_to_emoji("ERROR") == "🔴"

    def test_unknown_maps_to_red(self):
        assert status_to_emoji("UNKNOWN") == "🔴"


class TestRenderHealthReport:
    """Tests for the render_health_report function."""

    def test_report_contains_system_header(self):
        components = [HealthCheckResult(component="api", status="OK", detail="OK")]
        report = render_health_report(components)

        assert "🟢" in report
        assert "*System Health*" in report

    def test_report_contains_component_lines(self):
        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="DEGRADED", detail="Slow"),
        ]
        report = render_health_report(components)

        assert "🟢 api" in report
        assert "🟡 database" in report

    def test_report_contains_legend(self):
        components = [HealthCheckResult(component="api", status="OK", detail="OK")]
        report = render_health_report(components)

        assert "🔴 = mindestens ein Service DOWN / ERROR" in report
        assert "🟡 = kein Fehler, aber mindestens ein Service DEGRADED" in report
        assert "🟢 = alle Services OK" in report

    def test_report_format_with_error(self):
        components = [HealthCheckResult(component="api", status="ERROR", detail="Down")]
        report = render_health_report(components)

        assert report.startswith("🔴 *System Health*")

    def test_report_format_with_degraded(self):
        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="DEGRADED", detail="Slow"),
        ]
        report = render_health_report(components)

        assert report.startswith("🟡 *System Health*")

    def test_report_format_with_all_ok(self):
        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="OK", detail="OK"),
        ]
        report = render_health_report(components)

        assert report.startswith("🟢 *System Health*")

    def test_empty_components_report(self):
        report = render_health_report([])

        assert "🔴 *System Health*" in report
        assert "━━━━━━━━━━━━━━━━━━━" in report
