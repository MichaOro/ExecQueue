"""Tests for ACP reachability probe."""

from unittest.mock import patch

import httpx
import pytest

from execqueue.acp.health import ProbeResult, probe_acp_endpoint
from execqueue.settings import AcpOperatingMode, Settings


class TestProbeResult:
    """Tests for ProbeResult dataclass."""

    def test_probe_result_ok(self):
        """Test successful probe result."""
        result = ProbeResult(
            reachable=True,
            status="ok",
            latency_ms=123.45,
            message="ACP endpoint reachable.",
        )
        assert result.reachable is True
        assert result.status == "ok"
        assert result.latency_ms == 123.45
        assert result.message == "ACP endpoint reachable."

    def test_probe_result_timeout(self):
        """Test timeout probe result."""
        result = ProbeResult(
            reachable=False,
            status="timeout",
            message="ACP endpoint probe timed out.",
        )
        assert result.reachable is False
        assert result.status == "timeout"


class TestProbeAcpEndpoint:
    """Tests for probe_acp_endpoint function."""

    def test_probe_skipped_when_disabled(self):
        """Test that probe is skipped when ACP is disabled."""
        settings = Settings(acp_enabled=False)

        with patch("execqueue.acp.health.get_settings", return_value=settings):
            result = probe_acp_endpoint()

        assert result.reachable is False
        assert result.status == "skipped"
        assert "disabled" in result.message.lower()

    def test_probe_invalid_url_when_no_endpoint(self):
        """Test that probe returns invalid_url when no endpoint is configured."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url=None,
        )

        with patch("execqueue.acp.health.get_settings", return_value=settings):
            result = probe_acp_endpoint()

        assert result.reachable is False
        assert result.status == "invalid_url"
        assert "not configured" in result.message.lower()

    def test_probe_success_when_endpoint_reachable(self):
        """Test successful probe when endpoint is reachable."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url="http://127.0.0.1:8010",
        )

        mock_response = httpx.Response(
            status_code=200,
            content=b'{"status": "ok"}',
        )

        with (
            patch("execqueue.acp.health.get_settings", return_value=settings),
            patch("httpx.Client.get", return_value=mock_response),
        ):
            result = probe_acp_endpoint()

        assert result.reachable is True
        assert result.status == "ok"
        assert result.latency_ms is not None
        assert "reachable" in result.message.lower()

    def test_probe_handles_timeout(self):
        """Test that timeout is handled correctly."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url="http://127.0.0.1:8010",
        )

        with (
            patch("execqueue.acp.health.get_settings", return_value=settings),
            patch("httpx.Client.get", side_effect=httpx.TimeoutException("timeout")),
        ):
            result = probe_acp_endpoint()

        assert result.reachable is False
        assert result.status == "timeout"
        assert "timed out" in result.message.lower()

    def test_probe_handles_connect_error(self):
        """Test that connection error is handled correctly."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url="http://127.0.0.1:8010",
        )

        with (
            patch("execqueue.acp.health.get_settings", return_value=settings),
            patch("httpx.Client.get", side_effect=httpx.ConnectError("connection refused")),
        ):
            result = probe_acp_endpoint()

        assert result.reachable is False
        assert result.status == "http_error"
        assert "not reachable" in result.message.lower()

    def test_probe_handles_http_error(self):
        """Test that HTTP error is handled correctly."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url="http://127.0.0.1:8010",
        )

        mock_response = httpx.Response(
            status_code=503,
            content=b'{"error": "service unavailable"}',
        )

        with (
            patch("execqueue.acp.health.get_settings", return_value=settings),
            patch("httpx.Client.get", return_value=mock_response),
        ):
            result = probe_acp_endpoint()

        assert result.reachable is False
        assert result.status == "http_error"
        assert "503" in result.message

    def test_probe_builds_health_url_correctly(self):
        """Test that /health is appended to endpoint URL if not present."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url="http://127.0.0.1:8010",
        )

        mock_response = httpx.Response(status_code=200, content=b"{}")

        with patch("httpx.Client.get", return_value=mock_response) as mock_get:
            with patch("execqueue.acp.health.get_settings", return_value=settings):
                probe_acp_endpoint()

            # Verify /health was appended
            call_url = mock_get.call_args[0][0]
            assert call_url == "http://127.0.0.1:8010/health"

    def test_probe_does_not_duplicate_health_suffix(self):
        """Test that /health is not duplicated if already present."""
        settings = Settings(
            acp_enabled=True,
            acp_auto_start=False,
            acp_endpoint_url="http://127.0.0.1:8010/health",
        )

        mock_response = httpx.Response(status_code=200, content=b"{}")

        with patch("httpx.Client.get", return_value=mock_response) as mock_get:
            with patch("execqueue.acp.health.get_settings", return_value=settings):
                probe_acp_endpoint()

            # Verify /health was not duplicated
            call_url = mock_get.call_args[0][0]
            assert call_url == "http://127.0.0.1:8010/health"
            assert call_url.count("/health") == 1
