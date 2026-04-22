import pytest
from execqueue.validation.task_validator import validate_task_result, TaskValidationResult


class TestValidateTaskResult:
    """Tests for validate_task_result function in task_validator."""

    def test_valid_json_status_done(self):
        """Test: Valid JSON with status='done' returns is_done=True."""
        raw_output = '{"status": "done", "summary": "Completed"}'

        result = validate_task_result(raw_output)

        assert result.is_done is True
        assert result.normalized_status == "done"
        assert result.summary == "Completed"
        assert result.raw_status == "done"

    def test_valid_json_status_not_done(self):
        """Test: Valid JSON with status='not_done' returns is_done=False."""
        raw_output = '{"status": "not_done", "summary": "Incomplete"}'

        result = validate_task_result(raw_output)

        assert result.is_done is False
        assert result.normalized_status == "not_done"
        assert result.summary == "Incomplete"
        assert result.raw_status == "not_done"

    def test_valid_json_missing_status_field(self):
        """Test: JSON without status field defaults to not_done."""
        raw_output = '{"summary": "Some text"}'

        result = validate_task_result(raw_output)

        assert result.is_done is False
        assert result.normalized_status == "not_done"
        assert result.summary == "Some text"
        assert result.raw_status is None

    def test_valid_json_empty_summary(self):
        """Test: JSON with empty summary uses default summary."""
        raw_output = '{"status": "done"}'

        result = validate_task_result(raw_output)

        assert result.is_done is True
        assert result.normalized_status == "done"
        assert result.summary == "Task marked as done."

    def test_invalid_json_with_done_marker(self):
        """Test: Invalid JSON with DONE marker triggers fallback."""
        raw_output = 'Some text\nDONE\nMore text'

        result = validate_task_result(raw_output)

        assert result.is_done is True
        assert result.normalized_status == "done"
        assert result.summary == "Fallback validator matched DONE marker."
        assert result.raw_status == "done"

    def test_invalid_json_without_marker(self):
        """Test: Invalid JSON without markers returns not_done."""
        raw_output = 'Plain text without markers'

        result = validate_task_result(raw_output)

        assert result.is_done is False
        assert result.normalized_status == "not_done"
        assert result.summary == "Result was not parseable as a valid done response."
        assert result.raw_status is None

    def test_empty_string_input(self):
        """Test: Empty string input returns not_done."""
        raw_output = ""

        result = validate_task_result(raw_output)

        assert result.is_done is False
        assert result.normalized_status == "not_done"

    def test_none_input(self):
        """Test: None input returns not_done."""
        raw_output = None

        result = validate_task_result(raw_output)

        assert result.is_done is False
        assert result.normalized_status == "not_done"

    def test_case_insensitive_done_marker(self):
        """Test: Case-insensitive DONE marker detection."""
        raw_output = '"STATUS": "DONE"'

        result = validate_task_result(raw_output)

        assert result.is_done is True
        assert result.normalized_status == "done"

    def test_case_variations_json_status(self):
        """Test: JSON status is case-insensitive."""
        raw_output = '{"status": "DONE"}'

        result = validate_task_result(raw_output)

        assert result.is_done is True
        assert result.normalized_status == "done"

    def test_json_with_extra_fields(self):
        """Test: JSON with additional fields is handled correctly."""
        raw_output = '{"status": "done", "summary": "Done", "extra": "field", "nested": {"key": "value"}}'

        result = validate_task_result(raw_output)

        assert result.is_done is True
        assert result.normalized_status == "done"
        assert result.summary == "Done"

    def test_json_with_whitespace(self):
        """Test: JSON with extra whitespace is handled correctly."""
        raw_output = '''
        {
            "status": "done",
            "summary": "Done with whitespace"
        }
        '''

        result = validate_task_result(raw_output)

        assert result.is_done is True
        assert result.normalized_status == "done"
        assert result.summary == "Done with whitespace"

    def test_json_not_done_with_extra_fields(self):
        """Test: JSON with status='not_done' and extra fields."""
        raw_output = '{"status": "not_done", "summary": "Failed", "error": "Something went wrong"}'

        result = validate_task_result(raw_output)

        assert result.is_done is False
        assert result.normalized_status == "not_done"
        assert result.summary == "Failed"
