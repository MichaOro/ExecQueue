"""Batch specification for REQ-016 workflow execution.

This module defines the BatchSpec dataclass that specifies execution parameters
for batches, including size limits, timeouts, and rollback strategies.

See REQ-016 Section 7 for batch definition specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta


@dataclass(frozen=True)
class BatchSpec:
    """Specification for batch execution parameters.

    This dataclass defines the execution constraints and behaviors for a batch
    of tasks. It is used by the scheduler to enforce resource limits and
    failure handling strategies.

    Attributes:
        max_size: Maximum number of tasks in the batch (default: 10)
        timeout: Maximum execution time for the entire batch (default: 30 minutes)
        rollback_on_failure: Whether to rollback all changes if any task fails
        continue_on_partial_failure: Whether to continue remaining tasks if one fails
        retry_on_transient_error: Whether to retry transient errors automatically
        max_retries: Maximum retry attempts per task (default: 3)
        retry_delay_seconds: Delay between retries in seconds (default: 5)
        parallelism_limit: Maximum concurrent tasks within batch (default: 5)
        priority: Batch priority level (0-10, higher = more urgent, default: 5)
        metadata: Additional batch metadata for observability
    """

    max_size: int = 10
    timeout: timedelta = field(default_factory=lambda: timedelta(minutes=30))
    rollback_on_failure: bool = True
    continue_on_partial_failure: bool = False
    retry_on_transient_error: bool = True
    max_retries: int = 3
    retry_delay_seconds: int = 5
    parallelism_limit: int = 5
    priority: int = 5
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate batch spec constraints."""
        if self.max_size < 1:
            raise ValueError("max_size must be at least 1")
        if self.max_size > 100:
            raise ValueError("max_size must not exceed 100")
        if self.priority < 0 or self.priority > 10:
            raise ValueError("priority must be between 0 and 10")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")
        if self.parallelism_limit < 1:
            raise ValueError("parallelism_limit must be at least 1")
        if self.parallelism_limit > self.max_size:
            raise ValueError("parallelism_limit must not exceed max_size")

    @property
    def timeout_seconds(self) -> int:
        """Get timeout as seconds."""
        return int(self.timeout.total_seconds())

    @classmethod
    def default(cls) -> "BatchSpec":
        """Create a BatchSpec with default values.

        Returns:
            BatchSpec with conservative defaults for production use.
        """
        return cls()

    @classmethod
    def aggressive(cls) -> "BatchSpec":
        """Create a BatchSpec for aggressive parallel execution.

        Use with caution - suited for read-only or isolated tasks.

        Returns:
            BatchSpec optimized for maximum parallelism.
        """
        return cls(
            max_size=50,
            timeout=timedelta(minutes=60),
            rollback_on_failure=False,
            continue_on_partial_failure=True,
            retry_on_transient_error=True,
            max_retries=2,
            retry_delay_seconds=2,
            parallelism_limit=20,
            priority=7,
        )

    @classmethod
    def conservative(cls) -> "BatchSpec":
        """Create a BatchSpec for conservative sequential execution.

        Use for write-heavy or high-risk operations.

        Returns:
            BatchSpec with conservative settings for safety.
        """
        return cls(
            max_size=1,
            timeout=timedelta(minutes=15),
            rollback_on_failure=True,
            continue_on_partial_failure=False,
            retry_on_transient_error=True,
            max_retries=5,
            retry_delay_seconds=10,
            parallelism_limit=1,
            priority=3,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "max_size": self.max_size,
            "timeout_seconds": self.timeout_seconds,
            "rollback_on_failure": self.rollback_on_failure,
            "continue_on_partial_failure": self.continue_on_partial_failure,
            "retry_on_transient_error": self.retry_on_transient_error,
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "parallelism_limit": self.parallelism_limit,
            "priority": self.priority,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BatchSpec":
        """Create BatchSpec from dictionary.

        Args:
            data: Dictionary with batch spec fields.

        Returns:
            BatchSpec instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        timeout_seconds = data.get("timeout_seconds", 1800)
        return cls(
            max_size=data.get("max_size", 10),
            timeout=timedelta(seconds=timeout_seconds),
            rollback_on_failure=data.get("rollback_on_failure", True),
            continue_on_partial_failure=data.get("continue_on_partial_failure", False),
            retry_on_transient_error=data.get("retry_on_transient_error", True),
            max_retries=data.get("max_retries", 3),
            retry_delay_seconds=data.get("retry_delay_seconds", 5),
            parallelism_limit=data.get("parallelism_limit", 5),
            priority=data.get("priority", 5),
            metadata=data.get("metadata", {}),
        )
