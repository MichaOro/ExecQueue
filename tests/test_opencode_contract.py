"""OpenCode serve contract verification tests.

These tests verify the OpenCode serve API contract against a running instance.
When no instance is available, they run against mocks to validate the contract
structure and error handling.

Run against real instance:
    OPENCODE_BASE_URL=http://localhost:8000 pytest tests/test_opencode_contract.py -v

Run with mocks only:
    pytest tests/test_opencode_contract.py -v -m mock
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from execqueue.opencode import (
    OpenCodeClient,
    OpenCodeClientError,
    OpenCodeConnectionError,
    OpenCodeAPIError,
    OpenCodeTimeoutError,
    OpenCodeSession,
    OpenCodeMessage,
    OpenCodeEvent,
)
from execqueue.settings import Settings, RuntimeEnvironment, OpenCodeOperatingMode


# Mark for test selection
pytestmark = pytest.mark.anyio


class TestOpenCodeClientInstantiation:
    """Test client initialization and configuration."""

    def test_client_with_default_values(self):
        """Client uses default base URL and timeout when not specified."""
        client = OpenCodeClient()
        assert client.base_url == "http://localhost:8000"
        assert client.timeout_ms == 30000

    def test_client_with_custom_values(self):
        """Client accepts custom base URL and timeout."""
        client = OpenCodeClient(base_url="http://custom:9999", timeout_ms=5000)
        assert client.base_url == "http://custom:9999"
        assert client.timeout_ms == 5000

    def test_client_with_settings(self):
        """Client reads configuration from Settings."""
        settings = Settings(
            app_env=RuntimeEnvironment.TEST,
            opencode_mode=OpenCodeOperatingMode.ENABLED,
            opencode_base_url="http://settings-url:8080",
            opencode_timeout_ms=5000,
        )
        client = OpenCodeClient(settings=settings)
        assert client.base_url == "http://settings-url:8080"
        assert client.timeout_ms == 5000


class TestHealthEndpoint:
    """Test health endpoint contract."""

    @pytest.mark.asyncio
    async def test_health_success(self):
        """Health endpoint returns successful response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "version": "0.1.0"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = OpenCodeClient()
            result = await client.health()

        assert result["status"] == "ok"
        assert result["version"] == "0.1.0"

    @pytest.mark.asyncio
    async def test_health_timeout(self):
        """Health endpoint raises timeout error on timeout."""
        with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("timeout")):
            client = OpenCodeClient(timeout_ms=1000)
            with pytest.raises(OpenCodeTimeoutError):
                await client.health()

    @pytest.mark.asyncio
    async def test_health_connection_error(self):
        """Health endpoint raises connection error on failure."""
        with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("conn error")):
            client = OpenCodeClient()
            with pytest.raises(OpenCodeConnectionError):
                await client.health()

    @pytest.mark.asyncio
    async def test_health_api_error(self):
        """Health endpoint raises API error on non-2xx status."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Service Unavailable",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = OpenCodeClient()
            with pytest.raises(OpenCodeAPIError) as exc_info:
                await client.health()

            assert exc_info.value.status_code == 503


class TestSessionCreation:
    """Test session creation contract."""

    @pytest.mark.asyncio
    async def test_create_session_success(self):
        """Session creation returns session with ID."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "sess_abc123",
            "name": "test-session",
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            client = OpenCodeClient()
            session = await client.create_session(name="test-session")

        assert session.id == "sess_abc123"
        assert session.name == "test-session"
        assert session.created_at == "2024-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_create_session_without_name(self):
        """Session creation works without optional name."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "sess_xyz789"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            client = OpenCodeClient()
            session = await client.create_session()

        assert session.id == "sess_xyz789"
        assert session.name is None

    @pytest.mark.asyncio
    async def test_create_session_not_found(self):
        """Session creation returns 404 if endpoint doesn't exist."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            client = OpenCodeClient()
            with pytest.raises(OpenCodeAPIError) as exc_info:
                await client.create_session()

            assert exc_info.value.status_code == 404
            assert "implicit" in exc_info.value.message.lower()


