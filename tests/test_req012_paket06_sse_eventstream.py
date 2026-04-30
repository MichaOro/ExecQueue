"""Tests for REQ-012-06 SSE Event Stream Persistenz.

This module tests:
- SSE event stream reading with timeout
- Event normalization and correlation
- Heartbeat handling
- Deduplication on reconnect
- Payload truncation
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execqueue.opencode.client import OpenCodeClient, OpenCodeEvent
from execqueue.runner.sse_handler import (
    SSEEventHandler,
    NormalizedEvent,
    create_event_handler,
    MAX_PAYLOAD_SIZE,
)


class TestNormalizedEvent:
    """Test normalized event data structure."""

    def test_normalized_event_with_small_payload(self):
        """Test normalization with small payload."""
        event = NormalizedEvent(
            event_type="message.started",
            message_id="msg_123",
            session_id="sess_456",
            payload={"status": "processing"},
        )

        assert event.event_type == "message.started"
        assert event.message_id == "msg_123"
        assert event.session_id == "sess_456"
        assert event.payload == {"status": "processing"}
        assert event.is_heartbeat is False
        assert event.sequence == 0
        assert event.received_at is not None

    def test_normalized_event_with_heartbeat(self):
        """Test normalization marks heartbeat events."""
        # Heartbeat is detected based on event_type in _normalize_event
        # So we test the detection logic directly
        handler = SSEEventHandler(
            opencode_client=MagicMock(),
            execution_id="12345678-1234-1234-1234-123456789012",
        )
        
        raw_event = OpenCodeEvent(
            event_type="heartbeat",
            data={"ts": "2024-01-01T00:00:00Z"},
        )
        
        normalized = handler._normalize_event(raw_event)
        assert normalized.is_heartbeat is True

    def test_normalized_event_truncates_large_payload(self):
        """Test that large payloads are truncated."""
        large_payload = {"data": "x" * 2000}

        event = NormalizedEvent(
            event_type="message.delta",
            payload=large_payload,
        )

        assert event.payload is not None
        assert event.payload.get("_truncated") is True
        assert "_original_size" in event.payload
        assert len(event.payload.get("_content", "")) < MAX_PAYLOAD_SIZE

    def test_normalized_event_auto_sets_received_at(self):
        """Test that received_at is auto-set."""
        event = NormalizedEvent(
            event_type="test",
        )

        assert event.received_at is not None


class TestSSEEventHandler:
    """Test SSE event handler."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock OpenCode client."""
        client = MagicMock(spec=OpenCodeClient)
        return client

    @pytest.fixture
    def handler(self, mock_client):
        """Create an SSE event handler."""
        return SSEEventHandler(
            opencode_client=mock_client,
            execution_id="12345678-1234-1234-1234-123456789012",
            session_id="sess_test",
            message_id="msg_test",
        )

    def test_handler_initialization(self, handler):
        """Test handler initialization."""
        assert handler.execution_id is not None
        assert handler.session_id == "sess_test"
        assert handler.message_id == "msg_test"
        assert handler._sequence == 0
        assert len(handler._last_event_ids) == 0

    def test_normalize_event_basic(self, handler):
        """Test basic event normalization."""
        raw_event = OpenCodeEvent(
            event_type="message.started",
            data={"id": "msg_123", "status": "processing"},
            message_id="msg_123",
            session_id="sess_456",
        )

        normalized = handler._normalize_event(raw_event)

        assert normalized.event_type == "message.started"
        assert normalized.message_id == "msg_123"
        assert normalized.session_id == "sess_456"
        assert normalized.is_heartbeat is False

    def test_normalize_event_heartbeat(self, handler):
        """Test heartbeat event normalization."""
        raw_event = OpenCodeEvent(
            event_type="heartbeat",
            data={"ts": "2024-01-01T00:00:00Z"},
        )

        normalized = handler._normalize_event(raw_event)

        assert normalized.is_heartbeat is True

    def test_is_duplicate_detection(self, handler):
        """Test duplicate detection."""
        event1 = OpenCodeEvent(
            event_type="message.started",
            data={"id": "msg_123"},
        )

        event2 = OpenCodeEvent(
            event_type="message.started",
            data={"id": "msg_123"},  # Same ID
        )

        event3 = OpenCodeEvent(
            event_type="message.started",
            data={"id": "msg_456"},  # Different ID
        )

        assert handler._is_duplicate(event1) is False
        assert handler._is_duplicate(event2) is True  # Duplicate
        assert handler._is_duplicate(event3) is False

    def test_is_terminal_event(self, handler):
        """Test terminal event detection."""
        terminal_events = [
            OpenCodeEvent(event_type="message.completed", data={}),
            OpenCodeEvent(event_type="message.failed", data={}),
            OpenCodeEvent(event_type="execution.completed", data={}),
        ]

        non_terminal_events = [
            OpenCodeEvent(event_type="message.started", data={}),
            OpenCodeEvent(event_type="message.delta", data={}),
            OpenCodeEvent(event_type="heartbeat", data={}),
        ]

        for event in terminal_events:
            assert handler._is_terminal_event(event) is True

        for event in non_terminal_events:
            assert handler._is_terminal_event(event) is False

    def test_get_heartbeat_info(self, handler):
        """Test heartbeat info extraction."""
        event = NormalizedEvent(
            event_type="heartbeat",
            payload={"ts": "2024-01-01T00:00:00Z"},
            is_heartbeat=True,
        )

        info = handler.get_heartbeat_info(event)

        assert info["event_type"] == "heartbeat"
        assert "received_at" in info
        assert info["sequence"] == 0
        assert info["payload"] == {"ts": "2024-01-01T00:00:00Z"}

    def test_reset_sequence(self, handler):
        """Test sequence reset."""
        handler._sequence = 10
        handler._last_event_ids.add("event1")
        handler._terminal_event_received = True

        handler.reset_sequence()

        assert handler._sequence == 0
        assert len(handler._last_event_ids) == 0
        assert handler._terminal_event_received is False


