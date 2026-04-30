"""OpenCode serve API client.

This module provides a client for the OpenCode serve HTTP API, implementing
the contract defined in REQ-012-03 with proper response validation and
error categorization as specified in REQ-012-04.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import AsyncIterator
from urllib.parse import urljoin

import httpx

from execqueue.settings import Settings


# ============================================================================
# Exception Hierarchy
# ============================================================================


class OpenCodeClientError(Exception):
    """Base exception for OpenCode client errors."""

    pass


class OpenCodeConnectionError(OpenCodeClientError):
    """Connection to OpenCode failed."""

    pass


class OpenCodeTimeoutError(OpenCodeClientError):
    """Request to OpenCode timed out."""

    pass


class OpenCodeAPIError(OpenCodeClientError):
    """OpenCode API returned an error response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"OpenCode API error ({status_code}): {message}")


class OpenCodeValidationError(OpenCodeClientError):
    """Response validation failed - required fields missing or invalid."""

    def __init__(self, message: str, details: dict | None = None):
        self.details = details or {}
        super().__init__(f"Validation error: {message}")


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True)
class OpenCodeSession:
    """OpenCode session representation."""

    id: str
    name: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class OpenCodeMessage:
    """OpenCode message/run representation."""

    id: str
    session_id: str
    status: str
    content: str | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class OpenCodeEvent:
    """OpenCode SSE event."""

    event_type: str
    data: dict
    message_id: str | None = None
    session_id: str | None = None


# ============================================================================
# Validation Functions
# ============================================================================


def _validate_session_response(data: dict) -> dict:
    """Validate session creation response.

    Args:
        data: Parsed JSON response from session creation

    Returns:
        Validated session data

    Raises:
        OpenCodeValidationError: If required fields are missing
    """
    if "id" not in data:
        raise OpenCodeValidationError(
            "Session response missing required field: 'id'",
            {"received_keys": list(data.keys())},
        )
    return data


def _validate_message_response(data: dict) -> dict:
    """Validate message dispatch/polling response.

    Args:
        data: Parsed JSON response from message operation

    Returns:
        Validated message data

    Raises:
        OpenCodeValidationError: If required fields are missing
    """
    if "id" not in data:
        raise OpenCodeValidationError(
            "Message response missing required field: 'id'",
            {"received_keys": list(data.keys())},
        )
    if "session_id" not in data and "session" not in data:
        # session_id might be optional if it's the same as the request
        pass
    return data


def _map_error_category(exception: Exception) -> str:
    """Map exception to technical error category.

    Categories per REQ-012-04:
    - connection: Connection refused, DNS failure
    - http: HTTP error status codes (4xx, 5xx)
    - timeout: Request timed out
    - invalid_response: Malformed response, validation failed

    Args:
        exception: The exception that occurred

    Returns:
        Error category string
    """
    if isinstance(exception, (OpenCodeConnectionError,)):
        return "connection"
    elif isinstance(exception, OpenCodeTimeoutError):
        return "timeout"
    elif isinstance(exception, OpenCodeAPIError):
        return "http"
    elif isinstance(exception, OpenCodeValidationError):
        return "invalid_response"
    elif isinstance(exception, httpx.ConnectError):
        return "connection"
    elif isinstance(exception, httpx.TimeoutException):
        return "timeout"
    elif isinstance(exception, httpx.HTTPStatusError):
        return "http"
    elif isinstance(exception, json.JSONDecodeError):
        return "invalid_response"
    else:
        return "unknown"


# ============================================================================
# Client Implementation
# ============================================================================