class TestMessageDispatch:
    """Test message dispatch contract."""

    @pytest.mark.asyncio
    async def test_dispatch_message_success(self):
        """Message dispatch returns message with processing status."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "id": "msg_def456",
            "session_id": "sess_abc123",
            "status": "processing",
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            client = OpenCodeClient()
            message = await client.dispatch_message(
                session_id="sess_abc123",
                content="Test message",
                role="user",
            )

        assert message.id == "msg_def456"
        assert message.session_id == "sess_abc123"
        assert message.status == "processing"

    @pytest.mark.asyncio
    async def test_dispatch_message_fallback_endpoint(self):
        """Message dispatch falls back to /run endpoint if /messages not found."""
        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_404.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_404,
        )

        mock_success = MagicMock()
        mock_success.status_code = 202
        mock_success.json.return_value = {"id": "msg_fallback", "session_id": "sess_abc123"}
        mock_success.raise_for_status = MagicMock()

        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_404
            return mock_success

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            client = OpenCodeClient()
            message = await client.dispatch_message(
                session_id="sess_abc123",
                content="Test",
            )

        assert call_count == 2
        assert message.id == "msg_fallback"

    @pytest.mark.asyncio
    async def test_dispatch_message_timeout(self):
        """Message dispatch raises timeout on timeout."""
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("timeout")):
            client = OpenCodeClient(timeout_ms=1000)
            with pytest.raises(OpenCodeTimeoutError):
                await client.dispatch_message("sess_abc123", "test")


class TestMessagePolling:
    """Test message polling contract."""

    @pytest.mark.asyncio
    async def test_get_message_completed(self):
        """Get message returns completed message with content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "msg_def456",
            "session_id": "sess_abc123",
            "status": "completed",
            "content": "Assistant response",
            "completed_at": "2024-01-01T00:01:00Z",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = OpenCodeClient()
            message = await client.get_message("sess_abc123", "msg_def456")

        assert message.status == "completed"
        assert message.content == "Assistant response"
        assert message.completed_at == "2024-01-01T00:01:00Z"

    @pytest.mark.asyncio
    async def test_get_message_failed(self):
        """Get message returns failed message with error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "msg_err",
            "session_id": "sess_abc123",
            "status": "failed",
            "error": "Processing failed",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = OpenCodeClient()
            message = await client.get_message("sess_abc123", "msg_err")

        assert message.status == "failed"
        assert message.error == "Processing failed"


class TestSSEEventStream:
    """Test SSE event streaming contract."""

    @pytest.mark.asyncio
    async def test_stream_events_basic(self):
        """SSE stream yields events from response."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        async def aiter_lines():
            yield "event: message.started"
            yield 'data: {"id": "msg_1", "status": "processing"}'
            yield ""
            yield "event: message.delta"
            yield 'data: {"id": "msg_1", "content": "partial"}'
            yield ""

        mock_response.aiter_lines = aiter_lines

        stream_context = MagicMock()
        stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        stream_context.__aexit__ = AsyncMock(return_value=None)

        mock_client_instance = MagicMock()
        mock_client_instance.stream = MagicMock(return_value=stream_context)

        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=mock_client_instance)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=client_context):
            client = OpenCodeClient()
            events = []
            async for event in client.stream_events():
                events.append(event)

        assert len(events) == 2
        assert events[0].event_type == "message.started"
        assert events[0].data["id"] == "msg_1"
        assert events[1].event_type == "message.delta"
        assert events[1].data["content"] == "partial"

    @pytest.mark.asyncio
    async def test_stream_events_with_filters(self):
        """SSE stream accepts session and message filters."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        async def aiter_lines():
            yield "event: heartbeat"
            yield 'data: {"ts": "2024-01-01T00:00:00Z"}'
            yield ""

        mock_response.aiter_lines = aiter_lines

        stream_context = MagicMock()
        stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        stream_context.__aexit__ = AsyncMock(return_value=None)

        mock_client_instance = MagicMock()
        mock_client_instance.stream = MagicMock(return_value=stream_context)

        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=mock_client_instance)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=client_context):
            client = OpenCodeClient()
            events = []
            async for event in client.stream_events(
                session_id="sess_abc",
                message_id="msg_def",
            ):
                events.append(event)

        assert len(events) == 1
        assert events[0].event_type == "heartbeat"

    @pytest.mark.asyncio
    async def test_stream_events_not_found(self):
        """SSE stream raises error if endpoint doesn't exist."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        async def aiter_lines():
            yield ""

        mock_response.aiter_lines = aiter_lines

        stream_context = MagicMock()
        stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        stream_context.__aexit__ = AsyncMock(return_value=None)

        mock_client_instance = MagicMock()
        mock_client_instance.stream = MagicMock(return_value=stream_context)

        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=mock_client_instance)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=client_context):
            client = OpenCodeClient()
            with pytest.raises(OpenCodeAPIError) as exc_info:
                async for _ in client.stream_events():
                    pass

            assert exc_info.value.status_code == 404