class TestCreateEventHandler:
    """Test factory function."""

    @pytest.mark.anyio
    async def test_create_event_handler(self):
        """Test creating an event handler."""
        mock_client = MagicMock(spec=OpenCodeClient)

        handler = await create_event_handler(
            opencode_client=mock_client,
            execution_id="12345678-1234-1234-1234-123456789012",
            session_id="sess_test",
            message_id="msg_test",
        )

        assert handler is not None
        assert handler.execution_id is not None
        assert handler.session_id == "sess_test"
        assert handler.message_id == "msg_test"


class TestEventCorrelation:
    """Test event correlation logic."""

    def test_extract_message_id_from_payload(self):
        """Test message ID extraction from payload."""
        handler = SSEEventHandler(
            opencode_client=MagicMock(),
            execution_id="12345678-1234-1234-1234-123456789012",
        )

        # Test with 'id' field
        event1 = OpenCodeEvent(
            event_type="message.started",
            data={"id": "msg_123"},
        )
        normalized1 = handler._normalize_event(event1)
        assert normalized1.message_id == "msg_123"

        # Test with 'message_id' field
        event2 = OpenCodeEvent(
            event_type="message.started",
            data={"message_id": "msg_456"},
        )
        normalized2 = handler._normalize_event(event2)
        assert normalized2.message_id == "msg_456"

    def test_extract_session_id_from_payload(self):
        """Test session ID extraction from payload."""
        handler = SSEEventHandler(
            opencode_client=MagicMock(),
            execution_id="12345678-1234-1234-1234-123456789012",
        )

        event = OpenCodeEvent(
            event_type="message.started",
            data={"session_id": "sess_789"},
        )
        normalized = handler._normalize_event(event)
        assert normalized.session_id == "sess_789"


class TestPayloadSizeLimits:
    """Test payload size limiting."""

    def test_payload_within_limit_not_truncated(self):
        """Test that payloads within limit are not truncated."""
        small_payload = {"data": "x" * 100}

        event = NormalizedEvent(
            event_type="test",
            payload=small_payload,
        )

        assert event.payload == small_payload
        assert "_truncated" not in event.payload

    def test_payload_exceeding_limit_is_truncated(self):
        """Test that payloads exceeding limit are truncated."""
        large_payload = {"data": "x" * (MAX_PAYLOAD_SIZE + 1000)}

        event = NormalizedEvent(
            event_type="test",
            payload=large_payload,
        )

        assert event.payload.get("_truncated") is True
        assert "_original_size" in event.payload
        assert len(event.payload.get("_content", "")) < MAX_PAYLOAD_SIZE
