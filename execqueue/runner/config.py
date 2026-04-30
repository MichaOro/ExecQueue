"""Runner configuration for REQ-012 task execution."""

from dataclasses import dataclass
from uuid import uuid4


@dataclass
class RunnerConfig:
    """Configuration for a runner instance.

    Attributes:
        runner_id: Unique identifier for this runner instance
        poll_interval_seconds: Time between poll cycles
        batch_size: Maximum tasks to claim per poll cycle
        max_attempts: Default max retry attempts for executions
        watchdog_enabled: Whether the watchdog keep-alive feature is enabled
        watchdog_idle_seconds: Idle time before sending continue ping (seconds)
        watchdog_max_continues: Maximum number of continue pings to send
        watchdog_base_url: Base URL for OpenCode session API
        watchdog_session_id: OpenCode session ID for keep-alive pings (optional)
        watchdog_poll_interval_seconds: Poll interval for watchdog idle checks (seconds)
        watchdog_continue_prompt: Content of continue ping payload
    """

    runner_id: str
    poll_interval_seconds: int = 5
    batch_size: int = 1
    max_attempts: int = 3
    watchdog_enabled: bool = False
    watchdog_idle_seconds: int = 90
    watchdog_max_continues: int = 50
    watchdog_base_url: str = "http://127.0.0.1:4096"
    watchdog_session_id: str | None = None
    watchdog_poll_interval_seconds: int = 10
    watchdog_continue_prompt: str = "continue"

    @classmethod
    def create_default(cls) -> "RunnerConfig":
        """Create a runner config with auto-generated runner ID.

        Watchdog is disabled by default.
        """
        return cls(runner_id=str(uuid4()))
