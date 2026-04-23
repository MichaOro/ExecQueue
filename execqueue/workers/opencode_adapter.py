"""
OpenCode Adapter - Production-ready integration with OpenCode Execution Engine.

This module provides a robust HTTP client for communicating with the OpenCode API,
including retry logic with exponential backoff, timeout handling, and comprehensive logging.
It also supports the Agent Client Protocol (ACP) for session-based orchestration.

Configuration (REST):
    OPENCODE_BASE_URL (required): Base URL of the OpenCode API (e.g., http://localhost:8000)
    OPENCODE_TIMEOUT (default: 120): Timeout in seconds for API requests
    OPENCODE_MAX_RETRIES (default: 3): Number of retries for network errors
    OPENCODE_USERNAME (optional): Username for HTTP Basic Auth
    OPENCODE_PASSWORD (optional): Password for HTTP Basic Auth

Configuration (ACP):
    OPENCODE_ACP_URL (default: http://localhost:8765): Base URL of the ACP server
    OPENCODE_SESSION_TIMEOUT (default: 300): Timeout in seconds for sessions
    OPENCODE_PASSWORD (optional): Password for ACP authentication

REST API Specification:
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

Example (REST):
    >>> from execqueue.workers.opencode_adapter import execute_with_opencode
    >>> result = execute_with_opencode(
    ...     prompt="Implement a function that adds two numbers",
    ...     verification_prompt="Verify the function handles edge cases"
    ... )
    >>> print(result.summary)

Example (ACP):
    >>> from execqueue.workers.opencode_adapter import OpenCodeACPClient
    >>> client = OpenCodeACPClient(acp_url="http://localhost:8765", password="secret")
    >>> session_id = client.start_session("Implement feature X", cwd="/path/to/project")
    >>> status = client.get_session_status(session_id)
    >>> result = client.export_session(session_id)
"""

from __future__ import annotations

import json
import logging
import random
import subprocess
import time
from dataclasses import dataclass
from functools import wraps
from typing import Optional, Callable, TypeVar

import httpx