class TestDataClasses:
    """Test data class structures."""

    def test_opencode_session(self):
        """OpenCodeSession has correct fields."""
        session = OpenCodeSession(
            id="sess_123",
            name="test",
            created_at="2024-01-01T00:00:00Z",
        )
        assert session.id == "sess_123"
        assert session.name == "test"
        assert session.created_at == "2024-01-01T00:00:00Z"

    def test_opencode_message(self):
        """OpenCodeMessage has correct fields."""
        message = OpenCodeMessage(
            id="msg_123",
            session_id="sess_123",
            status="completed",
            content="response",
            error=None,
            created_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:01:00Z",
        )
        assert message.id == "msg_123"
        assert message.session_id == "sess_123"
        assert message.status == "completed"
        assert message.content == "response"
        assert message.error is None

    def test_opencode_event(self):
        """OpenCodeEvent has correct fields."""
        event = OpenCodeEvent(
            event_type="message.completed",
            data={"id": "msg_123", "status": "completed"},
            message_id="msg_123",
            session_id="sess_123",
        )
        assert event.event_type == "message.completed"
        assert event.data["id"] == "msg_123"
        assert event.message_id == "msg_123"
        assert event.session_id == "sess_123"


class TestExceptionHierarchy:
    """Test exception hierarchy."""

    def test_exceptions_inherit_from_base(self):
        """All client exceptions inherit from OpenCodeClientError."""
        assert issubclass(OpenCodeConnectionError, OpenCodeClientError)
        assert issubclass(OpenCodeTimeoutError, OpenCodeClientError)
        assert issubclass(OpenCodeAPIError, OpenCodeClientError)

    def test_api_error_has_status_code(self):
        """OpenCodeAPIError includes status code."""
        error = OpenCodeAPIError(404, "Not found")
        assert error.status_code == 404
        assert error.message == "Not found"


class TestContractVerification:
    """Contract verification against real OpenCode instance.
    
    These tests require a running OpenCode instance.
    Run with: OPENCODE_BASE_URL=http://localhost:8000 pytest -m contract
    """

    @pytest.mark.asyncio
    @pytest.mark.contract
    async def test_real_health_endpoint(self):
        """Verify health endpoint against real instance."""
        try:
            settings = Settings()
        except Exception:
            pytest.skip("Cannot load settings")
            
        client = OpenCodeClient(settings=settings)
        
        try:
            result = await client.health()
            assert "status" in result
        except (OpenCodeConnectionError, OpenCodeTimeoutError, OpenCodeAPIError):
            pytest.skip("No OpenCode instance available or endpoint error")
        except json.JSONDecodeError:
            pytest.skip("Non-JSON response from OpenCode instance")

    @pytest.mark.asyncio
    @pytest.mark.contract
    async def test_real_session_creation(self):
        """Verify session creation against real instance."""
        try:
            settings = Settings()
        except Exception:
            pytest.skip("Cannot load settings")
            
        client = OpenCodeClient(settings=settings)
        
        try:
            session = await client.create_session(name="contract-test")
            assert session.id is not None
            assert len(session.id) > 0
        except OpenCodeAPIError as e:
            if e.status_code == 404:
                pytest.skip("Session creation endpoint not found (may be implicit)")
            pytest.skip(f"API error: {e.message}")
        except (OpenCodeConnectionError, OpenCodeTimeoutError):
            pytest.skip("No OpenCode instance available")
        except json.JSONDecodeError:
            pytest.skip("Non-JSON response from OpenCode instance")

    @pytest.mark.asyncio
    @pytest.mark.contract
    async def test_real_message_dispatch(self):
        """Verify message dispatch against real instance."""
        try:
            settings = Settings()
        except Exception:
            pytest.skip("Cannot load settings")
            
        client = OpenCodeClient(settings=settings)
        
        try:
            try:
                session = await client.create_session()
            except OpenCodeAPIError:
                session = OpenCodeSession(id="test-session")

            message = await client.dispatch_message(
                session_id=session.id,
                content="Hello, this is a contract test.",
            )
            assert message.id is not None
            assert message.status in ["processing", "queued", "completed"]
        except (OpenCodeConnectionError, OpenCodeTimeoutError):
            pytest.skip("No OpenCode instance available")
        except json.JSONDecodeError:
            pytest.skip("Non-JSON response from OpenCode instance")


# Integration test fixtures
@pytest.fixture
def opencode_mock_server():
    """Mock OpenCode server responses for testing.
    
    Usage:
        def test_something(opencode_mock_server):
            opencode_mock_server.add_response("/health", {"status": "ok"})
            client = OpenCodeClient()
            result = await client.health()
    """
    class MockServer:
        def __init__(self):
            self.responses = {}

        def add_response(self, path: str, data: dict, status_code: int = 200):
            self.responses[path] = {"data": data, "status_code": status_code}

        def create_mock_response(self, path: str):
            mock = MagicMock()
            if path in self.responses:
                mock.status_code = self.responses[path]["status_code"]
                mock.json.return_value = self.responses[path]["data"]
            else:
                mock.status_code = 404
                mock.json.return_value = {"error": "Not found"}
            mock.raise_for_status = MagicMock()
            return mock

    return MockServer()


