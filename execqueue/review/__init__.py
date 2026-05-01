"""
ExecQueue Review Module.

Provides linting and code quality utilities for the technical-requirements-engineer-task.
This module is in bootstrap stage and may be extended with additional checks.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class LintIssue:
    """Represents a single lint issue found by ruff."""

    file: str
    line: int
    column: int
    code: str
    message: str
    severity: str  # "error", "warning", or "info"

    @classmethod
    def from_ruff_output(cls, line: str) -> "LintIssue | None":
        """Parse a ruff output line into a LintIssue."""
        # Expected format: file:line:column: code: message
        parts = line.split(":", maxsplit=3)
        if len(parts) < 4:
            return None

        file_path = parts[0]
        try:
            line_num = int(parts[1])
            column_num = int(parts[2])
        except ValueError:
            return None

        rest = parts[3].strip()
        # Split code and message (format: "CODE: message")
        code_msg = rest.split(":", maxsplit=1)
        if len(code_msg) < 2:
            return None

        code = code_msg[0].strip()
        message = code_msg[1].strip()

        # Determine severity based on code prefix
        if code.startswith("E") or code.startswith("F") or code.startswith("W"):
            severity = "error"
        elif code.startswith("N") or code.startswith("I"):
            severity = "warning"
        else:
            severity = "info"

        return cls(
            file=file_path,
            line=line_num,
            column=column_num,
            code=code,
            message=message,
            severity=severity,
        )


def run_ruff_check(file_paths: List[str], fix: bool = False) -> tuple[List[LintIssue], str]:
    """
    Run ruff check on the given file paths.

    Args:
        file_paths: List of file paths to check.
        fix: If True, attempt to auto-fix issues.

    Returns:
        A tuple of (list of LintIssue objects, raw output string).
    """
    cmd = [sys.executable, "-m", "ruff", "check"]
    if fix:
        cmd.append("--fix")
    cmd.extend(file_paths)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,  # ruff returns non-zero if issues are found
        )
        output = result.stdout + result.stderr
        issues = []
        for line in output.strip().split("\n"):
            if line and ":" in line:
                issue = LintIssue.from_ruff_output(line)
                if issue:
                    issues.append(issue)
        return issues, output
    except FileNotFoundError:
        return [], "ruff not found. Install with: pip install ruff"
    except Exception as e:
        return [], f"Error running ruff: {e}"


def run_ruff_format(file_paths: List[str], check_only: bool = False) -> tuple[bool, str]:
    """
    Run ruff format on the given file paths.

    Args:
        file_paths: List of file paths to format.
        check_only: If True, only check formatting without modifying files.

    Returns:
        A tuple of (success flag, raw output string).
    """
    cmd = [sys.executable, "-m", "ruff", "format"]
    if check_only:
        cmd.append("--check")
    cmd.extend(file_paths)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        return success, output
    except FileNotFoundError:
        return False, "ruff not found. Install with: pip install ruff"
    except Exception as e:
        return False, f"Error running ruff format: {e}"


__all__ = ["LintIssue", "run_ruff_check", "run_ruff_format"]
