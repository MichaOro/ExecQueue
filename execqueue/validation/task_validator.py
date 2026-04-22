from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class TaskValidationResult:
    is_done: bool
    normalized_status: str  # "done" | "not_done"
    summary: str
    raw_status: str | None = None


def validate_task_result(raw_output: str) -> TaskValidationResult:
    """
    Preferred contract from OpenCode:
    {
      "status": "done" | "not_done",
      "summary": "..."
    }

    Fallback:
    - if JSON parsing fails, look for strict text markers.
    """

    text = (raw_output or "").strip()

    # Preferred: strict JSON
    try:
        payload = json.loads(text)
        status = str(payload.get("status", "")).strip().lower()
        summary = str(payload.get("summary", "")).strip()

        if status == "done":
            return TaskValidationResult(
                is_done=True,
                normalized_status="done",
                summary=summary or "Task marked as done.",
                raw_status=status,
            )

        return TaskValidationResult(
            is_done=False,
            normalized_status="not_done",
            summary=summary or "Task not completed.",
            raw_status=status or None,
        )
    except json.JSONDecodeError:
        pass

    # Fallback: strict textual markers only
    upper_text = text.upper()

    if '"STATUS": "DONE"' in upper_text or "\nDONE\n" in f"\n{upper_text}\n":
        return TaskValidationResult(
            is_done=True,
            normalized_status="done",
            summary="Fallback validator matched DONE marker.",
            raw_status="done",
        )

    return TaskValidationResult(
        is_done=False,
        normalized_status="not_done",
        summary="Result was not parseable as a valid done response.",
        raw_status=None,
    )