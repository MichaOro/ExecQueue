"""Validation models for REQ-020.

This module provides structured validation result types for the validator system.
Implements WP01: Interface Extension - structured results instead of boolean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ValidationStatus(str, Enum):
    """Validation result states for REQ-020.

    Status transitions:
    - PASSED: Validation succeeded, no issues detected
    - FAILED: Validation failed, critical issues found
    - REQUIRES_REVIEW: Validation passed but manual review recommended
    """

    PASSED = "passed"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"


@dataclass
class ValidationIssue:
    """Represents a single validation issue.

    Attributes:
        code: Issue code for categorization
        message: Human-readable description
        severity: Issue severity (critical, warning, info)
        field: Affected field/path (if applicable)
        details: Additional context
    """

    code: str
    message: str
    severity: str  # 'critical', 'warning', 'info'
    field: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class ValidationResult:
    """Structured validation result for REQ-020.

    Replaces simple boolean with structured data for:
    - Clear status transitions (PASSED/FAILED/REQUIRES_REVIEW)
    - Detailed issue reporting
    - Metrics and observability
    - Manual intervention support

    Attributes:
        status: Overall validation status
        validator_name: Name of the validator that produced this result
        passed: Boolean convenience property (status == PASSED)
        issues: List of validation issues found
        metadata: Additional context for observability
        validated_at: Timestamp of validation
    """

    status: ValidationStatus
    validator_name: str
    issues: list[ValidationIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def passed(self) -> bool:
        """Convenience property - True if validation passed."""
        return self.status == ValidationStatus.PASSED

    @property
    def failed(self) -> bool:
        """Convenience property - True if validation failed."""
        return self.status == ValidationStatus.FAILED

    @property
    def requires_review(self) -> bool:
        """Convenience property - True if manual review needed."""
        return self.status == ValidationStatus.REQUIRES_REVIEW

    @property
    def has_critical_issues(self) -> bool:
        """True if any critical issues were found."""
        return any(issue.severity == "critical" for issue in self.issues)

    @property
    def issue_count(self) -> int:
        """Total number of issues found."""
        return len(self.issues)

    def add_issue(
        self,
        code: str,
        message: str,
        severity: str = "warning",
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a validation issue.

        Args:
            code: Issue code for categorization
            message: Human-readable description
            severity: Issue severity (critical, warning, info)
            field: Affected field/path
            details: Additional context
        """
        self.issues.append(ValidationIssue(
            code=code,
            message=message,
            severity=severity,
            field=field,
            details=details,
        ))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the result
        """
        return {
            "status": self.status.value,
            "validator_name": self.validator_name,
            "passed": self.passed,
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity,
                    "field": issue.field,
                    "details": issue.details,
                }
                for issue in self.issues
            ],
            "metadata": self.metadata,
            "validated_at": self.validated_at.isoformat(),
        }
