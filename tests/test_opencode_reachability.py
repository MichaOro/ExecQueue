"""Tests for OpenCode endpoint reachability."""

from unittest.mock import patch

import httpx
import pytest

from execqueue.opencode.health import OpenCodeReachability, get_opencode_healthcheck, probe_opencode_endpoint
from execqueue.settings import OpenCodeOperatingMode, Settings


def test_probe_returns_disabled_without_http_call():
    settings = Settings(opencode_mode=OpenCodeOperatingMode.DISABLED)

    with patch("httpx.Client.get") as mock_get:
        result = probe_opencode_endpoint(settings=settings)

    assert result.state == "disabled"
    assert result.reachable is False
    mock_get.assert_not_called()


def test_probe_reports_available_for_2xx_response():
    settings = Settings(
        opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
        opencode_base_url="http://127.0.0.1:4096",
    )

    with patch("httpx.Client.get", return_value=httpx.Response(status_code=200)):
        result = probe_opencode_endpoint(settings=settings)

    assert result.state == "available"
    assert result.reachable is True
    assert result.http_status == 200


def test_probe_reports_unexpected_response_for_4xx():
    settings = Settings(
        opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
        opencode_base_url="http://127.0.0.1:4096",
    )

    with patch("httpx.Client.get", return_value=httpx.Response(status_code=404)):
        result = probe_opencode_endpoint(settings=settings)

    assert result.state == "unexpected_response"
    assert result.reachable is False
    assert result.http_status == 404


def test_probe_reports_unexpected_response_for_5xx():
    settings = Settings(
        opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
        opencode_base_url="http://127.0.0.1:4096",
    )

    with patch("httpx.Client.get", return_value=httpx.Response(status_code=500)):
        result = probe_opencode_endpoint(settings=settings)

    assert result.state == "unexpected_response"
    assert result.reachable is False
    assert result.http_status == 500


def test_probe_reports_unreachable_for_connection_error():
    settings = Settings(
        opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
        opencode_base_url="http://127.0.0.1:4096",
    )

    with patch("httpx.Client.get", side_effect=httpx.ConnectError("connection refused")):
        result = probe_opencode_endpoint(settings=settings)

    assert result.state == "unreachable"
    assert result.reachable is False


def test_probe_reports_timeout_for_timeout_error():
    settings = Settings(
        opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
        opencode_base_url="http://127.0.0.1:4096",
        opencode_timeout_ms=750,
    )

    with patch("httpx.Client.get", side_effect=httpx.TimeoutException("timeout")):
        result = probe_opencode_endpoint(settings=settings)

    assert result.state == "timeout"
    assert "750ms" in result.detail


def test_probe_reports_invalid_config_for_invalid_url():
    settings = Settings(
        opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
        opencode_base_url="http://127.0.0.1:4096",
    )

    with patch("httpx.Client.get", side_effect=httpx.InvalidURL("malformed URL")):
        result = probe_opencode_endpoint(settings=settings)

    assert result.state == "invalid_config"
    assert result.reachable is False
    assert "invalid" in result.detail.lower()


def test_probe_appends_health_path():
    settings = Settings(
        opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
        opencode_base_url="http://127.0.0.1:4096",
    )

    with patch("httpx.Client.get", return_value=httpx.Response(status_code=200)) as mock_get:
        probe_opencode_endpoint(settings=settings)

    assert mock_get.call_args[0][0] == "http://127.0.0.1:4096/health"


def test_probe_result_dataclass():
    result = OpenCodeReachability(
        state="available",
        reachable=True,
        detail="OpenCode endpoint is available.",
        latency_ms=12.5,
        http_status=200,
    )

    assert result.state == "available"
    assert result.http_status == 200


class TestHealthcheckStatusMapping:
    """Tests for health status mapping from OpenCode reachability states."""

    def test_healthcheck_maps_disabled_to_degraded(self):
        result = get_opencode_healthcheck(
            settings=Settings(opencode_mode=OpenCodeOperatingMode.DISABLED)
        )

        assert result.component == "opencode"
        assert result.status == "DEGRADED"
        assert result.state == "disabled"

    def test_healthcheck_maps_unreachable_to_degraded(self):
        settings = Settings(
            opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
            opencode_base_url="http://127.0.0.1:4096",
        )

        with patch("httpx.Client.get", side_effect=httpx.ConnectError("connection refused")):
            result = get_opencode_healthcheck(settings=settings)

        assert result.status == "DEGRADED"
        assert result.state == "unreachable"

    def test_healthcheck_maps_available_to_ok(self):
        settings = Settings(
            opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
            opencode_base_url="http://127.0.0.1:4096",
        )

        with patch("httpx.Client.get", return_value=httpx.Response(status_code=200)):
            result = get_opencode_healthcheck(settings=settings)

        assert result.status == "OK"
        assert result.state == "available"

    def test_healthcheck_maps_timeout_to_degraded(self):
        settings = Settings(
            opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
            opencode_base_url="http://127.0.0.1:4096",
            opencode_timeout_ms=750,
        )

        with patch("httpx.Client.get", side_effect=httpx.TimeoutException("timeout")):
            result = get_opencode_healthcheck(settings=settings)

        assert result.status == "DEGRADED"
        assert result.state == "timeout"

    def test_healthcheck_maps_unexpected_response_to_degraded(self):
        settings = Settings(
            opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
            opencode_base_url="http://127.0.0.1:4096",
        )

        with patch("httpx.Client.get", return_value=httpx.Response(status_code=500)):
            result = get_opencode_healthcheck(settings=settings)

        assert result.status == "DEGRADED"
        assert result.state == "unexpected_response"

    def test_healthcheck_maps_invalid_config_to_degraded(self):
        settings = Settings(
            opencode_mode=OpenCodeOperatingMode.EXTERNAL_ENDPOINT,
            opencode_base_url="http://127.0.0.1:4096",
        )

        with patch("httpx.Client.get", side_effect=httpx.InvalidURL("malformed")):
            result = get_opencode_healthcheck(settings=settings)

        assert result.status == "DEGRADED"
        assert result.state == "invalid_config"
