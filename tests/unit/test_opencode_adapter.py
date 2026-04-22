import pytest
import json
from execqueue.workers.opencode_adapter import (
    execute_with_opencode,
    OpenCodeExecutionResult,
)
from execqueue.validation.task_validator import validate_task_result


class TestExecuteWithOpencode:
    """Tests for execute_with_opencode function in opencode_adapter."""

    def test_stub_execution_returns_result(self):
        """Test: Stub execution returns OpenCodeExecutionResult."""
        result = execute_with_opencode(prompt="test prompt")

        assert isinstance(result, OpenCodeExecutionResult)
        assert result.status == "completed"
        assert result.raw_output is not None
        assert result.summary is not None

    def test_stub_execution_deterministic_output(self):
        """Test: Stub returns deterministic output regardless of input."""
        result1 = execute_with_opencode(prompt="first prompt")
        result2 = execute_with_opencode(prompt="completely different prompt")

        assert result1.raw_output == result2.raw_output
        assert result1.summary == result2.summary

    def test_stub_output_contains_valid_json(self):
        """Test: raw_output contains parseable JSON."""
        result = execute_with_opencode(prompt="test")

        parsed = json.loads(result.raw_output)
        assert "status" in parsed
        assert "summary" in parsed

    def test_stub_output_parsed_by_validator(self):
        """Test: Validator can parse the stub output."""
        result = execute_with_opencode(
            prompt="test prompt", verification_prompt="verify"
        )

        validation = validate_task_result(result.raw_output)

        assert validation.is_done is True
        assert validation.normalized_status == "done"

    def test_stub_contract_status_field(self):
        """Test: Result always has status field."""
        result = execute_with_opencode(prompt="test")

        assert result.status in ["completed", "failed", "error"]

    def test_stub_contract_raw_output_field(self):
        """Test: Result always has raw_output field."""
        result = execute_with_opencode(prompt="test")

        assert result.raw_output is not None
        assert isinstance(result.raw_output, str)
        assert len(result.raw_output) > 0

    def test_stub_contract_summary_field(self):
        """Test: Result has optional summary field."""
        result = execute_with_opencode(prompt="test")

        assert result.summary is not None
        assert isinstance(result.summary, str)

    def test_stub_ignores_verification_prompt(self):
        """Test: Stub ignores verification_prompt parameter."""
        result1 = execute_with_opencode(prompt="test", verification_prompt=None)
        result2 = execute_with_opencode(prompt="test", verification_prompt="strict verify")

        assert result1.raw_output == result2.raw_output

    def test_stub_output_structure(self):
        """Test: Stub output has expected JSON structure."""
        result = execute_with_opencode(prompt="test")

        parsed = json.loads(result.raw_output)

        assert parsed["status"] in ["done", "not_done"]
        assert "summary" in parsed
        assert isinstance(parsed["summary"], str)
