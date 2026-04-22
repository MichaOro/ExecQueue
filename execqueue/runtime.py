from __future__ import annotations

import logging
import os


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_test_mode() -> bool:
    return _bool_env("EXECQUEUE_TEST_MODE", "PYTEST_CURRENT_TEST" in os.environ)


def get_test_prefix() -> str:
    return os.getenv("TEST_QUEUE_PREFIX", "test_")


def get_test_suffix() -> str:
    return os.getenv("TEST_QUEUE_SUFFIX", "")


def apply_test_label(title: str) -> str:
    if not is_test_mode():
        return title

    prefix = get_test_prefix()
    suffix = get_test_suffix()
    labeled = title

    if prefix and not labeled.startswith(prefix):
        labeled = f"{prefix}{labeled}"

    if suffix and not labeled.endswith(suffix):
        labeled = f"{labeled}{suffix}"

    return labeled


logger = logging.getLogger(__name__)


def is_scheduler_enabled() -> bool:
    """Prüft, ob der Background Scheduler aktiviert ist."""
    return _bool_env("SCHEDULER_ENABLED", False)


def get_scheduler_task_delay() -> int:
    """Liefert das Delay in Sekunden zwischen Task-Versuchen."""
    value = os.getenv("SCHEDULER_TASK_DELAY")
    if value is None:
        return 5
    
    try:
        delay = int(value.strip())
        if delay < 1 or delay > 300:
            logger.warning(
                "SCHEDULER_TASK_DELAY %d outside valid range [1, 300], using default 5",
                delay
            )
            return 5
        return delay
    except ValueError:
        logger.warning(
            "Invalid SCHEDULER_TASK_DELAY value '%s', using default 5",
            value
        )
        return 5


def get_scheduler_shutdown_timeout() -> int:
    """Liefert den Timeout in Sekunden für Graceful Shutdown."""
    value = os.getenv("SCHEDULER_SHUTDOWN_TIMEOUT")
    if value is None:
        return 30
    
    try:
        timeout = int(value.strip())
        if timeout < 5 or timeout > 120:
            logger.warning(
                "SCHEDULER_SHUTDOWN_TIMEOUT %d outside valid range [5, 120], using default 30",
                timeout
            )
            return 30
        return timeout
    except ValueError:
        logger.warning(
            "Invalid SCHEDULER_SHUTDOWN_TIMEOUT value '%s', using default 30",
            value
        )
        return 30
