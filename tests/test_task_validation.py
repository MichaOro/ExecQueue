"""Tests for task validation logic."""

from __future__ import annotations

import pytest

from execqueue.tasks.service import (
    ALLOWED_INTAKE_TYPES,
    ALLOWED_TASK_TYPES,
    validate_task_type,
)


class TestValidateTaskType:
    """Tests for the validate_task_type function."""

    def test_validates_planning_type(self):
        """Planning type should pass validation unchanged."""
        result = validate_task_type("planning")
        assert result == "planning"

    def test_validates_execution_type(self):
        """Execution type should pass validation unchanged."""
        result = validate_task_type("execution")
        assert result == "execution"

    def test_validates_analysis_type(self):
        """Analysis type should pass validation unchanged."""
        result = validate_task_type("analysis")
        assert result == "analysis"

    def test_maps_requirement_to_planning(self):
        """Requirement type should be mapped to planning."""
        result = validate_task_type("requirement")
        assert result == "planning"

    def test_rejects_invalid_type(self):
        """Invalid type should raise ValueError with descriptive message."""
        with pytest.raises(ValueError) as exc_info:
            validate_task_type("incident")

        assert "Invalid task type 'incident'" in str(exc_info.value)
        assert "requirement" in str(exc_info.value)
        assert "planning" in str(exc_info.value)
        assert "execution" in str(exc_info.value)
        assert "analysis" in str(exc_info.value)

    def test_rejects_unknown_type(self):
        """Unknown type should raise ValueError."""
        with pytest.raises(ValueError):
            validate_task_type("unknown")

    def test_rejects_empty_string(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError):
            validate_task_type("")

    def test_allowed_intake_types_constant(self):
        """ALLOWED_INTAKE_TYPES should contain all valid intake types."""
        assert ALLOWED_INTAKE_TYPES == {"requirement", "planning", "execution", "analysis"}

    def test_allowed_task_types_constant(self):
        """ALLOWED_TASK_TYPES should contain only executable task types."""
        assert ALLOWED_TASK_TYPES == {"planning", "execution", "analysis"}
        assert "requirement" not in ALLOWED_TASK_TYPES