from execqueue.runtime import (
    get_opencode_base_url,
    get_opencode_timeout,
    get_opencode_max_retries,
    get_opencode_username,
    get_opencode_password,
    get_opencode_acp_url,
    get_opencode_session_timeout,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


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


class OpenCodeSessionLostError(OpenCodeError):
    """Raised when a session is lost or no longer accessible."""
    pass


def retry_on_transient_errors(
    max_retries: int = 3,
    backoff_multiplier: float = 2.0,
    min_delay: float = 1.0,
    max_delay: float = 10.0,
):
    """
    Decorator for retrying transient OpenCode errors.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_multiplier: Multiplier for exponential backoff
        min_delay: Minimum delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Exception | None = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except (OpenCodeConnectionError, OpenCodeTimeoutError, OpenCodeSessionLostError) as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        # Calculate delay with exponential backoff + jitter
                        delay = min(min_delay * (backoff_multiplier ** attempt), max_delay)
                        jitter = delay * 0.1 * random.random()  # 10% jitter
                        total_delay = delay + jitter
                        
                        logger.warning(
                            "Transient error in %s (attempt %d/%d): %s. Retrying in %.2fs",
                            func.__name__,
                            attempt + 1,
                            max_retries + 1,
                            str(e)[:100],
                            total_delay
                        )
                        
                        time.sleep(total_delay)
                    else:
                        logger.error(
                            "Failed after %d attempts in %s: %s",
                            max_retries + 1,
                            func.__name__,
                            str(e)[:200]
                        )
                        raise
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected state in retry decorator")
        
        return wrapper
    return decorator


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
    - HTTP Basic Auth support (optional)
    
    Args:
        base_url: Base URL of the OpenCode API
        timeout: Timeout in seconds for API requests
        max_retries: Maximum number of retries for transient errors
        auth: Optional tuple of (username, password) for HTTP Basic Auth
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 120,
        max_retries: int = 3,
        auth: tuple[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.auth = auth
        
        # httpx.Client unterstützt auth-Parameter für Basic Auth
        self._client = httpx.Client(timeout=timeout, auth=auth)
    
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
        OPENCODE_USERNAME: Optional. Username for HTTP Basic Auth.
        OPENCODE_PASSWORD: Optional. Password for HTTP Basic Auth.
    
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
    username = get_opencode_username()
    password = get_opencode_password()
    
    # HTTP Basic Auth konfigurieren, falls Credentials vorhanden
    auth = None
    if username and password:
        auth = (username, password)
        logger.info("OpenCode: HTTP Basic Auth configured")
    else:
        logger.info("OpenCode: No authentication configured (assuming public API)")
    
    with OpenCodeClient(
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
        auth=auth,
    ) as client:
        return client.execute(prompt, verification_prompt)


# ============================================================================
# ACP (Agent Client Protocol) Client
# ============================================================================

class OpenCodeACPClient:
    """
    Client für die Kommunikation mit dem OpenCode ACP-Server.
    
    Dieser Client nutzt die OpenCode CLI zur Steuerung von Sessions über
    Subprocess-Aufrufe mit JSON-Output für strukturierte Parsing.
    
    Configuration:
        OPENCODE_ACP_URL: Base URL of the ACP server (default: http://localhost:8765)
        OPENCODE_SESSION_TIMEOUT: Session timeout in seconds (default: 300)
        OPENCODE_PASSWORD: Password for ACP authentication (optional)
    
    Example:
        >>> client = OpenCodeACPClient(acp_url="http://localhost:8765", password="secret")
        >>> session_id = client.start_session("Implement feature", cwd="/path/to/project")
        >>> status = client.get_session_status(session_id)
        >>> result = client.export_session(session_id)
    """
    
    def __init__(
        self,
        acp_url: str | None = None,
        password: str | None = None,
        timeout: int | None = None,
    ):
        """
        Initialisiere den ACP-Client.
        
        Args:
            acp_url: ACP-Server URL (default from OPENCODE_ACP_URL)
            password: Password for authentication (default from OPENCODE_PASSWORD)
            timeout: Session timeout in seconds (default from OPENCODE_SESSION_TIMEOUT)
        """
        self.acp_url = acp_url or get_opencode_acp_url()
        self.password = password or get_opencode_password()
        self.timeout = timeout or get_opencode_session_timeout()
        
        logger.info(
            "OpenCodeACPClient initialized: url=%s, timeout=%ds, password=%s",
            self.acp_url,
            self.timeout,
            "set" if self.password else "not set"
        )
    
    def _build_base_command(self) -> list[str]:
        """Build base opencode command with common flags."""
        cmd = ["opencode", "run"]
        
        if self.password:
            cmd.extend(["--password", self.password])
        
        return cmd
    
    def _run_command(
        self,
        args: list[str],
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> dict:
        """
        Execute opencode command and parse JSON output.
        
        Supports multiple output formats:
        - Single JSON object: {"status": "completed", "output": "..."}
        - JSON array: [{"event": "..."}, {"event": "..."}]
        - NDJSON (newline-delimited JSON): One JSON object per line
        - Plain text: Fallback if no JSON detected
        
        Args:
            args: Command arguments (after 'opencode run')
            cwd: Working directory for the command
            timeout: Command timeout in seconds
            
        Returns:
            Parsed JSON response or aggregated events
            
        Raises:
            OpenCodeTimeoutError: If command times out
            OpenCodeConnectionError: If command fails
            OpenCodeSessionLostError: If session is not found
        """
        cmd = self._build_base_command() + args
        
        try:
            logger.debug("Executing ACP command: %s", " ".join(cmd[:10]))
            
            # Use Popen for streaming output (better for long-running commands)
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1  # Line buffered
            )
            
            stdout_lines = []
            json_events = []
            
            # Read output line by line
            if process.stdout:
                for line in process.stdout:
                    line = line.rstrip('\n\r')
                    if not line:
                        continue
                    
                    stdout_lines.append(line)
                    
                    # Try to parse as JSON (NDJSON format)
                    try:
                        event = json.loads(line)
                        json_events.append(event)
                    except json.JSONDecodeError:
                        # Not JSON, keep as text
                        logger.debug("Non-JSON output line: %s", line[:100])
                
                # Wait for process to complete
                process.wait(timeout=timeout or self.timeout)
            
            # Handle process errors
            if process.returncode != 0:
                error_output = ""
                if process.stderr:
                    error_output = process.stderr.read() or ""
                error_msg = error_output.strip() or "Unknown error"
                
                if "session not found" in error_msg.lower() or "invalid session" in error_msg.lower():
                    raise OpenCodeSessionLostError(f"Session lost: {error_msg}")
                
                raise OpenCodeConnectionError(f"Command failed: {error_msg}")
            
            # Parse and return result
            return self._parse_json_output(
                "\n".join(stdout_lines),
                json_events
            )
            
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            raise OpenCodeTimeoutError(f"Command timed out after {timeout or self.timeout}s")
        except FileNotFoundError as e:
            raise OpenCodeConfigurationError(
                "opencode CLI not found in PATH. Please install opencode."
            ) from e
        except subprocess.SubprocessError as e:
            raise OpenCodeConnectionError(f"Subprocess error: {str(e)}") from e
    
    def _parse_json_output(self, stdout: str, json_events: list) -> dict:
        """
        Parse JSON output from various formats.
        
        Args:
            stdout: Raw stdout output
            json_events: List of successfully parsed JSON events
            
        Returns:
            Aggregated result dict
        """
        # Case 1: We have parsed JSON events
        if json_events:
            if len(json_events) == 1:
                # Single event - return as-is
                return json_events[0]
            else:
                # Multiple events - return aggregated
                return {
                    "events": json_events,
                    "status": "completed",
                    "event_count": len(json_events),
                    "last_event": json_events[-1]
                }
        
        # Case 2: No JSON events, try to parse stdout as single JSON
        stdout = stdout.strip()
        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                pass  # Not JSON, fall through to text
        
        # Case 3: Plain text output
        if stdout:
            logger.warning("No JSON detected in output, returning as text")
            return {
                "output": stdout,
                "status": "unknown",
                "type": "text"
            }
        
        # Case 4: Empty output
        return {"status": "success", "output": ""}
    
    @retry_on_transient_errors(max_retries=3, min_delay=1.0, max_delay=10.0)
    def start_session(
        self,
        prompt: str,
        cwd: str,
        title: str | None = None,
    ) -> str:
        """
        Start a new OpenCode session.
        
        Args:
            prompt: The prompt to execute
            cwd: Project directory for the session
            title: Optional title for the session
            
        Returns:
            Session ID
            
        Raises:
            OpenCodeError: If session creation fails
        """
        args = [
            "--attach", self.acp_url,
            "--cwd", cwd,
            "--format", "json",
            "--print-logs",
            "--log-level", "ERROR",
            prompt,
        ]
        
        if title:
            args.extend(["--title", title])
        
        logger.info(
            "Starting ACP session: prompt_length=%d, cwd=%s, title=%s",
            len(prompt),
            cwd,
            title or "none"
        )
        
        result = self._run_command(args, cwd=cwd)
        
        # Extract session ID from result
        session_id = result.get("session_id") or result.get("id")
        if not session_id:
            # If no session ID in response, generate one or extract from output
            logger.warning("No session_id in response, using timestamp-based ID")
            session_id = f"session-{int(time.time())}"
        
        logger.info("ACP session started: session_id=%s", session_id)
        return session_id
    
    @retry_on_transient_errors(max_retries=2, min_delay=1.0, max_delay=5.0)
    def get_session_status(self, session_id: str) -> dict:
        """
        Get the status of a session.
        
        Args:
            session_id: The session ID to check
            
        Returns:
            Session status information
            
        Raises:
            OpenCodeSessionLostError: If session not found
        """
        # Use 'opencode session get' or attach to session
        args = [
            "--attach", self.acp_url,
            "--session", session_id,
            "--format", "json",
            "--print-logs",
            "--log-level", "ERROR",
            "Status check",
        ]
        
        logger.debug("Checking session status: session_id=%s", session_id)
        result = self._run_command(args)
        
        return {
            "session_id": session_id,
            "status": result.get("status", "unknown"),
            "output": result.get("output", ""),
            "raw_output": result.get("raw_output", ""),
        }
    
    @retry_on_transient_errors(max_retries=2, min_delay=1.0, max_delay=5.0)
    def continue_session(
        self,
        session_id: str,
        prompt: str | None = None,
    ) -> dict:
        """
        Continue a paused session.
        
        Args:
            session_id: The session ID to continue
            prompt: Optional prompt to send when continuing
            
        Returns:
            Session result
            
        Raises:
            OpenCodeSessionLostError: If session not found
        """
        args = [
            "--attach", self.acp_url,
            "--session", session_id,
            "--continue",
            "--format", "json",
            "--print-logs",
            "--log-level", "ERROR",
        ]
        
        if prompt:
            args.append(prompt)
        
        logger.info("Continuing ACP session: session_id=%s", session_id)
        result = self._run_command(args)
        
        return {
            "session_id": session_id,
            "status": result.get("status", "continued"),
            "output": result.get("output", ""),
        }
    
    def export_session(self, session_id: str) -> dict:
        """
        Export the result of a completed session.
        
        Args:
            session_id: The session ID to export
            
        Returns:
            Session result including full output
            
        Raises:
            OpenCodeSessionLostError: If session not found
        """
        # Use 'opencode export' command
        try:
            cmd = ["opencode", "export", session_id]
            if self.password:
                cmd.extend(["--password", self.password])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
            )
            
            if result.returncode != 0:
                raise OpenCodeConnectionError(f"Export failed: {result.stderr}")
            
            output = result.stdout.strip()
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"session_id": session_id, "output": output}
                
        except subprocess.TimeoutExpired:
            raise OpenCodeTimeoutError("Export timed out")
        except FileNotFoundError:
            raise OpenCodeConfigurationError("opencode CLI not found")
    
    def close_session(self, session_id: str) -> None:
        """
        Close a session gracefully.
        
        Args:
            session_id: The session ID to close
        """
        logger.info("Closing ACP session: session_id=%s", session_id)
        # Note: Sessions may auto-close after timeout
        # This is a best-effort cleanup
        try:
            args = [
                "--attach", self.acp_url,
                "--session", session_id,
                "--format", "json",
                "Session closed",
            ]
            self._run_command(args, timeout=10)
        except Exception as e:
            logger.warning("Failed to close session %s: %s", session_id, e)
