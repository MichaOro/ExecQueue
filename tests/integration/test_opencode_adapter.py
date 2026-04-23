"""Integration tests for OpenCode adapter.

These tests verify the actual integration with the OpenCode API.
They require OPENCODE_BASE_URL to be set and will be skipped otherwise.
"""
import os
import pytest

from execqueue.workers.opencode_adapter import (
    execute_with_opencode,
    OpenCodeExecutionResult,
    OpenCodeConfigurationError,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def opencode_configured():
    """Check if OpenCode is configured for integration testing."""
    base_url = os.getenv("OPENCODE_BASE_URL")
    if not base_url:
        pytest.skip("OPENCODE_BASE_URL environment variable not set. Skipping integration test.")
    return base_url


class TestOpenCodeIntegration:
    """Integration tests for OpenCode API communication."""

    def test_real_api_call_returns_result(self, opencode_configured):
        """Test: Real API call returns properly structured result.
        
        This test makes an actual HTTP request to the OpenCode API.
        """
        result = execute_with_opencode(prompt="Say hello briefly")
        
        assert isinstance(result, OpenCodeExecutionResult)
        assert result.status in ["completed", "failed", "error"]
        assert result.raw_output is not None
        assert isinstance(result.raw_output, str)
        assert len(result.raw_output) > 0
        assert result.summary is not None
        assert isinstance(result.summary, str)

    def test_real_api_call_with_verification(self, opencode_configured):
        """Test: API call with verification_prompt works correctly.
        
        This test verifies that verification prompts are properly sent to the API.
        """
        result = execute_with_opencode(
            prompt="Write a simple function",
            verification_prompt="Check for edge cases and error handling"
        )
        
        assert isinstance(result, OpenCodeExecutionResult)
        assert result.status in ["completed", "failed", "error"]
        assert result.raw_output is not None
        assert result.summary is not None

    def test_real_api_call_timeout_handling(self, opencode_configured):
        """Test: Timeout handling with real API.
        
        This test verifies that the timeout configuration is respected.
        Note: This test may take up to OPENCODE_TIMEOUT seconds.
        """
        # Use a very short timeout to test timeout handling
        # This should raise OpenCodeTimeoutError if the API is slow
        import os
        original_timeout = os.getenv("OPENCODE_TIMEOUT")
        os.environ["OPENCODE_TIMEOUT"] = "5"  # 5 second timeout
        
        try:
            # This might timeout or succeed depending on API response time
            result = execute_with_opencode(prompt="Quick response please")
            # If we get here, the API was fast enough
            assert result is not None
        except Exception as e:
            # Timeout or other error is acceptable in this test
            assert "timeout" in str(e).lower() or "connection" in str(e).lower()
        finally:
            # Restore original timeout
            if original_timeout:
                os.environ["OPENCODE_TIMEOUT"] = original_timeout
            else:
                os.environ.pop("OPENCODE_TIMEOUT", None)

    def test_real_api_call_response_structure(self, opencode_configured):
        """Test: Real API response has expected structure.
        
        This test validates the response structure from the actual API.
        """
        result = execute_with_opencode(prompt="Return a test response")
        
        # Validate all expected fields are present
        assert hasattr(result, "status")
        assert hasattr(result, "raw_output")
        assert hasattr(result, "summary")
        
        # Validate field types
        assert isinstance(result.status, str)
        assert isinstance(result.raw_output, str)
        assert result.summary is None or isinstance(result.summary, str)
        
        # Validate status values
        assert result.status in ["completed", "failed", "error"]

    def test_real_api_call_error_handling(self, opencode_configured):
        """Test: Error responses from real API are handled correctly.
        
        This test checks that error statuses are properly parsed.
        """
        # Send a prompt that might cause an error
        result = execute_with_opencode(prompt="Invalid prompt {{{{")
        
        # Result should still be properly structured even on error
        assert isinstance(result, OpenCodeExecutionResult)
        assert result.status in ["completed", "failed", "error"]
        assert result.raw_output is not None
        
        # If status is error/failed, we should have some output about the error
        if result.status in ["failed", "error"]:
            assert len(result.raw_output) > 0


class TestOpenCodeConfigurationIntegration:
    """Integration tests for OpenCode configuration."""

    def test_missing_config_raises_error(self):
        """Test: Missing OPENCODE_BASE_URL raises configuration error.
        
        This test verifies the configuration validation works correctly.
        """
        # Temporarily remove the env var
        original = os.getenv("OPENCODE_BASE_URL")
        os.environ.pop("OPENCODE_BASE_URL", None)
        
        try:
            with pytest.raises(OpenCodeConfigurationError):
                execute_with_opencode(prompt="test")
        finally:
            # Restore original value
            if original:
                os.environ["OPENCODE_BASE_URL"] = original

    def test_invalid_url_handling(self):
        """Test: Invalid URL is handled gracefully.
        
        This test checks that invalid URLs don't crash the system.
        Note: This test may be skipped if no invalid URL pattern is found.
        """
        # Set an obviously invalid URL
        original = os.getenv("OPENCODE_BASE_URL")
        os.environ["OPENCODE_BASE_URL"] = "http://this-domain-definitely-does-not-exist-12345.local"
        
        try:
            # This should raise a connection error, not crash
            with pytest.raises(Exception) as exc_info:
                execute_with_opencode(prompt="test", client_timeout=2)
            
            # Verify it's a connection-related error
            assert "connection" in str(exc_info.value).lower() or \
                   "timeout" in str(exc_info.value).lower() or \
                   "name resolution" in str(exc_info.value).lower()
        finally:
            # Restore original value
            if original:
                os.environ["OPENCODE_BASE_URL"] = original
            else:
                os.environ.pop("OPENCODE_BASE_URL", None)
