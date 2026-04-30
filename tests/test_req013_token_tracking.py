"""Tests for REQ-013 token tracking utilities."""

from __future__ import annotations

import pytest

from execqueue.utils.token_tracking import extract_total_tokens, extract_token_usage


class TestExtractTotalTokens:
    """Tests for the extract_total_tokens function."""

    def test_none_input_returns_none(self):
        """Test that None input returns None."""
        assert extract_total_tokens(None) is None

    def test_empty_dict_returns_none(self):
        """Test that empty dict returns None."""
        assert extract_total_tokens({}) is None

    def test_direct_total_tokens(self):
        """Test extraction of direct total_tokens field."""
        assert extract_total_tokens({"total_tokens": 150}) == 150

    def test_total_tokens_as_string(self):
        """Test extraction of total_tokens as string number."""
        assert extract_total_tokens({"total_tokens": "150"}) == 150

    def test_total_tokens_invalid_string(self):
        """Test that invalid string returns None."""
        assert extract_total_tokens({"total_tokens": "invalid"}) is None

    def test_input_and_output_tokens_sum(self):
        """Test extraction from input_tokens + output_tokens."""
        assert extract_total_tokens({"input_tokens": 100, "output_tokens": 50}) == 150

    def test_input_and_output_tokens_as_strings(self):
        """Test extraction when both are strings."""
        assert extract_total_tokens({"input_tokens": "100", "output_tokens": "50"}) == 150

    def test_input_and_output_tokens_mixed_types(self):
        """Test extraction with mixed int/string types."""
        assert extract_total_tokens({"input_tokens": 100, "output_tokens": "50"}) == 150
        assert extract_total_tokens({"input_tokens": "100", "output_tokens": 50}) == 150

    def test_input_and_output_tokens_invalid(self):
        """Test that invalid values return None."""
        assert extract_total_tokens({"input_tokens": "abc", "output_tokens": 50}) is None

    def test_prefers_total_tokens_over_sum(self):
        """Test that total_tokens takes precedence over input+output sum."""
        data = {"total_tokens": 200, "input_tokens": 100, "output_tokens": 50}
        assert extract_total_tokens(data) == 200

    def test_non_dict_input_returns_none(self):
        """Test that non-dict input returns None."""
        assert extract_total_tokens("invalid") is None
        assert extract_total_tokens(123) is None
        assert extract_total_tokens([]) is None

    def test_alternative_field_total_tokens(self):
        """Test extraction from alternative field names."""
        assert extract_total_tokens({"totalTokens": 150}) == 150

    def test_prompt_completion_tokens(self):
        """Test extraction from prompt_tokens and completion_tokens."""
        # Note: These are only checked when total_tokens is not present
        result = extract_total_tokens({"prompt_tokens": 100})
        assert result == 100

    def test_large_token_values(self):
        """Test that large token values work correctly."""
        assert extract_total_tokens({"total_tokens": 10_000_000}) == 10_000_000

    def test_zero_tokens(self):
        """Test that zero is a valid token value."""
        assert extract_total_tokens({"total_tokens": 0}) == 0


class TestExtractTokenUsage:
    """Tests for the extract_token_usage function."""

    def test_none_input_returns_all_none(self):
        """Test that None input returns dict with all None values."""
        result = extract_token_usage(None)
        assert result == {"total_tokens": None, "input_tokens": None, "output_tokens": None}

    def test_empty_response_returns_all_none(self):
        """Test that empty response returns dict with all None values."""
        result = extract_token_usage({})
        assert result == {"total_tokens": None, "input_tokens": None, "output_tokens": None}

    def test_extract_usage_nested(self):
        """Test extraction from nested usage field."""
        response = {"usage": {"total_tokens": 150, "input_tokens": 100, "output_tokens": 50}}
        result = extract_token_usage(response)
        assert result["total_tokens"] == 150
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50

    def test_extract_token_usage_nested(self):
        """Test extraction from nested token_usage field."""
        response = {"token_usage": {"total_tokens": 200}}
        result = extract_token_usage(response)
        assert result["total_tokens"] == 200

    def test_extract_with_alternative_fields(self):
        """Test extraction with prompt_tokens and completion_tokens."""
        response = {"usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        result = extract_token_usage(response)
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50

    def test_only_total_tokens(self):
        """Test extraction when only total_tokens is available."""
        response = {"usage": {"total_tokens": 150}}
        result = extract_token_usage(response)
        assert result["total_tokens"] == 150
        assert result["input_tokens"] is None
        assert result["output_tokens"] is None

    def test_invalid_usage_field(self):
        """Test handling of invalid usage field type."""
        response = {"usage": "invalid"}
        result = extract_token_usage(response)
        assert result == {"total_tokens": None, "input_tokens": None, "output_tokens": None}
