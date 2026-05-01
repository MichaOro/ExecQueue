"""Smoke tests for the review module."""

from __future__ import annotations

from execqueue.review import LintIssue, run_ruff_check, run_ruff_format


def test_lint_issue_parsing_valid():
    """Test parsing a valid ruff output line."""
    line = "execqueue/review/__init__.py:10:5: RUF001: String contains ambiguous character"
    issue = LintIssue.from_ruff_output(line)
    assert issue is not None
    assert issue.file == "execqueue/review/__init__.py"
    assert issue.line == 10
    assert issue.column == 5
    assert issue.code == "RUF001"
    assert "ambiguous" in issue.message
    assert issue.severity == "info"


def test_lint_issue_parsing_invalid():
    """Test parsing an invalid ruff output line."""
    line = "this is not a valid ruff output"
    issue = LintIssue.from_ruff_output(line)
    assert issue is None


def test_run_ruff_check_module_exists():
    """Test that ruff check can be invoked on the review module."""
    issues, output = run_ruff_check(["execqueue/review/__init__.py"])
    # We expect this to run without crashing, even if issues are found
    assert isinstance(issues, list)
    assert isinstance(output, str)


def test_run_ruff_format_check():
    """Test that ruff format check can be invoked."""
    success, output = run_ruff_format(["execqueue/review/__init__.py"], check_only=True)
    # success may be True or False depending on formatting, but should not crash
    assert isinstance(success, bool)
    assert isinstance(output, str)
