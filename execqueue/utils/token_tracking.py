"""Token usage tracking utilities for REQ-013.

This module provides utilities for extracting and handling token usage
data from AI provider responses.
"""

from __future__ import annotations

from typing import Any


def extract_total_tokens(usage_data: dict[str, Any] | None) -> int | None:
    """Extract total token count from provider usage data.

    This function handles various provider response formats and extracts
    the total token count. It returns None if no valid token data is found.

    Args:
        usage_data: Usage data from provider response, typically containing
                   fields like 'total_tokens', 'input_tokens', 'output_tokens'

    Returns:
        Total token count if available, None otherwise

    Examples:
        >>> extract_total_tokens({"total_tokens": 150})
        150
        >>> extract_total_tokens({"input_tokens": 100, "output_tokens": 50})
        150
        >>> extract_total_tokens(None)
        None
        >>> extract_total_tokens({})
        None
    """
    if usage_data is None:
        return None

    if not isinstance(usage_data, dict):
        return None

    # Try direct total_tokens first (most common format)
    if "total_tokens" in usage_data:
        value = usage_data["total_tokens"]
        if isinstance(value, int):
            return value
        # Handle string numbers
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    # Try summing input and output tokens (alternative format)
    if "input_tokens" in usage_data and "output_tokens" in usage_data:
        input_tokens = usage_data["input_tokens"]
        output_tokens = usage_data["output_tokens"]

        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            return input_tokens + output_tokens

        # Handle string numbers
        if isinstance(input_tokens, str) and isinstance(output_tokens, str):
            if input_tokens.isdigit() and output_tokens.isdigit():
                return int(input_tokens) + int(output_tokens)

        # Mixed types
        if isinstance(input_tokens, int) and isinstance(output_tokens, str):
            if output_tokens.isdigit():
                return input_tokens + int(output_tokens)

        if isinstance(input_tokens, str) and isinstance(output_tokens, int):
            if input_tokens.isdigit():
                return int(input_tokens) + output_tokens

        return None

    # Try alternative field names (provider-specific)
    for field in ["prompt_tokens", "completion_tokens", "totalTokens", "usage"]:
        if field in usage_data:
            value = usage_data[field]
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)

    return None


def extract_token_usage(
    response_data: dict[str, Any] | None,
) -> dict[str, int | None]:
    """Extract structured token usage from provider response.

    Args:
        response_data: Full provider response data

    Returns:
        Dictionary with extracted token metrics:
        - total_tokens: Total token count
        - input_tokens: Input/prompt token count (if available)
        - output_tokens: Output/completion token count (if available)
    """
    result = {
        "total_tokens": None,
        "input_tokens": None,
        "output_tokens": None,
    }

    if response_data is None:
        return result

    usage = response_data.get("usage") or response_data.get("token_usage")
    if not isinstance(usage, dict):
        return result

    # Extract total tokens
    result["total_tokens"] = extract_total_tokens(usage)

    # Extract input tokens
    if "input_tokens" in usage:
        val = usage["input_tokens"]
        if isinstance(val, int):
            result["input_tokens"] = val
        elif isinstance(val, str) and val.isdigit():
            result["input_tokens"] = int(val)

    # Extract output tokens
    if "output_tokens" in usage:
        val = usage["output_tokens"]
        if isinstance(val, int):
            result["output_tokens"] = val
        elif isinstance(val, str) and val.isdigit():
            result["output_tokens"] = int(val)

    # Alternative field names
    if result["input_tokens"] is None and "prompt_tokens" in usage:
        val = usage["prompt_tokens"]
        if isinstance(val, int):
            result["input_tokens"] = val

    if result["output_tokens"] is None and "completion_tokens" in usage:
        val = usage["completion_tokens"]
        if isinstance(val, int):
            result["output_tokens"] = val

    return result