class OpenCodeClient:
    """Client for OpenCode serve API.

    This client provides access to the OpenCode serve HTTP API for
    session management, message dispatch, and event streaming.

    Features per REQ-012-04:
    - Session creation and management
    - Prompt dispatch with response validation
    - Error categorization (connection, http, timeout, invalid_response)
    - SSE event streaming

    Note: API endpoints are based on the contract from REQ-012-03 and
    require verification against a running OpenCode instance.
    See docs/REQ-012-runner-implementierung-qualitaetsverbessert/03-opencode-serve-contract.md
    for the current contract specification.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_ms: int | None = None,
        settings: Settings | None = None,
    ):
        """Initialize OpenCode client.

        Args:
            base_url: OpenCode serve base URL (e.g., http://localhost:8000)
            timeout_ms: Request timeout in milliseconds
            settings: Settings instance (used if base_url not provided)
        """
        if settings:
            self.base_url = settings.opencode_base_url
            self.timeout_ms = settings.opencode_timeout_ms
        else:
            self.base_url = base_url or "http://localhost:8000"
            self.timeout_ms = timeout_ms or 30000

        self._timeout = self.timeout_ms / 1000

    async def health(self) -> dict:
        """Check OpenCode service health.

        Returns:
            Health check response dict with 'status' field.

        Raises:
            OpenCodeConnectionError: If connection fails
            OpenCodeTimeoutError: If request times out
        """
        url = urljoin(self.base_url, "/health")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            raise OpenCodeTimeoutError(
                f"Health check timed out after {self.timeout_ms}ms"
            ) from e
        except httpx.ConnectError as e:
            raise OpenCodeConnectionError(
                f"Failed to connect to OpenCode at {url}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OpenCodeAPIError(e.response.status_code, str(e)) from e

    async def create_session(self, name: str | None = None) -> OpenCodeSession:
        """Create a new conversation session.

        Args:
            name: Optional session name

        Returns:
            Created session with ID and metadata

        Raises:
            OpenCodeConnectionError: If connection fails
            OpenCodeTimeoutError: If request times out
            OpenCodeAPIError: If session creation fails
            OpenCodeValidationError: If response is invalid

        Note:
            This endpoint is UNVERIFIED. If it fails, sessions may be
            created implicitly on first message dispatch.
        """
        url = urljoin(self.base_url, "/sessions")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {"name": name} if name else {}
                response = await client.post(url, json=payload)

                if response.status_code == 404:
                    # Session endpoint may not exist - sessions might be implicit
                    raise OpenCodeAPIError(
                        404,
                        "Session creation endpoint not found. Sessions may be created implicitly.",
                    )

                response.raise_for_status()
                data = response.json()

                # Validate response structure
                validated_data = _validate_session_response(data)

                return OpenCodeSession(
                    id=validated_data["id"],
                    name=validated_data.get("name"),
                    created_at=validated_data.get("created_at"),
                )
        except httpx.TimeoutException as e:
            raise OpenCodeTimeoutError(
                f"Session creation timed out after {self.timeout_ms}ms"
            ) from e
        except httpx.ConnectError as e:
            raise OpenCodeConnectionError(
                f"Failed to connect to OpenCode at {url}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OpenCodeAPIError(e.response.status_code, str(e)) from e
        except json.JSONDecodeError as e:
            raise OpenCodeValidationError(
                "Invalid JSON response from session creation endpoint",
                {
                    "url": url,
                    "status_code": response.status_code
                    if "response" in locals()
                    else None,
                },
            ) from e

    async def dispatch_message(
        self, session_id: str, content: str, role: str = "user"
    ) -> OpenCodeMessage:
        """Dispatch a message to a session.

        Args:
            session_id: Target session ID
            content: Message content
            role: Message role (default: "user")

        Returns:
            Message object with initial status

        Raises:
            OpenCodeConnectionError: If connection fails
            OpenCodeTimeoutError: If request times out
            OpenCodeAPIError: If message dispatch fails
            OpenCodeValidationError: If response is invalid

        Note:
            This endpoint is UNVERIFIED. Endpoint path may vary:
            - /sessions/{id}/messages (assumed)
            - /sessions/{id}/run (alternative)
            - /chat (with session in body)
        """
        # Try primary endpoint pattern
        url = urljoin(self.base_url, f"/sessions/{session_id}/messages")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {"content": content, "role": role}
                response = await client.post(url, json=payload)

                if response.status_code == 404:
                    # Try alternative endpoint pattern
                    url = urljoin(self.base_url, f"/sessions/{session_id}/run")
                    response = await client.post(url, json=payload)

                response.raise_for_status()
                data = response.json()

                # Validate response structure
                validated_data = _validate_message_response(data)

                return OpenCodeMessage(
                    id=validated_data["id"],
                    session_id=validated_data.get("session_id", session_id),
                    status=validated_data.get("status", "processing"),
                    content=validated_data.get("content"),
                    created_at=validated_data.get("created_at"),
                    completed_at=validated_data.get("completed_at"),
                )
        except httpx.TimeoutException as e:
            raise OpenCodeTimeoutError(
                f"Message dispatch timed out after {self.timeout_ms}ms"
            ) from e
        except httpx.ConnectError as e:
            raise OpenCodeConnectionError(
                f"Failed to connect to OpenCode at {url}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OpenCodeAPIError(e.response.status_code, str(e)) from e
        except json.JSONDecodeError as e:
            raise OpenCodeValidationError(
                "Invalid JSON response from message dispatch endpoint",
                {
                    "url": url,
                    "status_code": response.status_code
                    if "response" in locals()
                    else None,
                },
            ) from e

    async def get_message(self, session_id: str, message_id: str) -> OpenCodeMessage:
        """Get message status and result (polling).

        Args:
            session_id: Session ID
            message_id: Message ID

        Returns:
            Message object with current status and content

        Raises:
            OpenCodeConnectionError: If connection fails
            OpenCodeTimeoutError: If request times out
            OpenCodeAPIError: If message retrieval fails
            OpenCodeValidationError: If response is invalid

        Note:
            This endpoint is UNVERIFIED. May not exist if SSE is the
            primary result delivery mechanism.
        """
        url = urljoin(self.base_url, f"/sessions/{session_id}/messages/{message_id}")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                # Validate response structure
                validated_data = _validate_message_response(data)

                return OpenCodeMessage(
                    id=validated_data["id"],
                    session_id=validated_data.get("session_id", session_id),
                    status=validated_data.get("status", "unknown"),
                    content=validated_data.get("content"),
                    error=validated_data.get("error"),
                    created_at=validated_data.get("created_at"),
                    completed_at=validated_data.get("completed_at"),
                )
        except httpx.TimeoutException as e:
            raise OpenCodeTimeoutError(
                f"Message retrieval timed out after {self.timeout_ms}ms"
            ) from e
        except httpx.ConnectError as e:
            raise OpenCodeConnectionError(
                f"Failed to connect to OpenCode at {url}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OpenCodeAPIError(e.response.status_code, str(e)) from e
        except json.JSONDecodeError as e:
            raise OpenCodeValidationError(
                "Invalid JSON response from message retrieval endpoint",
                {
                    "url": url,
                    "status_code": response.status_code
                    if "response" in locals()
                    else None,
                },
            ) from e

    async def stream_events(
        self, session_id: str | None = None, message_id: str | None = None
    ) -> AsyncIterator[OpenCodeEvent]:
        """Stream events via SSE.

        Args:
            session_id: Optional session filter
            message_id: Optional message filter

        Yields:
            OpenCodeEvent objects from the SSE stream

        Raises:
            OpenCodeConnectionError: If connection fails
            OpenCodeTimeoutError: If connection times out
            OpenCodeAPIError: If SSE endpoint returns error

        Note:
            This endpoint is UNVERIFIED. Endpoint path may vary:
            - /event (assumed, with query params)
            - /sessions/{id}/events (alternative)
            - May require POST with subscription body
        """
        # Build URL with query parameters
        url = urljoin(self.base_url, "/event")
        if session_id or message_id:
            from urllib.parse import urlencode

            params = {}
            if session_id:
                params["session_id"] = session_id
            if message_id:
                params["message_id"] = message_id
            url = f"{url}?{urlencode(params)}"

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code == 404:
                        raise OpenCodeAPIError(
                            404,
                            "SSE endpoint not found. May require different path or method.",
                        )

                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_str = line[5:].strip()
                            try:
                                data = json.loads(data_str)
                                yield OpenCodeEvent(
                                    event_type=event_type,
                                    data=data,
                                    message_id=data.get("id"),
                                    session_id=data.get("session_id"),
                                )
                            except json.JSONDecodeError:
                                # Non-JSON data, yield as-is
                                yield OpenCodeEvent(
                                    event_type=event_type,
                                    data={"raw": data_str},
                                )
                        elif line == "":
                            # Empty line separates events
                            pass
        except httpx.TimeoutException as e:
            raise OpenCodeTimeoutError("SSE stream timed out") from e
        except httpx.ConnectError as e:
            raise OpenCodeConnectionError(
                f"Failed to connect to OpenCode at {url}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OpenCodeAPIError(e.response.status_code, str(e)) from e

    async def close(self):
        """Close client and cleanup resources."""
        pass  # httpx client is context-managed

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
