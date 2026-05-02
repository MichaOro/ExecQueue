"""Write task validator for REQ-021.

This module provides a validator that checks whether write tasks have produced
valid code changes that can be safely adopted.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from execqueue.models.task_execution import TaskExecution
from execqueue.runner.validation_models import (
    ValidationIssue,
    ValidationStatus,
    ValidationResult,
)
from execqueue.runner.validator import Validator

if TYPE_CHECKING:
    from execqueue.models.task import Task

logger = logging.getLogger(__name__)


class WriteTaskValidator(Validator):
    """Validator for write tasks that checks code quality and safety.

    This validator checks:
    - Whether the task actually wrote files (not just read or planned)
    - Whether the written code compiles/runs (language-specific)
    - Whether there are any obvious security issues
    - Whether the changes are reasonable in size
    """

    def __init__(
        self,
        validator_name: str = "write_task_validator",
        check_compilation: bool = True,
        max_file_size_kb: int = 1024,  # 1MB max per file
        max_total_changes_kb: int = 10240,  # 10MB max total
    ):
        """Initialize the write task validator.

        Args:
            validator_name: Name for the validator
            check_compilation: Whether to check code compilation
            max_file_size_kb: Maximum size per file in KB
            max_total_changes_kb: Maximum total changes in KB
        """
        self.validator_name = validator_name
        self.check_compilation = check_compilation
        self.max_file_size_kb = max_file_size_kb
        self.max_total_changes_kb = max_total_changes_kb
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return the number of times validate() has been called."""
        return self._call_count

    async def validate(self, execution: TaskExecution) -> ValidationResult:
        """Validate a write task execution.

        Args:
            execution: The TaskExecution to validate

        Returns:
            ValidationResult with validation status and issues
        """
        self._call_count += 1
        logger.debug(
            f"WriteTaskValidator.validate() called (call #{self._call_count})"
        )

        result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name=self.validator_name,
            metadata={
                "call_count": self._call_count,
                "execution_id": str(execution.id),
                "task_id": str(execution.task_id),
            },
        )

        # Check if this is actually a write task
        if not await self._is_write_task(execution):
            logger.debug("Task is not a write task, skipping validation")
            return result

        # Check if worktree path is available
        if not execution.worktree_path:
            result.status = ValidationStatus.FAILED
            result.add_issue(
                code="MISSING_WORKTREE_PATH",
                message="No worktree path available for write task validation",
                severity="critical",
            )
            return result

        worktree_path = Path(execution.worktree_path)

        # Check for changes
        changes = await self._get_changed_files(worktree_path)
        if not changes:
            result.status = ValidationStatus.FAILED
            result.add_issue(
                code="NO_CHANGES",
                message="Write task produced no file changes",
                severity="critical",
            )
            return result

        # Check file sizes
        oversized_files = await self._check_file_sizes(worktree_path, changes)
        for file_path, size_kb in oversized_files:
            result.add_issue(
                code="OVERSIZED_FILE",
                message=f"File {file_path} is {size_kb}KB, exceeding limit of {self.max_file_size_kb}KB",
                severity="warning",
                field=str(file_path),
                details={"size_kb": size_kb, "limit_kb": self.max_file_size_kb},
            )

        # Check total changes size
        total_size_kb = sum(size for _, size in oversized_files) if oversized_files else 0
        if total_size_kb > self.max_total_changes_kb:
            result.add_issue(
                code="TOTAL_SIZE_EXCEEDED",
                message=f"Total changes {total_size_kb}KB exceed limit of {self.max_total_changes_kb}KB",
                severity="warning",
                details={"size_kb": total_size_kb, "limit_kb": self.max_total_changes_kb},
            )

        # Check for potentially dangerous patterns
        dangerous_patterns = await self._check_dangerous_patterns(worktree_path, changes)
        for file_path, patterns in dangerous_patterns.items():
            for pattern in patterns:
                result.add_issue(
                    code="DANGEROUS_PATTERN",
                    message=f"Dangerous pattern '{pattern}' found in {file_path}",
                    severity="warning" if "rm -rf" not in pattern else "critical",
                    field=str(file_path),
                    details={"pattern": pattern},
                )

        # Check compilation if enabled
        if self.check_compilation and result.status == ValidationStatus.PASSED:
            compilation_issues = await self._check_compilation(worktree_path, changes)
            for issue in compilation_issues:
                result.add_issue(**issue.__dict__)

        # Update status based on issues
        if result.has_critical_issues:
            result.status = ValidationStatus.FAILED
        elif any(issue.severity == "warning" for issue in result.issues):
            result.status = ValidationStatus.REQUIRES_REVIEW

        logger.debug(
            f"WriteTaskValidator completed: {result.status.value} with {result.issue_count} issues"
        )

        return result

    async def _is_write_task(self, execution: TaskExecution) -> bool:
        """Check if this execution represents a write task.

        Args:
            execution: Task execution to check

        Returns:
            True if this is a write task
        """
        # For now, we'll assume all tasks that reach this validator are write tasks
        # In a real implementation, this would check the task type or metadata
        return True

    async def _get_changed_files(self, worktree_path: Path) -> list[str]:
        """Get list of changed files in the worktree.

        Args:
            worktree_path: Path to the worktree

        Returns:
            List of changed file paths
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to get git status: {result.stderr}")
                return []

            # Parse git status output
            changed_files = []
            for line in result.stdout.splitlines():
                if line.startswith((" M ", " A ", " D ", " R ")):
                    # Modified, Added, Deleted, Renamed
                    parts = line.split()
                    if len(parts) >= 2:
                        changed_files.append(parts[-1])

            return changed_files
        except Exception as e:
            logger.error(f"Error getting changed files: {e}")
            return []

    async def _check_file_sizes(self, worktree_path: Path, files: list[str]) -> list[tuple[str, int]]:
        """Check if any files exceed size limits.

        Args:
            worktree_path: Path to the worktree
            files: List of file paths to check

        Returns:
            List of (file_path, size_in_kb) tuples for oversized files
        """
        oversized = []
        for file_path in files:
            full_path = worktree_path / file_path
            try:
                if full_path.is_file():
                    size_bytes = full_path.stat().st_size
                    size_kb = size_bytes / 1024
                    if size_kb > self.max_file_size_kb:
                        oversized.append((file_path, int(size_kb)))
            except Exception as e:
                logger.warning(f"Could not check size of {file_path}: {e}")

        return oversized

    async def _check_dangerous_patterns(self, worktree_path: Path, files: list[str]) -> dict[str, list[str]]:
        """Check for potentially dangerous code patterns.

        Args:
            worktree_path: Path to the worktree
            files: List of file paths to check

        Returns:
            Dict mapping file paths to lists of dangerous patterns found
        """
        dangerous_patterns = {
            "rm -rf /": "System deletion",
            "chmod 777": "Overly permissive permissions",
            "eval(": "Dynamic code execution",
            "exec(": "Dynamic code execution",
            "__import__": "Dynamic imports",
        }

        findings = {}
        for file_path in files:
            full_path = worktree_path / file_path
            if not full_path.is_file():
                continue

            try:
                content = full_path.read_text(encoding='utf-8', errors='ignore')
                found_patterns = []
                for pattern, description in dangerous_patterns.items():
                    if pattern in content:
                        found_patterns.append(pattern)

                if found_patterns:
                    findings[file_path] = found_patterns
            except Exception as e:
                logger.warning(f"Could not read {file_path}: {e}")

        return findings

    async def _check_compilation(self, worktree_path: Path, files: list[str]) -> list[ValidationIssue]:
        """Check if code compiles correctly.

        Args:
            worktree_path: Path to the worktree
            files: List of changed files

        Returns:
            List of validation issues found during compilation check
        """
        issues = []

        # Group files by extension
        files_by_extension = {}
        for file_path in files:
            ext = Path(file_path).suffix.lower()
            if ext not in files_by_extension:
                files_by_extension[ext] = []
            files_by_extension[ext].append(file_path)

        # Check Python files
        if ".py" in files_by_extension:
            python_issues = await self._check_python_compilation(worktree_path, files_by_extension[".py"])
            issues.extend(python_issues)

        # Check JavaScript files
        if ".js" in files_by_extension:
            js_issues = await self._check_javascript_compilation(worktree_path, files_by_extension[".js"])
            issues.extend(js_issues)

        return issues

    async def _check_python_compilation(self, worktree_path: Path, files: list[str]) -> list[ValidationIssue]:
        """Check if Python files compile correctly.

        Args:
            worktree_path: Path to the worktree
            files: List of Python file paths

        Returns:
            List of validation issues found during compilation check
        """
        issues = []
        for file_path in files:
            full_path = worktree_path / file_path
            if not full_path.is_file():
                continue

            try:
                # Compile the Python file to check for syntax errors
                with open(full_path, 'r', encoding='utf-8') as f:
                    source = f.read()
                
                compile(source, str(full_path), 'exec')
            except SyntaxError as e:
                issues.append(
                    ValidationIssue(
                        code="PYTHON_SYNTAX_ERROR",
                        message=f"Syntax error in {file_path}: {e.msg} at line {e.lineno}",
                        severity="critical",
                        field=file_path,
                        details={
                            "error_type": "SyntaxError",
                            "line": e.lineno,
                            "message": e.msg,
                        },
                    )
                )
            except Exception as e:
                issues.append(
                    ValidationIssue(
                        code="PYTHON_COMPILATION_ERROR",
                        message=f"Compilation error in {file_path}: {str(e)}",
                        severity="warning",
                        field=file_path,
                        details={
                            "error_type": type(e).__name__,
                            "message": str(e),
                        },
                    )
                )

        return issues

    async def _check_javascript_compilation(self, worktree_path: Path, files: list[str]) -> list[ValidationIssue]:
        """Check if JavaScript files compile correctly (basic syntax check).

        Args:
            worktree_path: Path to the worktree
            files: List of JavaScript file paths

        Returns:
            List of validation issues found during compilation check
        """
        # For now, we'll just do a basic existence check
        # A more sophisticated implementation would use a JS parser or linter
        issues = []
        
        # This is a placeholder - in a real implementation, you'd use something like:
        # - ESLint for linting
        # - Babel for syntax checking
        # - Node.js to actually parse the files
        
        logger.debug(f"JS compilation check skipped for {len(files)} files (not implemented)")
        
        return issues