"""Watchdog implementation for OpenCode session keep-alive.

This module provides a Watchdog class that sends periodic continue pings to
an OpenCode session during periods of inactivity, preventing the session
from timing out.

The watchdog is designed to be non-intrusive:
- It only activates when explicitly enabled via configuration
- It requires a valid session_id to function
- HTTP errors are logged but do not crash the runner
- The maximum number of continue pings is configurable
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Final

import httpx

from execqueue.runner.config import RunnerConfig

logger = logging.getLogger(__name__)

# Continue prompt used for keep-alive pings (configurable via RunnerConfig)
CONTINUE_PROMPT: Final[str] = "continue"


class Watchdog:
    """Watchdog for OpenCode session keep-alive.

    The watchdog monitors activity and sends continue pings to an OpenCode
    session when the session has been idle for a configured duration.

    Attributes:
        config: Runner configuration containing watchdog settings
    """

    def __init__(
        self,
        config: RunnerConfig,
        poll_interval: int | None = None,
        http_client: httpx.AsyncClient | None = None,
        on_continue_sent: Callable[[int], None] | None = None,
    ):
        """Initialize the watchdog.

        Args:
            config: Runner configuration with watchdog settings
            poll_interval: Optional override for poll interval (for testing)
            http_client: Optional pre-configured HTTP client (for testing)
            on_continue_sent: Optional callback invoked after each successful ping
        """
        self.config = config
        self._poll_interval = poll_interval or config.watchdog_poll_interval_seconds
        self._http_client_override = http_client
        self._on_continue_sent = on_continue_sent

        # Internal state
        self._task: asyncio.Task | None = None
        self._running = False
        self._continues_sent = 0
        self._last_activity_time: float | None = None  # monotonic time
        self._http_client: httpx.AsyncClient | None = None

    @property
    def is_running(self) -> bool:
        """Check if the watchdog is currently running."""
        return self._running and self._task is not None and not self._task.done()

    @property
    def continues_sent(self) -> int:
        """Return the number of continue pings sent."""
        return self._continues_sent

    def record_activity(self) -> None:
        """Record an activity event to reset the idle timer."""
        self._last_activity_time = time.monotonic()
        logger.debug("Watchdog activity recorded")

    def set_session_id(self, session_id: str) -> None:
        """Set the OpenCode session ID for watchdog keep-alive.

        This method allows dynamically setting the session ID after
        the Watchdog is created, enabling the initialization flow where
        the session is created before the watchdog is started.

        Args:
            session_id: OpenCode session ID to use for keep-alive pings
        """
        self.config.watchdog_session_id = session_id
        logger.debug(f"Watchdog session_id set to {session_id}")

    async def start(self) -> None:
        """Start the watchdog.

        This is a no-op if:
        - watchdog_enabled is False in config
        - watchdog_session_id is not set

        If already running, this method is idempotent.
        """
        if not self.config.watchdog_enabled:
            logger.debug("Watchdog is disabled in config, not starting")
            return

        if not self.config.watchdog_session_id:
            logger.warning(
                "Watchdog enabled but session_id not set, not starting. "
                "Set watchdog_session_id in config to enable keep-alive pings."
            )
            return

        if self.is_running:
            logger.debug("Watchdog is already running")
            return

        logger.info(
            f"Starting watchdog for session {self.config.watchdog_session_id} "
            f"(idle_threshold={self.config.watchdog_idle_seconds}s, "
            f"max_continues={self.config.watchdog_max_continues}, "
            f"poll_interval={self._poll_interval}s)"
        )

        # Log endpoint URL at DEBUG for operator verification
        url = f"{self.config.watchdog_base_url}/sessions/{self.config.watchdog_session_id}/messages"
        logger.debug(f"Watchdog endpoint: {url}")

        self._running = True
        if self._http_client_override:
            self._http_client = self._http_client_override
        else:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the watchdog gracefully.

        Cancels the background task and closes the HTTP client.
        This method is idempotent.
        """
        if not self._running:
            return

        logger.info(
            f"Stopping watchdog for session {self.config.watchdog_session_id} "
            f"(continues_sent={self._continues_sent})"
        )
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("Watchdog task cancelled")
            self._task = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _run(self) -> None:
        """Main watchdog loop.

        Monitors idle time and sends continue pings when:
        - The session has been idle for longer than watchdog_idle_seconds
        - The maximum number of continues has not been reached
        """
        logger.debug("Watchdog loop started")

        try:
            while self._running:
                await asyncio.sleep(self._poll_interval)

                if not self._should_send_ping():
                    continue

                await self._send_continue_ping()

        except asyncio.CancelledError:
            logger.info("Watchdog loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Watchdog loop error: {e}", exc_info=True)
            # Don't crash - continue running or stop based on error severity
            # For now, we'll stop on unexpected errors
            self._running = False

    def _should_send_ping(self) -> bool:
        """Check if a ping should be sent.

        Uses monotonic time for consistent idle interval measurement.

        Returns:
            True if conditions are met for sending a ping
        """
        if not self._last_activity_time:
            # No activity recorded yet, don't ping
            return False

        if self._continues_sent >= self.config.watchdog_max_continues:
            logger.debug(
                f"Max continues ({self.config.watchdog_max_continues}) reached"
            )
            return False

        idle_seconds = time.monotonic() - self._last_activity_time
        if idle_seconds < self.config.watchdog_idle_seconds:
            return False

        return True

    async def _send_continue_ping(self) -> None:
        """Send a continue ping to the OpenCode session."""
        if not self._http_client:
            logger.error("HTTP client not initialized, cannot send ping")
            return

        url = f"{self.config.watchdog_base_url}/sessions/{self.config.watchdog_session_id}/messages"
        payload = {"content": self.config.watchdog_continue_prompt, "role": "user"}

        try:
            logger.debug(f"Sending continue ping to {url}")
            response = await self._http_client.post(url, json=payload)

            if response.status_code >= 400:
                logger.warning(
                    f"Continue ping failed with status {response.status_code}: "
                    f"{response.text[:200]}"
                )
            else:
                self._continues_sent += 1
                logger.debug(
                    f"Continue ping sent successfully (total: {self._continues_sent})"
                )
                # Invoke optional metrics hook
                if self._on_continue_sent:
                    self._on_continue_sent(self._continues_sent)

        except httpx.RequestError as e:
            logger.warning(f"Continue ping request error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending continue ping: {e}", exc_info=True)
