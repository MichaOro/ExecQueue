"""Tests for ACP lifecycle operations."""

from unittest.mock import patch

import pytest

from execqueue.acp.lifecycle import LifecycleResult, restart_acp
from execqueue.acp.health import ProbeResult
from execqueue.settings import Settings


class TestLifecycleResult:
    """Tests for LifecycleResult dataclass."""

    def test_lifecycle_result_success(self):
        """Test successful lifecycle result."""
        result = LifecycleResult(
            status="success",
            operation="restart",
            message="ACP restart initiated successfully.",
        )
        assert result.status == "success"
        assert result.operation == "restart"
        assert result.message == "ACP restart initiated successfully."

    def test_lifecycle_result_with_details(self):
        """Test lifecycle result with details."""
        result = LifecycleResult(
            status="external_managed",
            operation="restart",
            message="ACP is externally managed.",
            details={"endpoint_status": "reachable"},
        )
        assert result.details == {"endpoint_status": "reachable"}


class TestRestartAcp:
    """Tests for restart_acp function."""

    def test_restart_disabled_returns_disabled_status(self):
        """Test that restart returns disabled status when ACP is disabled."""
        settings = Settings(acp_enabled=False)

        with patch("execqueue.acp.lifecycle.get_settings", return_value=settings):
            result = restart_acp()

        assert result.status == "disabled"
        assert result.operation == "restart"
        assert "disabled" in result.message.lower()

    def test_restart_external_managed_returns_external_managed_status(self):
        """Test that restart returns external_managed for external endpoint."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url="http://127.0.0.1:8010",
        )

        mock_probe = ProbeResult(
            reachable=True,
            status="ok",
            latency_ms=100.0,
            message="ACP endpoint reachable.",
        )

        with (
            patch("execqueue.acp.lifecycle.get_settings", return_value=settings),
            patch("execqueue.acp.lifecycle.probe_acp_endpoint", return_value=mock_probe),
        ):
            result = restart_acp()

        assert result.status == "external_managed"
        assert "externally managed" in result.message.lower()

    def test_restart_external_unreachable_returns_external_managed_with_error(self):
        """Test that restart handles unreachable external endpoint."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url="http://127.0.0.1:8010",
        )

        mock_probe = ProbeResult(
            reachable=False,
            status="timeout",
            message="ACP endpoint probe timed out.",
        )

        with (
            patch("execqueue.acp.lifecycle.get_settings", return_value=settings),
            patch("execqueue.acp.lifecycle.probe_acp_endpoint", return_value=mock_probe),
        ):
            result = restart_acp()

        assert result.status == "external_managed"
        assert "externally managed" in result.message.lower()

    def test_restart_invalid_config_returns_invalid_config_status(self):
        """Test that restart returns invalid_config for invalid settings."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=True,
            acp_endpoint_url="http://127.0.0.1:8010",
            acp_start_command=None,  # Missing start command
        )

        with patch("execqueue.acp.lifecycle.get_settings", return_value=settings):
            result = restart_acp()

        assert result.status == "invalid_config"
        assert "invalid" in result.message.lower()

    def test_restart_local_managed_executes_script(self):
        """Test that restart executes script for local managed process."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=True,
            acp_endpoint_url="http://127.0.0.1:8010",
            acp_start_command="python -m acp",
        )

        with (
            patch("execqueue.acp.lifecycle.get_settings", return_value=settings),
            patch("pathlib.Path.exists", return_value=True),
            patch("execqueue.acp.lifecycle.subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stderr = ""
            mock_run.return_value.stdout = ""

            result = restart_acp()

        assert result.status == "success"
        assert "initiated successfully" in result.message.lower()
        mock_run.assert_called_once()

    def test_restart_local_managed_handles_script_failure(self):
        """Test that restart handles script failure."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=True,
            acp_endpoint_url="http://127.0.0.1:8010",
            acp_start_command="python -m acp",
        )

        with (
            patch("execqueue.acp.lifecycle.get_settings", return_value=settings),
            patch("pathlib.Path.exists", return_value=True),
            patch("execqueue.acp.lifecycle.subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Script failed"
            mock_run.return_value.stdout = ""

            result = restart_acp()

        assert result.status == "failed"
        assert "failed" in result.message.lower()

    def test_restart_local_managed_handles_script_not_found(self):
        """Test that restart handles missing script."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=True,
            acp_endpoint_url="http://127.0.0.1:8010",
            acp_start_command="python -m acp",
        )

        with (
            patch("execqueue.acp.lifecycle.get_settings", return_value=settings),
            patch("pathlib.Path.exists", return_value=False),
        ):
            result = restart_acp()

        assert result.status == "failed"
        assert "script not found" in result.message.lower()

    def test_restart_local_managed_handles_timeout(self):
        """Test that restart handles subprocess timeout."""
        import subprocess

        settings = Settings(
            acp_enabled=True,
            acp_auto_start=True,
            acp_endpoint_url="http://127.0.0.1:8010",
            acp_start_command="python -m acp",
        )

        with (
            patch("execqueue.acp.lifecycle.get_settings", return_value=settings),
            patch("pathlib.Path.exists", return_value=True),
            patch("execqueue.acp.lifecycle.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)

            result = restart_acp()

        assert result.status == "failed"
        assert "timed out" in result.message.lower()
