"""Tests for health aggregation logic."""

import pytest

from execqueue.health.models import HealthCheckResult, HealthStatus
from execqueue.health.service import (
    aggregate_system_status,
    format_component_name,
    format_status_label,
    get_overall_health,
    normalize_health_component,
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

    def test_unknown_status_in_raw_component_is_treated_as_error(self):
        assert aggregate_system_status([{"component": "api", "status": "UNKNOWN"}]) == "ERROR"

    def test_missing_status_in_raw_component_is_treated_as_degraded(self):
        assert aggregate_system_status([{"component": "api", "detail": "missing"}]) == "DEGRADED"

    def test_partial_component_data_is_treated_as_degraded(self):
        assert aggregate_system_status([{"component": "api", "status": "OK"}]) == "DEGRADED"

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


class TestFormattingHelpers:
    def test_format_component_name_uses_aliases(self):
        assert format_component_name("api") == "API"
        assert format_component_name("telegram_bot") == "Telegram Bot"

    def test_format_status_label_is_user_friendly(self):
        assert format_status_label("OK") == "OK"
        assert format_status_label("DEGRADED") == "Degraded"
        assert format_status_label("ERROR") == "Error"


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

        assert "🟢 API — OK" in report
        assert "🟡 Database — Degraded" in report

    def test_report_contains_separator(self):
        components = [HealthCheckResult(component="api", status="OK", detail="OK")]
        report = render_health_report(components)

        assert "━━━━━━━━━━━━━━━━━━━━" in report

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
        assert "━━━━━━━━━━━━━━━━━━━━" in report

    def test_partial_component_report_shows_degraded_system(self):
        report = render_health_report([{"component": "api", "status": "OK"}])

        assert report.startswith("🟡 *System Health*")
        assert "🟡 API — Degraded" in report


class TestNormalizeHealthComponent:
    def test_missing_status_normalizes_to_degraded(self):
        result = normalize_health_component({"component": "api"}, fallback_name="api")

        assert result.status == HealthStatus.DEGRADED
        assert result.detail == "Component health data is incomplete: missing status."


class TestOverallHealth:
    def test_timeout_is_treated_as_error(self, monkeypatch):
        def slow_check():
            raise TimeoutError("Too slow")

        monkeypatch.setattr(
            "execqueue.health.service.get_registered_healthchecks",
            lambda: [slow_check],
        )

        summary = get_overall_health()

        assert summary.status == "ERROR"
        assert summary.checks["slow_check"].status == "ERROR"
        assert summary.checks["slow_check"].detail == "Health check timed out."

    def test_unexpected_exception_is_sanitized(self, monkeypatch):
        def broken_check():
            raise RuntimeError("secret connection string")

        monkeypatch.setattr(
            "execqueue.health.service.get_registered_healthchecks",
            lambda: [broken_check],
        )

        summary = get_overall_health()

        assert summary.status == "ERROR"
        assert summary.checks["broken_check"].detail == "Health check failed."

    def test_partial_data_is_treated_as_degraded(self, monkeypatch):
        def partial_check():
            return {"component": "api", "status": "OK"}

        monkeypatch.setattr(
            "execqueue.health.service.get_registered_healthchecks",
            lambda: [partial_check],
        )

        summary = get_overall_health()

        assert summary.status == "DEGRADED"
        assert summary.checks["api"].status == "DEGRADED"
        assert summary.checks["api"].detail == "Component health data is incomplete."
