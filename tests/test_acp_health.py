"""Tests for ACP health check implementation."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from execqueue.acp.health import get_acp_healthcheck, write_acp_health_status
from execqueue.health.models import HealthCheckResult


class TestAcpHealthCheck:
    """Tests for ACP health check implementation."""

    def test_acp_disabled_returns_degraded(self, monkeypatch):
        """ACP disabled should return DEGRADED, not ERROR."""

        def mock_settings():
            from execqueue.settings import Settings

            return Settings(acp_enabled=False)

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)

        result = get_acp_healthcheck()

        assert result.component == "acp"
        assert result.status == "DEGRADED"
        assert "disabled" in result.detail.lower()

    def test_acp_status_file_not_found_returns_error(self, monkeypatch, tmp_path):
        """Missing ACP status file should return ERROR."""

        def mock_settings():
            from execqueue.settings import Settings

            # For local_managed_process mode, all required fields must be set
            return Settings(
                acp_enabled=True,
                acp_auto_start=True,
                acp_endpoint_url="http://127.0.0.1:8010",
                acp_start_command="python -m acp",
            )

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)
        monkeypatch.setattr(
            "execqueue.acp.health.ACP_HEALTH_FILE", tmp_path / "nonexistent.json"
        )

        result = get_acp_healthcheck()

        assert result.status == "ERROR"
        assert "not found" in result.detail.lower()

    def test_acp_status_ok_returns_ok(self, monkeypatch, tmp_path):
        """ACP status OK should return OK."""

        health_file = tmp_path / "acp.json"
        health_data = {
            "component": "acp",
            "status": "ok",
            "detail": "ACP is running.",
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        health_file.write_text(json.dumps(health_data))

        def mock_settings():
            from execqueue.settings import Settings

            return Settings(
                acp_enabled=True,
                acp_auto_start=True,
                acp_endpoint_url="http://127.0.0.1:8010",
                acp_start_command="python -m acp",
            )

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        result = get_acp_healthcheck()

        assert result.status == "OK"
        assert result.component == "acp"

    def test_acp_status_stale_returns_error(self, monkeypatch, tmp_path):
        """Stale ACP status should return ERROR."""

        health_file = tmp_path / "acp.json"
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        health_data = {
            "component": "acp",
            "status": "ok",
            "detail": "ACP is running.",
            "last_check": old_time.isoformat(),
        }
        health_file.write_text(json.dumps(health_data))

        def mock_settings():
            from execqueue.settings import Settings

            return Settings(
                acp_enabled=True,
                acp_auto_start=True,
                acp_endpoint_url="http://127.0.0.1:8010",
                acp_start_command="python -m acp",
            )

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        result = get_acp_healthcheck()

        assert result.status == "ERROR"
        assert "stale" in result.detail.lower()

    def test_acp_invalid_json_returns_error(self, monkeypatch, tmp_path):
        """Invalid JSON in ACP status file should return ERROR."""

        health_file = tmp_path / "acp.json"
        health_file.write_text("invalid json")

        def mock_settings():
            from execqueue.settings import Settings

            return Settings(
                acp_enabled=True,
                acp_auto_start=True,
                acp_endpoint_url="http://127.0.0.1:8010",
                acp_start_command="python -m acp",
            )

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        result = get_acp_healthcheck()

        assert result.status == "ERROR"
        assert "invalid json" in result.detail.lower() or "Failed to read" in result.detail

    def test_acp_status_degraded_returns_degraded(self, monkeypatch, tmp_path):
        """ACP status degraded should return DEGRADED."""

        health_file = tmp_path / "acp.json"
        health_data = {
            "component": "acp",
            "status": "degraded",
            "detail": "ACP is degraded.",
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        health_file.write_text(json.dumps(health_data))

        def mock_settings():
            from execqueue.settings import Settings

            return Settings(
                acp_enabled=True,
                acp_auto_start=True,
                acp_endpoint_url="http://127.0.0.1:8010",
                acp_start_command="python -m acp",
            )

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        result = get_acp_healthcheck()

        assert result.status == "DEGRADED"

    def test_acp_status_error_returns_error(self, monkeypatch, tmp_path):
        """ACP status error should return ERROR."""

        health_file = tmp_path / "acp.json"
        health_data = {
            "component": "acp",
            "status": "error",
            "detail": "ACP is down.",
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        health_file.write_text(json.dumps(health_data))

        def mock_settings():
            from execqueue.settings import Settings

            return Settings(
                acp_enabled=True,
                acp_auto_start=True,
                acp_endpoint_url="http://127.0.0.1:8010",
                acp_start_command="python -m acp",
            )

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        result = get_acp_healthcheck()

        assert result.status == "ERROR"

    def test_acp_status_starting_returns_degraded(self, monkeypatch, tmp_path):
        """ACP status starting should return DEGRADED."""

        health_file = tmp_path / "acp.json"
        health_data = {
            "component": "acp",
            "status": "starting",
            "detail": "ACP is starting.",
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        health_file.write_text(json.dumps(health_data))

        def mock_settings():
            from execqueue.settings import Settings

            return Settings(
                acp_enabled=True,
                acp_auto_start=True,
                acp_endpoint_url="http://127.0.0.1:8010",
                acp_start_command="python -m acp",
            )

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        result = get_acp_healthcheck()

        assert result.status == "DEGRADED"

    def test_acp_unknown_status_returns_error(self, monkeypatch, tmp_path):
        """ACP unknown status should return ERROR."""

        health_file = tmp_path / "acp.json"
        health_data = {
            "component": "acp",
            "status": "unknown_status",
            "detail": "Unknown status.",
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        health_file.write_text(json.dumps(health_data))

        def mock_settings():
            from execqueue.settings import Settings

            return Settings(
                acp_enabled=True,
                acp_auto_start=True,
                acp_endpoint_url="http://127.0.0.1:8010",
                acp_start_command="python -m acp",
            )

        monkeypatch.setattr("execqueue.acp.health.get_settings", mock_settings)
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        result = get_acp_healthcheck()

        assert result.status == "ERROR"


class TestWriteAcpHealthStatus:
    """Tests for write_acp_health_status function."""

    def test_write_acp_health_status_creates_file(self, tmp_path, monkeypatch):
        """write_acp_health_status should create health file."""

        health_file = tmp_path / "acp.json"
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        write_acp_health_status("ok", "ACP is running.")

        assert health_file.exists()
        data = json.loads(health_file.read_text())
        assert data["status"] == "ok"
        assert data["detail"] == "ACP is running."
        assert "last_check" in data

    def test_write_acp_health_status_creates_parent_dir(self, tmp_path, monkeypatch):
        """write_acp_health_status should create parent directories."""

        health_file = tmp_path / "subdir" / "acp.json"
        monkeypatch.setattr("execqueue.acp.health.ACP_HEALTH_FILE", health_file)

        write_acp_health_status("ok", "ACP is running.")

        assert health_file.exists()


class TestAcpHealthAggregation:
    """Tests for ACP participation in health aggregation."""

    def test_acp_disabled_does_not_cause_system_error(self, monkeypatch):
        """ACP disabled (DEGRADED) should not cause system ERROR."""
        from execqueue.health.service import aggregate_system_status

        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="OK", detail="OK"),
            HealthCheckResult(component="acp", status="DEGRADED", detail="ACP disabled."),
        ]

        overall = aggregate_system_status(components)

        assert overall == "DEGRADED"  # Not ERROR

    def test_acp_error_causes_system_error(self, monkeypatch):
        """ACP ERROR should cause system ERROR."""
        from execqueue.health.service import aggregate_system_status

        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="OK", detail="OK"),
            HealthCheckResult(component="acp", status="ERROR", detail="ACP down."),
        ]

        overall = aggregate_system_status(components)

        assert overall == "ERROR"

    def test_acp_ok_with_all_ok_returns_ok(self, monkeypatch):
        """All OK including ACP should return OK."""
        from execqueue.health.service import aggregate_system_status

        components = [
            HealthCheckResult(component="api", status="OK", detail="OK"),
            HealthCheckResult(component="database", status="OK", detail="OK"),
            HealthCheckResult(component="acp", status="OK", detail="ACP running."),
        ]

        overall = aggregate_system_status(components)

        assert overall == "OK"


class TestAcpHealthIntegration:
    """Integration tests for ACP health check."""

    def test_acp_component_in_registry(self, monkeypatch):
        """ACP should be in registry."""
        from execqueue.health.registry import get_registered_healthchecks

        checks = get_registered_healthchecks()
        check_names = [check.__name__ for check in checks]

        assert "get_acp_healthcheck" in check_names

    def test_acp_format_component_name(self, monkeypatch):
        """ACP component name should be formatted correctly."""
        from execqueue.health.service import format_component_name

        formatted = format_component_name("acp")

        assert formatted == "ACP"