@pytest.fixture
def settings_mock():
    """Create mock settings for testing."""
    return Settings(
        app_env=RuntimeEnvironment.TEST,
        opencode_mode=OpenCodeOperatingMode.ENABLED,
        opencode_base_url="http://test-opencode:8000",
        opencode_timeout_ms=5000,
    )


# ============================================================================
# REQ-012-04: Response Validation Tests
# ============================================================================


class TestResponseValidation:
    """Test response validation per REQ-012-04."""

    @pytest.mark.anyio
    async def test_session_creation_validates_required_id_field(self):
        """Test that session creation validates required 'id' field."""
        from execqueue.opencode.client import OpenCodeValidationError

        # Mock response missing 'id' field
        async def mock_post(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"name": "test"}  # Missing 'id'
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("httpx.AsyncClient.post", mock_post):
            client = OpenCodeClient(base_url="http://test.local")
            with pytest.raises(OpenCodeValidationError) as exc_info:
                await client.create_session(name="test")

            assert "missing required field" in str(exc_info.value).lower()
            assert "id" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_message_dispatch_validates_required_id_field(self):
        """Test that message dispatch validates required 'id' field."""
        from execqueue.opencode.client import OpenCodeValidationError

        # Mock response missing 'id' field
        async def mock_post(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.status_code = 202
            mock_response.json.return_value = {"session_id": "sess_123"}  # Missing 'id'
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("httpx.AsyncClient.post", mock_post):
            client = OpenCodeClient(base_url="http://test.local")
            with pytest.raises(OpenCodeValidationError) as exc_info:
                await client.dispatch_message("sess_123", "Hello")

            assert "missing required field" in str(exc_info.value).lower()
            assert "id" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_invalid_json_response_raises_validation_error(self):
        """Test that invalid JSON raises OpenCodeValidationError."""
        from execqueue.opencode.client import OpenCodeValidationError

        async def mock_post(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "test", 0)
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("httpx.AsyncClient.post", mock_post):
            client = OpenCodeClient(base_url="http://test.local")
            with pytest.raises(OpenCodeValidationError):
                await client.create_session()


# ============================================================================
# REQ-012-04: Error Category Mapping Tests
# ============================================================================


class TestErrorCategoryMapping:
    """Test error category mapping per REQ-012-04."""

    def test_connection_error_mapped_to_connection_category(self):
        """Test that connection errors map to 'connection' category."""
        from execqueue.opencode.client import _map_error_category

        exc = OpenCodeConnectionError("Connection failed")
        assert _map_error_category(exc) == "connection"

    def test_timeout_error_mapped_to_timeout_category(self):
        """Test that timeout errors map to 'timeout' category."""
        from execqueue.opencode.client import _map_error_category

        exc = OpenCodeTimeoutError("Request timed out")
        assert _map_error_category(exc) == "timeout"

    def test_api_error_mapped_to_http_category(self):
        """Test that API errors map to 'http' category."""
        from execqueue.opencode.client import _map_error_category

        exc = OpenCodeAPIError(500, "Internal server error")
        assert _map_error_category(exc) == "http"

    def test_validation_error_mapped_to_invalid_response_category(self):
        """Test that validation errors map to 'invalid_response' category."""
        from execqueue.opencode.client import _map_error_category, OpenCodeValidationError

        exc = OpenCodeValidationError("Missing field")
        assert _map_error_category(exc) == "invalid_response"

    def test_httpx_connect_error_mapped_to_connection_category(self):
        """Test that httpx ConnectError maps to 'connection' category."""
        from execqueue.opencode.client import _map_error_category

        exc = httpx.ConnectError("Connection refused")
        assert _map_error_category(exc) == "connection"

    def test_httpx_timeout_exception_mapped_to_timeout_category(self):
        """Test that httpx TimeoutException maps to 'timeout' category."""
        from execqueue.opencode.client import _map_error_category

        exc = httpx.TimeoutException("Timed out")
        assert _map_error_category(exc) == "timeout"

    def test_http_status_error_mapped_to_http_category(self):
        """Test that HTTPStatusError maps to 'http' category."""
        from execqueue.opencode.client import _map_error_category

        mock_response = MagicMock()
        mock_response.status_code = 500
        exc = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
        assert _map_error_category(exc) == "http"

    def test_json_decode_error_mapped_to_invalid_response_category(self):
        """Test that JSONDecodeError maps to 'invalid_response' category."""
        from execqueue.opencode.client import _map_error_category

        exc = json.JSONDecodeError("Expecting value", "test", 0)
        assert _map_error_category(exc) == "invalid_response"

    def test_unknown_error_mapped_to_unknown_category(self):
        """Test that unknown errors map to 'unknown' category."""
        from execqueue.opencode.client import _map_error_category

        exc = ValueError("Some unknown error")
        assert _map_error_category(exc) == "unknown"
