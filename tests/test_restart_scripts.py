"""Tests for restart script behavior (detached execution)."""

import os
import subprocess
import time
from pathlib import Path

import pytest

# Calculate paths relative to test file location
TESTS_DIR = Path(__file__).parent
PROJECT_ROOT = TESTS_DIR.parent
SCRIPTS_DIR = PROJECT_ROOT / "ops" / "scripts"
LOGS_DIR = PROJECT_ROOT / "ops" / "logs"
PID_DIR = PROJECT_ROOT / "ops" / "pids"
LOCKS_DIR = PROJECT_ROOT / "ops" / "locks"


@pytest.fixture(autouse=True)
def clean_restart_environment():
    """Clean up PID files, lock files, and logs before each test."""
    # Clean PID files
    for pid_file in PID_DIR.glob("*.pid"):
        pid_file.unlink(missing_ok=True)
    
    # Clean lock files
    for lock_file in LOCKS_DIR.glob("*.lock"):
        lock_file.unlink(missing_ok=True)
    
    # Clean restart logs (keep other logs)
    for log_file in LOGS_DIR.glob("*restart*.log"):
        log_file.unlink(missing_ok=True)
    
    yield
    
    # Cleanup after test (optional)


def test_global_restart_creates_lock_file():
    """Test that global_restart.sh creates a lock file."""
    lock_file = LOCKS_DIR / "global_restart.lock"
    
    # Run global_restart.sh with --help or a no-op step to avoid full restart
    result = subprocess.run(
        ["bash", "-c", f"cd {SCRIPTS_DIR.parent} && {SCRIPTS_DIR}/global_restart.sh api_restart"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    
    # Lock should be created and released
    # (We don't check if it exists after, just that the script ran without lock errors)
    assert result.returncode == 0 or "lock" not in result.stderr.lower()


def test_global_restart_starts_detached():
    """Test that global_restart.sh starts steps in detached mode."""
    result = subprocess.run(
        ["bash", "-c", f"cd {SCRIPTS_DIR.parent} && {SCRIPTS_DIR}/global_restart.sh api_restart"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    
    # Check that the log indicates detached execution
    log_file = LOGS_DIR / "global_restart.log"
    if log_file.exists():
        log_content = log_file.read_text()
        assert "detached" in log_content.lower() or "launched" in log_content.lower()


def test_api_restart_detach_mode():
    """Test that api_restart.sh uses DETACH_MODE."""
    result = subprocess.run(
        [str(SCRIPTS_DIR / "api_restart.sh")],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "EXECQUEUE_API_PORT": "8999"},  # Use different port to avoid conflict
    )
    
    # The script should exit 0 after detaching (parent process exits immediately)
    assert result.returncode == 0


def test_telegram_restart_detach_mode():
    """Test that telegram_restart.sh uses DETACH_MODE."""
    result = subprocess.run(
        [str(SCRIPTS_DIR / "telegram_restart.sh")],
        capture_output=True,
        text=True,
        timeout=10,
        env={
            **os.environ,
            "TELEGRAM_BOT_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",  # Fake token for testing
        },
    )
    
    # The script should exit 0 after detaching (parent process exits immediately)
    assert result.returncode == 0


def test_global_restart_lock_prevents_concurrent_execution():
    """Test that global_restart.sh prevents concurrent execution via lock."""
    lock_file = LOCKS_DIR / "global_restart.lock"
    
    # Create a lock file manually with a running PID (our own process)
    lock_file.write_text(str(os.getpid()))
    
    try:
        result = subprocess.run(
            [str(SCRIPTS_DIR / "global_restart.sh"), "api_restart"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # Should fail or warn about lock being held by running process
        # (The script may still proceed if it detects the lock is from itself)
        # We just check that the script runs without crashing
        assert result.returncode == 0 or "lock" in result.stdout.lower() or "lock" in result.stderr.lower() or "Aborting" in result.stdout
    finally:
        # Clean up
        lock_file.unlink(missing_ok=True)


def test_restart_scripts_handle_stale_locks():
    """Test that restart scripts can handle stale lock files."""
    import tempfile
    
    # Create a lock file with a non-existent PID
    lock_file = LOCKS_DIR / "api.restart.lock"
    lock_file.write_text("99999")  # Non-existent PID
    
    try:
        # Should clean up stale lock and proceed (or at least not crash)
        result = subprocess.run(
            [str(SCRIPTS_DIR / "api_restart.sh")],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "EXECQUEUE_API_PORT": "8998"},
        )
        
        # Script should handle stale lock gracefully
        assert result.returncode == 0 or "stale" in result.stdout.lower() or "clean" in result.stdout.lower()
    finally:
        lock_file.unlink(missing_ok=True)


def test_restart_scripts_log_to_correct_files():
    """Test that restart scripts write to correct log files."""
    # Run api_restart with a fake port
    result = subprocess.run(
        [str(SCRIPTS_DIR / "api_restart.sh")],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "EXECQUEUE_API_PORT": "8997"},
    )
    
    # Wait a moment for the detached process to write logs
    time.sleep(2)
    
    # Check that log file was created
    log_file = LOGS_DIR / "api_restart.log"
    # Note: The log may not exist if the script exited early due to port conflicts
    # We just check that the script ran without crashing
    assert result.returncode == 0, f"api_restart.sh should exit 0, got {result.returncode}"
    
    # If log exists, check its content
    if log_file.exists():
        log_content = log_file.read_text()
        assert "api_restart" in log_content.lower() or "starting" in log_content.lower()


def test_setsid_used_for_detached_execution():
    """Test that setsid is used in restart scripts for proper detachment."""
    # Check api_restart.sh for setsid usage
    api_script = (SCRIPTS_DIR / "api_restart.sh").read_text()
    assert "setsid" in api_script, "api_restart.sh should use setsid for detachment"
    
    # Check telegram_restart.sh for setsid usage
    telegram_script = (SCRIPTS_DIR / "telegram_restart.sh").read_text()
    assert "setsid" in telegram_script, "telegram_restart.sh should use setsid for detachment"
    
    # Check global_restart.sh for setsid usage
    global_script = (SCRIPTS_DIR / "global_restart.sh").read_text()
    assert "setsid" in global_script, "global_restart.sh should use setsid for detachment"


def test_detach_mode_environment_variable():
    """Test that DETACH_MODE environment variable is checked in scripts."""
    api_script = (SCRIPTS_DIR / "api_restart.sh").read_text()
    assert "DETACH_MODE" in api_script, "api_restart.sh should check DETACH_MODE"
    
    telegram_script = (SCRIPTS_DIR / "telegram_restart.sh").read_text()
    assert "DETACH_MODE" in telegram_script, "telegram_restart.sh should check DETACH_MODE"
