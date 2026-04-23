from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class TaskValidationResult:
    """Result of task result validation."""
    is_done: bool
    normalized_status: str
    summary: str
    raw_status: str | None
    evidence: str = ""


def validate_task_result(output: str) -> TaskValidationResult:
    """
    Validate task execution result.
    
    Expects JSON output with structure:
    {
        "status": "done" | "not_done",
        "summary": "...",
        "evidence": "..."
    }
    
    Falls kein JSON, wird Fallback-Logik verwendet.
    """
    if not output or not output.strip():
        return TaskValidationResult(
            is_done=False,
            normalized_status="not_done",
            summary="Empty output",
            raw_status=None,
            evidence=""
        )
    
    output_stripped = output.strip()
    
    try:
        data = json.loads(output_stripped)
        
        if not isinstance(data, dict):
            return TaskValidationResult(
                is_done=False,
                normalized_status="not_done",
                summary="Result was not parseable as a valid done response.",
                raw_status=None,
                evidence=""
            )
        
        status = data.get("status", "")
        if status:
            status = status.lower()
        summary = data.get("summary", "Task marked as done." if status == "done" else "Result was not parseable as a valid done response.")
        evidence = data.get("evidence", "")
        
        if status == "done":
            return TaskValidationResult(
                is_done=True,
                normalized_status="done",
                summary=summary,
                raw_status="done",
                evidence=evidence
            )
        elif status == "not_done":
            return TaskValidationResult(
                is_done=False,
                normalized_status="not_done",
                summary=summary,
                raw_status="not_done",
                evidence=evidence
            )
        else:
            return TaskValidationResult(
                is_done=False,
                normalized_status="not_done",
                summary=summary if summary != "Task marked as done." else "Result was not parseable as a valid done response.",
                raw_status=None,
                evidence=evidence
            )
            
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parsing failed, using fallback: {e}")
        output_lower = output_stripped.lower()
        
        if "done" in output_lower:
            return TaskValidationResult(
                is_done=True,
                normalized_status="done",
                summary="Fallback validator matched DONE marker.",
                raw_status="done",
                evidence="Plain text detection"
            )
        
        return TaskValidationResult(
            is_done=False,
            normalized_status="not_done",
            summary="Result was not parseable as a valid done response.",
            raw_status=None,
            evidence="Plain text fallback"
        )
