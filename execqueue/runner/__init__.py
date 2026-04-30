"""Runner module for REQ-012 task execution lifecycle.

This module provides the runner implementation for claiming and executing
prepared tasks with atomic claim semantics, prompt dispatch, SSE event handling,
result inspection, commit adoption, validator integration, and watchdog keep-alive.
"""

from execqueue.runner.claim import ClaimFailedError, claim_task
from execqueue.runner.polling import poll_and_claim_tasks
from execqueue.runner.prompt_templates import build_prompt, build_readonly_prompt, build_write_prompt
from execqueue.runner.dispatch import PromptDispatcher, DispatchError
from execqueue.runner.sse_handler import (
    SSEEventHandler,
    NormalizedEvent,
    create_event_handler,
    MAX_PAYLOAD_SIZE,
)
from execqueue.runner.result_inspector import (
    ResultInspector,
    InspectionResult,
    inspect_task_result,
)
from execqueue.runner.commit_adopter import (
    CommitAdopter,
    AdoptionResult,
    adopt_commit,
)
from execqueue.runner.validator import Validator, MockValidator
from execqueue.runner.watchdog import Watchdog

__all__ = [
    "ClaimFailedError",
    "claim_task",
    "poll_and_claim_tasks",
    "build_prompt",
    "build_readonly_prompt",
    "build_write_prompt",
    "PromptDispatcher",
    "DispatchError",
    "SSEEventHandler",
    "NormalizedEvent",
    "create_event_handler",
    "MAX_PAYLOAD_SIZE",
    "ResultInspector",
    "InspectionResult",
    "inspect_task_result",
    "CommitAdopter",
    "AdoptionResult",
    "adopt_commit",
    "Validator",
    "MockValidator",
    "Watchdog",
]
