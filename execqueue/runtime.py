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


def get_scheduler_backoff_multiplier() -> float:
    """Liefert den Multiplikator für exponentielles Backoff."""
    value = os.getenv("SCHEDULER_BACKOFF_MULTIPLIER")
    if value is None:
        return 2.0
    
    try:
        multiplier = float(value.strip())
        if multiplier < 1.0:
            logger.warning(
                "SCHEDULER_BACKOFF_MULTIPLIER %f below minimum 1.0, using default 2.0",
                multiplier
            )
            return 2.0
        return multiplier
    except ValueError:
        logger.warning(
            "Invalid SCHEDULER_BACKOFF_MULTIPLIER value '%s', using default 2.0",
            value
        )
        return 2.0


def get_scheduler_backoff_min_delay() -> int:
    """Liefert die minimale Wartezeit in Sekunden für Backoff."""
    value = os.getenv("SCHEDULER_BACKOFF_MIN_DELAY")
    if value is None:
        return 10
    
    try:
        delay = int(value.strip())
        if delay < 1:
            logger.warning(
                "SCHEDULER_BACKOFF_MIN_DELAY %d below minimum 1, using default 10",
                delay
            )
            return 10
        return delay
    except ValueError:
        logger.warning(
            "Invalid SCHEDULER_BACKOFF_MIN_DELAY value '%s', using default 10",
            value
        )
        return 10


def get_scheduler_backoff_max_delay() -> int:
    """Liefert die maximale Wartezeit in Sekunden für Backoff."""
    value = os.getenv("SCHEDULER_BACKOFF_MAX_DELAY")
    if value is None:
        return 300
    
    try:
        delay = int(value.strip())
        if delay < 1:
            logger.warning(
                "SCHEDULER_BACKOFF_MAX_DELAY %d below minimum 1, using default 300",
                delay
            )
            return 300
        return delay
    except ValueError:
        logger.warning(
            "Invalid SCHEDULER_BACKOFF_MAX_DELAY value '%s', using default 300",
            value
        )
        return 300


def get_opencode_base_url() -> str | None:
    """Liefert die Basis-URL der OpenCode API."""
    return os.getenv("OPENCODE_BASE_URL")


def get_opencode_timeout() -> int:
    """Liefert den Timeout in Sekunden für OpenCode API-Requests."""
    value = os.getenv("OPENCODE_TIMEOUT")
    if value is None:
        return 120
    
    try:
        timeout = int(value.strip())
        if timeout < 5 or timeout > 600:
            logger.warning(
                "OPENCODE_TIMEOUT %d outside valid range [5, 600], using default 120",
                timeout
            )
            return 120
        return timeout
    except ValueError:
        logger.warning(
            "Invalid OPENCODE_TIMEOUT value '%s', using default 120",
            value
        )
        return 120


def get_opencode_max_retries() -> int:
    """Liefert die maximale Anzahl an Retries bei Netzwerkfehlern."""
    value = os.getenv("OPENCODE_MAX_RETRIES")
    if value is None:
        return 3
    
    try:
        retries = int(value.strip())
        if retries < 0 or retries > 10:
            logger.warning(
                "OPENCODE_MAX_RETRIES %d outside valid range [0, 10], using default 3",
                retries
            )
            return 3
        return retries
    except ValueError:
        logger.warning(
            "Invalid OPENCODE_MAX_RETRIES value '%s', using default 3",
            value
        )
        return 3


def get_opencode_username() -> str | None:
    """Liefert den Username für die OpenCode API-Authentifizierung."""
    return os.getenv("OPENCODE_USERNAME")


def get_opencode_password() -> str | None:
    """Liefert das Passwort für die OpenCode API-Authentifizierung."""
    return os.getenv("OPENCODE_PASSWORD")


def get_worker_instance_id() -> str:
    """Liefert die eindeutige ID dieser Worker-Instanz."""
    return os.getenv("WORKER_INSTANCE_ID") or f"worker-{os.getpid()}"


def get_worker_lock_timeout_seconds() -> int:
    """Liefert den Timeout in Sekunden für Worker-Locks."""
    value = os.getenv("WORKER_LOCK_TIMEOUT_SECONDS")
    if value is None:
        return 300
    
    try:
        timeout = int(value.strip())
        if timeout < 30 or timeout > 3600:
            logger.warning(
                "WORKER_LOCK_TIMEOUT_SECONDS %d outside valid range [30, 3600], using default 300",
                timeout
            )
            return 300
        return timeout
    except ValueError:
        logger.warning(
            "Invalid WORKER_LOCK_TIMEOUT_SECONDS value '%s', using default 300",
            value
        )
        return 300
