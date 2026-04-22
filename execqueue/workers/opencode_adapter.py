from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class OpenCodeExecutionResult:
    status: str  # raw/external status, not trusted as final truth
    raw_output: str
    summary: Optional[str] = None


def execute_with_opencode(prompt: str, verification_prompt: str | None = None) -> OpenCodeExecutionResult:
    """
    Placeholder adapter for OpenCode.

    Replace this later with the real OpenCode integration, e.g.:
    - CLI call
    - HTTP call
    - SDK call

    Contract:
    Returns raw output from OpenCode. Validation happens separately.
    """

    # TODO: Replace with real OpenCode invocation.
    # For now this is a deterministic stub so the scheduler can be implemented and tested.
    simulated_output = """
    {
      "status": "done",
      "summary": "Stub execution completed successfully.",
      "evidence": "No real OpenCode integration attached yet."
    }
    """.strip()

    return OpenCodeExecutionResult(
        status="completed",
        raw_output=simulated_output,
        summary="Stub execution completed successfully.",
    )