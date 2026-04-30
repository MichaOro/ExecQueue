"""OpenCode integration helpers.

This module provides the OpenCode serve API client with proper response
validation and error categorization as specified in REQ-012-04.
"""

from execqueue.opencode.client import (
    OpenCodeClient,
    OpenCodeClientError,
    OpenCodeConnectionError,
    OpenCodeAPIError,
    OpenCodeTimeoutError,
    OpenCodeValidationError,
    OpenCodeSession,
    OpenCodeMessage,
    OpenCodeEvent,
    _map_error_category,
)
from execqueue.opencode.health import (
    probe_opencode_endpoint,
    get_opencode_healthcheck,
    OpenCodeReachability,
    OpenCodeState,
)

__all__ = [
    # Client
    "OpenCodeClient",
    "OpenCodeClientError",
    "OpenCodeConnectionError",
    "OpenCodeAPIError",
    "OpenCodeTimeoutError",
    "OpenCodeValidationError",
    "OpenCodeSession",
    "OpenCodeMessage",
    "OpenCodeEvent",
    "_map_error_category",
    # Health
    "probe_opencode_endpoint",
    "get_opencode_healthcheck",
    "OpenCodeReachability",
    "OpenCodeState",
]
