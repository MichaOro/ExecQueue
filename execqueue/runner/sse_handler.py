"""SSE Event Stream handler for REQ-012-06.

This module implements:
- SSE event stream reading with timeout/cancel support
- Event normalization and correlation
- Heartbeat handling for liveness
- Append-only persistence with sequence numbers
- Deduplication on reconnect
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import UUID

from execqueue.models.enums import EventType
from execqueue.opencode.client import OpenCodeClient, OpenCodeEvent, OpenCodeTimeoutError

logger = logging.getLogger(__name__)


# Maximum payload size to store (1KB)
MAX_PAYLOAD_SIZE = 1024


@dataclass
class NormalizedEvent:
    """Normalized event representation for persistence.

    Attributes:
        event_type: Normalized event type
        message_id: Associated message ID if available
        session_id: Associated session ID if available
        payload: Truncated payload (max MAX_PAYLOAD_SIZE bytes)
        sequence: Sequence number (assigned on persistence)
        received_at: When the event was received
        is_heartbeat: Whether this is a heartbeat event
    """
    event_type: str
    message_id: str | None = None
    session_id: str | None = None
    payload: dict | None = None
    sequence: int = 0
    received_at: datetime = None
    is_heartbeat: bool = False

    def __post_init__(self):
        if self.received_at is None:
            self.received_at = datetime.now(timezone.utc)

        # Truncate payload if too large
        if self.payload:
            payload_str = json.dumps(self.payload)
            if len(payload_str) > MAX_PAYLOAD_SIZE:
                self.payload = {
                    "_truncated": True,
                    "_original_size": len(payload_str),
                    "_content": payload_str[:MAX_PAYLOAD_SIZE - 100] + "...[truncated]",
                }


class SSEEventHandler:
    """Handler for SSE event streams with persistence support.

    This class provides:
    - Event stream reading with proper timeout handling
    - Event normalization and correlation
    - Heartbeat detection and liveness tracking
    - Deduplication logic for reconnect scenarios
    """

    # Heartbeat event types
    HEARTBEAT_EVENT_TYPES = frozenset(["heartbeat", "stream.heartbeat"])

    # Event types that indicate completion/failure
    TERMINAL_EVENT_TYPES = frozenset([
        "message.completed",
        "message.failed",
        "message.cancelled",
        "execution.completed",
        "execution.failed",
    ])

    def __init__(
        self,
        opencode_client: OpenCodeClient,
        execution_id: UUID,
        session_id: str | None = None,
        message_id: str | None = None,
    ):
        """Initialize SSE event handler.

        Args:
            opencode_client: OpenCode client for stream access
            execution_id: TaskExecution ID to correlate events
            session_id: Optional OpenCode session ID for filtering
            message_id: Optional OpenCode message ID for filtering
        """
        self.opencode_client = opencode_client
        self.execution_id = execution_id
        self.session_id = session_id
        self.message_id = message_id
        self._sequence = 0
        self._last_event_ids: set[str] = set()  # For deduplication
        self._terminal_event_received = False

    def _normalize_event(self, event: OpenCodeEvent) -> NormalizedEvent:
        """Normalize an OpenCodeEvent for persistence.

        Args:
            event: Raw OpenCodeEvent from stream

        Returns:
            NormalizedEvent ready for persistence
        """
        is_heartbeat = event.event_type in self.HEARTBEAT_EVENT_TYPES

        # Extract message/session IDs from payload if not in event
        payload = event.data or {}
        message_id = event.message_id or payload.get("id") or payload.get("message_id")
        session_id = event.session_id or payload.get("session_id")

        return NormalizedEvent(
            event_type=event.event_type,
            message_id=message_id,
            session_id=session_id,
            payload=payload,
            sequence=self._sequence,
            received_at=datetime.now(timezone.utc),
            is_heartbeat=is_heartbeat,
        )

    def _is_duplicate(self, event: OpenCodeEvent) -> bool:
        """Check if an event is a duplicate (e.g., from reconnect).

        Args:
            event: Event to check

        Returns:
            True if event is a duplicate
        """
        # Use event ID from payload if available
        event_id = None
        if event.data and "id" in event.data:
            event_id = event.data["id"]
        elif event.data and "message_id" in event.data:
            event_id = event.data["message_id"]

        if event_id:
            if event_id in self._last_event_ids:
                return True
            self._last_event_ids.add(event_id)
            # Keep only last 100 event IDs for memory efficiency
            if len(self._last_event_ids) > 100:
                self._last_event_ids.clear()

        return False

    def _is_terminal_event(self, event: OpenCodeEvent) -> bool:
        """Check if an event indicates terminal state.

        Args:
            event: Event to check

        Returns:
            True if event indicates completion/failure
        """
        return event.event_type in self.TERMINAL_EVENT_TYPES

    async def stream_events(
        self,
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[NormalizedEvent]:
        """Stream and normalize events from OpenCode.

        Args:
            timeout_seconds: Optional timeout for the stream

        Yields:
            NormalizedEvent objects, filtered and deduplicated

        Raises:
            asyncio.TimeoutError: If stream times out
            OpenCodeTimeoutError: If OpenCode connection times out
        """
        try:
            stream_task = asyncio.create_task(
                self._stream_events_internal()
            )

            if timeout_seconds:
                async for event in asyncio.wait_for(
                    self._event_generator_with_timeout(stream_task, timeout_seconds),
                    timeout=timeout_seconds
                ):
                    yield event
            else:
                async for event in stream_task:
                    yield event

        except asyncio.CancelledError:
            logger.info(
                f"SSE stream cancelled for execution {self.execution_id}"
            )
            raise
        except asyncio.TimeoutError:
            logger.warning(
                f"SSE stream timed out after {timeout_seconds}s for execution {self.execution_id}"
            )
            raise
        except Exception as e:
            logger.error(
                f"SSE stream error for execution {self.execution_id}: {e}",
                exc_info=True,
            )
            raise

    async def _event_generator_with_timeout(
        self,
        stream_task: asyncio.Task,
        timeout_seconds: int,
    ) -> AsyncIterator[NormalizedEvent]:
        """Wrap stream task with timeout.

        Args:
            stream_task: The streaming task
            timeout_seconds: Timeout in seconds

        Yields:
            Events from the stream
        """
        try:
            async for event in stream_task:
                yield event
        except asyncio.TimeoutError:
            stream_task.cancel()
            raise

    async def _stream_events_internal(
        self,
    ) -> AsyncIterator[NormalizedEvent]:
        """Internal event streaming logic.

        Yields:
            NormalizedEvent objects
        """
        try:
            async for raw_event in self.opencode_client.stream_events(
                session_id=self.session_id,
                message_id=self.message_id,
            ):
                # Check for terminal event
                if self._is_terminal_event(raw_event):
                    self._terminal_event_received = True

                # Skip duplicates
                if self._is_duplicate(raw_event):
                    logger.debug(
                        f"Skipping duplicate event: {raw_event.event_type}"
                    )
                    continue

                # Normalize event
                normalized = self._normalize_event(raw_event)
                normalized.sequence = self._sequence
                self._sequence += 1

                logger.debug(
                    f"Event {normalized.event_type} (seq={normalized.sequence}) "
                    f"for execution {self.execution_id}"
                )

                yield normalized

        except Exception as e:
            # Stream ended - check if it was a terminal event
            if not self._terminal_event_received:
                logger.warning(
                    f"SSE stream ended unexpectedly for execution {self.execution_id}: {e}"
                )
            raise

    def get_heartbeat_info(self, event: NormalizedEvent) -> dict:
        """Extract heartbeat information for liveness tracking.

        Args:
            event: Normalized event (should be a heartbeat)

        Returns:
            Dict with heartbeat metadata
        """
        if not event.is_heartbeat:
            raise ValueError("Event is not a heartbeat")

        return {
            "event_type": event.event_type,
            "received_at": event.received_at.isoformat(),
            "sequence": event.sequence,
            "payload": event.payload,
        }

    def reset_sequence(self):
        """Reset sequence counter (e.g., after reconnect).

        Note: This should only be called when starting a fresh stream.
        """
        self._sequence = 0
        self._last_event_ids.clear()
        self._terminal_event_received = False


async def create_event_handler(
    opencode_client: OpenCodeClient,
    execution_id: UUID,
    session_id: str | None = None,
    message_id: str | None = None,
) -> SSEEventHandler:
    """Factory function to create an SSE event handler.

    Args:
        opencode_client: OpenCode client
        execution_id: TaskExecution ID
        session_id: Optional OpenCode session ID
        message_id: Optional OpenCode message ID

    Returns:
        Configured SSEEventHandler instance
    """
    return SSEEventHandler(
        opencode_client=opencode_client,
        execution_id=execution_id,
        session_id=session_id,
        message_id=message_id,
    )
