from __future__ import annotations

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
