from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of task result validation."""
    is_done: bool
    normalized_status: str
    summary: str


def validate_task_result(output: str) -> ValidationResult:
    """
    Validate task execution result.
    
    Checks if the output indicates successful completion.
    """
    if not output:
        return ValidationResult(
            is_done=False,
            normalized_status="not_done",
            summary="Empty output"
        )
    
    output_lower = output.lower()
    
    if "done" in output_lower or '{"status": "done"}' in output_lower:
        return ValidationResult(
            is_done=True,
            normalized_status="done",
            summary="Task completed successfully"
        )
    
    return ValidationResult(
        is_done=False,
        normalized_status="not_done",
        summary=output[:200] if len(output) > 200 else output
    )
