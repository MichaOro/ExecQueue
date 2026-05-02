"""Tests for validation models (REQ-020/REQ-021 Section 4).

Tests for ValidationStatus, ValidationIssue, and ValidationResult.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from execqueue.runner.validation_models import (
    ValidationIssue,
    ValidationResult,
    ValidationStatus,
)


class TestValidationStatus:
    """Test ValidationStatus enum."""

    def test_status_values(self):
        """Test that status values are correct."""
        assert ValidationStatus.PASSED.value == "passed"
        assert ValidationStatus.FAILED.value == "failed"
        assert ValidationStatus.REQUIRES_REVIEW.value == "requires_review"

    def test_status_is_string_enum(self):
        """Test that ValidationStatus is a string enum."""
        assert isinstance(ValidationStatus.PASSED.value, str)
        assert isinstance(ValidationStatus.FAILED.value, str)
        assert isinstance(ValidationStatus.REQUIRES_REVIEW.value, str)


class TestValidationIssue:
    """Test ValidationIssue dataclass."""

    def test_minimal_issue(self):
        """Test creating a minimal issue."""
        issue = ValidationIssue(
            code="TEST_CODE",
            message="Test message",
            severity="warning",
        )
        assert issue.code == "TEST_CODE"
        assert issue.message == "Test message"
        assert issue.severity == "warning"
        assert issue.field is None
        assert issue.details is None

    def test_full_issue(self):
        """Test creating a full issue with all fields."""
        issue = ValidationIssue(
            code="TEST_CODE",
            message="Test message",
            severity="critical",
            field="some_field",
            details={"key": "value"},
        )
        assert issue.code == "TEST_CODE"
        assert issue.message == "Test message"
        assert issue.severity == "critical"
        assert issue.field == "some_field"
        assert issue.details == {"key": "value"}

    def test_issue_severity_levels(self):
        """Test different severity levels."""
        critical = ValidationIssue(code="C", message="Critical", severity="critical")
        warning = ValidationIssue(code="W", message="Warning", severity="warning")
        info = ValidationIssue(code="I", message="Info", severity="info")

        assert critical.severity == "critical"
        assert warning.severity == "warning"
        assert info.severity == "info"


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_minimal_result(self):
        """Test creating a minimal result."""
        result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_validator",
        )
        assert result.status == ValidationStatus.PASSED
        assert result.validator_name == "test_validator"
        assert result.passed is True
        assert result.failed is False
        assert result.requires_review is False
        assert len(result.issues) == 0
        assert result.issue_count == 0
        assert result.has_critical_issues is False
        assert result.validated_at is not None
        assert isinstance(result.validated_at, datetime)

    def test_passed_result(self):
        """Test a passed validation result."""
        result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_validator",
        )
        assert result.passed is True
        assert result.failed is False
        assert result.requires_review is False

    def test_failed_result(self):
        """Test a failed validation result."""
        result = ValidationResult(
            status=ValidationStatus.FAILED,
            validator_name="test_validator",
            issues=[
                ValidationIssue(
                    code="ERR_001",
                    message="Something went wrong",
                    severity="critical",
                )
            ],
        )
        assert result.passed is False
        assert result.failed is True
        assert result.requires_review is False
        assert result.issue_count == 1
        assert result.has_critical_issues is True

    def test_requires_review_result(self):
        """Test a requires_review validation result."""
        result = ValidationResult(
            status=ValidationStatus.REQUIRES_REVIEW,
            validator_name="test_validator",
            issues=[
                ValidationIssue(
                    code="REVIEW_001",
                    message="Manual review needed",
                    severity="warning",
                )
            ],
        )
        assert result.passed is False
        assert result.failed is False
        assert result.requires_review is True
        assert result.issue_count == 1
        assert result.has_critical_issues is False

    def test_add_issue(self):
        """Test adding issues to a result."""
        result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_validator",
        )
        assert result.issue_count == 0

        result.add_issue(
            code="WARN_001",
            message="Warning message",
            severity="warning",
            field="config.timeout",
            details={"current": 30, "recommended": 60},
        )

        assert result.issue_count == 1
        assert result.issues[0].code == "WARN_001"
        assert result.issues[0].field == "config.timeout"
        assert result.issues[0].details == {"current": 30, "recommended": 60}

    def test_multiple_issues(self):
        """Test result with multiple issues."""
        result = ValidationResult(
            status=ValidationStatus.FAILED,
            validator_name="test_validator",
            issues=[
                ValidationIssue(code="ERR_001", message="Error 1", severity="critical"),
                ValidationIssue(code="ERR_002", message="Error 2", severity="warning"),
                ValidationIssue(code="ERR_003", message="Error 3", severity="info"),
            ],
        )
        assert result.issue_count == 3
        assert result.has_critical_issues is True

    def test_no_critical_issues(self):
        """Test has_critical_issues with no critical issues."""
        result = ValidationResult(
            status=ValidationStatus.FAILED,
            validator_name="test_validator",
            issues=[
                ValidationIssue(code="WARN", message="Warning", severity="warning"),
                ValidationIssue(code="INFO", message="Info", severity="info"),
            ],
        )
        assert result.issue_count == 2
        assert result.has_critical_issues is False

    def test_to_dict_passed(self):
        """Test to_dict for a passed result."""
        result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_validator",
            metadata={"key": "value"},
        )
        d = result.to_dict()
        assert d["status"] == "passed"
        assert d["validator_name"] == "test_validator"
        assert d["passed"] is True
        assert d["issues"] == []
        assert d["metadata"] == {"key": "value"}
        assert "validated_at" in d

    def test_to_dict_with_issues(self):
        """Test to_dict with issues."""
        result = ValidationResult(
            status=ValidationStatus.FAILED,
            validator_name="test_validator",
            issues=[
                ValidationIssue(
                    code="ERR",
                    message="Error",
                    severity="critical",
                    field="test",
                    details={"detail": "value"},
                )
            ],
        )
        d = result.to_dict()
        assert d["status"] == "failed"
        assert len(d["issues"]) == 1
        issue = d["issues"][0]
        assert issue["code"] == "ERR"
        assert issue["message"] == "Error"
        assert issue["severity"] == "critical"
        assert issue["field"] == "test"
        assert issue["details"] == {"detail": "value"}

    def test_validated_at_timestamp(self):
        """Test that validated_at is set on creation."""
        before = datetime.now(timezone.utc)
        result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_validator",
        )
        after = datetime.now(timezone.utc)

        assert before <= result.validated_at <= after

    def test_metadata_default(self):
        """Test that metadata defaults to empty dict."""
        result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_validator",
        )
        assert result.metadata == {}

    def test_metadata_custom(self):
        """Test custom metadata."""
        result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_validator",
            metadata={"call_count": 5, "duration_ms": 123},
        )
        assert result.metadata["call_count"] == 5
        assert result.metadata["duration_ms"] == 123