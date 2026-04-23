"""
OpenCode Adapter - Production-ready integration with OpenCode Execution Engine.

This module provides a robust HTTP client for communicating with the OpenCode API,
including retry logic with exponential backoff, timeout handling, and comprehensive logging.

Configuration:
    OPENCODE_BASE_URL (required): Base URL of the OpenCode API (e.g., http://localhost:8000)
    OPENCODE_TIMEOUT (default: 120): Timeout in seconds for API requests
    OPENCODE_MAX_RETRIES (default: 3): Number of retries for network errors

API Specification:
    Request: POST {base_url}/execute
    Body: {
        "prompt": str,
        "verification_prompt": str | None
    }
    
    Response: {
        "status": "completed" | "failed",
        "output": str,
        "summary": str
    }

Example:
    >>> from execqueue.workers.opencode_adapter import execute_with_opencode
    >>> result = execute_with_opencode(
    ...     prompt="Implement a function that adds two numbers",
    ...     verification_prompt="Verify the function handles edge cases"
    ... )
    >>> print(result.summary)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from execqueue.runtime import (
    get_opencode_base_url,
    get_opencode_timeout,
    get_opencode_max_retries,
)

logger = logging.getLogger(__name__)


class OpenCodeError(Exception):
    """Base exception for OpenCode-related errors."""
    pass


class OpenCodeTimeoutError(OpenCodeError):
    """Raised when OpenCode API request times out."""
    pass


class OpenCodeConnectionError(OpenCodeError):
    """Raised when connection to OpenCode API fails."""
    pass


class OpenCodeHTTPError(OpenCodeError):
    """Raised when OpenCode API returns an error response."""
    
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class OpenCodeConfigurationError(OpenCodeError):
    """Raised when OpenCode is not properly configured."""
    pass


@dataclass
class OpenCodeExecutionResult:
    """Result of an OpenCode execution."""
    status: str  # raw/external status, not trusted as final truth
    raw_output: str
    summary: Optional[str] = None


class OpenCodeClient:
    """
    HTTP client for communicating with the OpenCode API.
    
    Features:
    - Retry logic with exponential backoff for transient errors
    - Timeout handling
    - Comprehensive logging
    - Type-safe response parsing
    
    Args:
        base_url: Base URL of the OpenCode API
        timeout: Timeout in seconds for API requests
        max_retries: Maximum number of retries for transient errors
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 120,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.Client(timeout=timeout)
    
    def execute(
        self,
        prompt: str,
        verification_prompt: Optional[str] = None,
    ) -> OpenCodeExecutionResult:
        """
        Execute a prompt via the OpenCode API.
        
        Args:
            prompt: The main prompt to execute
            verification_prompt: Optional verification prompt
            
        Returns:
            OpenCodeExecutionResult with status, raw_output, and summary
            
        Raises:
            OpenCodeConfigurationError: If base_url is not configured
            OpenCodeTimeoutError: If request times out after all retries
            OpenCodeConnectionError: If connection fails after all retries
            OpenCodeHTTPError: If API returns 4xx error
        """
        url = f"{self.base_url}/execute"
        
        request_payload = {
            "prompt": prompt,
            "verification_prompt": verification_prompt,
        }
        
        logger.info(
            "Starting OpenCode execution: prompt_length=%d, verification=%s, timeout=%ds",
            len(prompt),
            "present" if verification_prompt else "none",
            self.timeout,
        )
        
        last_exception: Exception | None = None
        
        for attempt in range(self.max_retries + 1):
            try:
                start_time = time.time()
                
                response = self._client.post(
                    url=url,
                    json=request_payload,
                )
                
                duration = time.time() - start_time
                
                if response.status_code == 400:
                    error_msg = f"Bad request to OpenCode: {response.text[:200]}"
                    logger.error(error_msg)
                    raise OpenCodeHTTPError(error_msg, status_code=400)
                
                if response.status_code == 401:
                    error_msg = "Unauthorized: Check OPENCODE_BASE_URL and authentication"
                    logger.error(error_msg)
                    raise OpenCodeHTTPError(error_msg, status_code=401)
                
                if response.status_code == 404:
                    error_msg = f"Endpoint not found: {url}"
                    logger.error(error_msg)
                    raise OpenCodeHTTPError(error_msg, status_code=404)
                
                if response.status_code >= 400:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(error_msg)
                    raise OpenCodeHTTPError(error_msg, status_code=response.status_code)
                
                result = self._parse_response(response.json())
                
                logger.info(
                    "OpenCode execution completed: status=%s, duration=%.2fs",
                    result.status,
                    duration,
                )
                
                return result
                
            except httpx.TimeoutException as e:
                last_exception = e
                duration = time.time() - start_time if 'start_time' in locals() else 0
                logger.warning(
                    "Timeout on attempt %d/%d: duration=%.2fs",
                    attempt + 1,
                    self.max_retries + 1,
                    duration,
                )
                
            except httpx.ConnectError as e:
                last_exception = e
                logger.warning(
                    "Connection error on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    str(e)[:100],
                )
                
            except httpx.HTTPError as e:
                last_exception = e
                logger.warning(
                    "HTTP error on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    str(e)[:100],
                )
            
            if attempt < self.max_retries:
                backoff_delay = self._calculate_backoff_delay(attempt)
                logger.info(
                    "Retrying in %.2f seconds...",
                    backoff_delay,
                )
                time.sleep(backoff_delay)
        
        if isinstance(last_exception, httpx.TimeoutException):
            raise OpenCodeTimeoutError(
                f"Request timed out after {self.max_retries + 1} attempts"
            ) from last_exception
        elif isinstance(last_exception, httpx.ConnectError):
            raise OpenCodeConnectionError(
                f"Failed to connect after {self.max_retries + 1} attempts"
            ) from last_exception
        else:
            raise OpenCodeConnectionError(
                f"Request failed after {self.max_retries + 1} attempts: {last_exception}"
            ) from last_exception
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for retries."""
        min_delay = 1.0
        max_delay = 10.0
        multiplier = 2.0
        
        delay = min(min_delay * (multiplier ** attempt), max_delay)
        return delay
    
    def _parse_response(self, response_data: dict) -> OpenCodeExecutionResult:
        """
        Parse OpenCode API response into OpenCodeExecutionResult.
        
        Args:
            response_data: JSON response from OpenCode API
            
        Returns:
            Parsed OpenCodeExecutionResult
            
        Raises:
            OpenCodeHTTPError: If response format is invalid
        """
        if not isinstance(response_data, dict):
            raise OpenCodeHTTPError(
                "Invalid response format: expected JSON object",
                status_code=500,
            )
        
        status = response_data.get("status", "unknown")
        raw_output = response_data.get("output", response_data.get("raw_output", ""))
        summary = response_data.get("summary", raw_output[:200] if raw_output else "No summary")
        
        if not raw_output:
            logger.warning("Empty output from OpenCode")
        
        return OpenCodeExecutionResult(
            status=str(status),
            raw_output=str(raw_output),
            summary=str(summary),
        )
    
    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
    
    def __enter__(self) -> "OpenCodeClient":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def execute_with_opencode(
    prompt: str,
    verification_prompt: Optional[str] = None,
) -> OpenCodeExecutionResult:
    """
    Execute a prompt via the OpenCode API.
    
    This is the main entry point for OpenCode execution. It reads configuration
    from environment variables and handles the HTTP communication.
    
    Configuration:
        OPENCODE_BASE_URL: Required. Base URL of the OpenCode API.
        OPENCODE_TIMEOUT: Optional. Timeout in seconds (default: 120).
        OPENCODE_MAX_RETRIES: Optional. Max retries for transient errors (default: 3).
    
    Args:
        prompt: The main prompt to execute
        verification_prompt: Optional verification prompt
        
    Returns:
        OpenCodeExecutionResult with status, raw_output, and summary
        
    Raises:
        OpenCodeConfigurationError: If OPENCODE_BASE_URL is not set
        OpenCodeTimeoutError: If request times out
        OpenCodeConnectionError: If connection fails
        OpenCodeHTTPError: If API returns error response
        
    Example:
        >>> result = execute_with_opencode(
        ...     prompt="Implement a function",
        ...     verification_prompt="Verify edge cases"
        ... )
        >>> print(result.summary)
    """
    base_url = get_opencode_base_url()
    
    if not base_url:
        raise OpenCodeConfigurationError(
            "OPENCODE_BASE_URL environment variable is not set. "
            "Please configure the OpenCode API endpoint."
        )
    
    timeout = get_opencode_timeout()
    max_retries = get_opencode_max_retries()
    
    with OpenCodeClient(
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
    ) as client:
        return client.execute(prompt, verification_prompt)
