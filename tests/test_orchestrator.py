"""Tests for the local process orchestrator."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from unittest.mock import patch

from execqueue.orchestrator import (
    ACPLifecycleManager,
    LaunchPlan,
    ManagedProcess,
    build_acp_command,
    build_launch_plan,
    monitor_processes,
)
from execqueue.settings import Settings


def test_build_launch_plan_starts_api_without_bot_by_default():
    # Create settings without loading .env to ensure clean defaults
    from pydantic_settings import SettingsConfigDict
    
    class TestSettings(Settings):
        model_config = SettingsConfigDict(env_file="", extra="ignore")
    
    settings = TestSettings()

    plan = build_launch_plan(settings, python_executable="python")

    assert isinstance(plan, LaunchPlan)
    assert plan.bot_command is None
    assert plan.acp_command is None
    assert plan.configuration_errors == ()
    assert plan.api_command == [
        "python",
        "-m",
        "uvicorn",
        "execqueue.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]


def test_build_launch_plan_skips_bot_when_enabled_without_token():
    settings = Settings(
        telegram_bot_enabled=True,
        telegram_bot_token=None,
    )

    plan = build_launch_plan(settings, python_executable="python")

    assert plan.bot_command is None
    assert plan.configuration_errors == (
        "Telegram bot is enabled but TELEGRAM_BOT_TOKEN is not set. "
        "Skipping bot startup.",
    )


def test_build_launch_plan_starts_bot_when_enabled_with_token():
    settings = Settings(
        telegram_bot_enabled=True,
        telegram_bot_token="test-token",
    )

    plan = build_launch_plan(settings, python_executable="python")

    assert plan.bot_command == ["python", "-m", "execqueue.workers.telegram.bot"]


def test_build_acp_command_returns_none_without_configuration():
    settings = Settings(acp_enabled=True, acp_start_command=None)

    assert build_acp_command(settings) is None


def test_build_launch_plan_skips_acp_when_auto_start_lacks_command():
    settings = Settings(
        acp_enabled=True,
        acp_auto_start=True,
        acp_start_command=None,
    )

    plan = build_launch_plan(settings, python_executable="python")

    assert plan.acp_command is None
    assert plan.configuration_errors == (
        "ACP auto-start is enabled but ACP_START_COMMAND is not set. "
        "Skipping ACP startup.",
    )


def test_build_launch_plan_starts_acp_when_enabled_for_auto_start():
    settings = Settings(
        acp_enabled=True,
        acp_auto_start=True,
        acp_start_command="python -m opencode_acp --port 8010",
    )

    plan = build_launch_plan(settings, python_executable="python")

    assert plan.acp_command == ["python", "-m", "opencode_acp", "--port", "8010"]


@dataclass
class FakePopen:
    pid: int
    poll_result: int | None = None

    def poll(self) -> int | None:
        return self.poll_result

    def terminate(self) -> None:
        self.poll_result = 0

    def kill(self) -> None:
        self.poll_result = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.poll_result or 0


def test_monitor_processes_returns_when_required_process_exits():
    stop_event = threading.Event()
    processes = [
        ManagedProcess(name="api", process=FakePopen(pid=1, poll_result=0), required=True)
    ]

    exit_code = monitor_processes(processes, stop_event=stop_event, poll_interval=0)

    assert exit_code == 0
    assert stop_event.is_set() is True


def test_monitor_processes_returns_zero_when_stop_signal_is_set():
    stop_event = threading.Event()
    stop_event.set()
    processes = [
        ManagedProcess(name="api", process=FakePopen(pid=1, poll_result=None), required=True),
        ManagedProcess(
            name="telegram-bot",
            process=FakePopen(pid=2, poll_result=1),
            required=False,
        ),
    ]

    exit_code = monitor_processes(processes, stop_event=stop_event, poll_interval=0)

    assert exit_code == 0


def test_acp_lifecycle_status_is_disabled_when_feature_flag_is_off():
    manager = ACPLifecycleManager(Settings(acp_enabled=False))

    status = manager.status()

    assert status.enabled is False
    assert status.running is False
    assert status.state == "disabled"


def test_acp_lifecycle_start_returns_error_without_start_command():
    manager = ACPLifecycleManager(Settings(acp_enabled=True, acp_start_command=None))

    status = manager.start()

    assert status.state == "error"
    assert status.running is False
    assert status.last_error == "ACP is enabled but ACP_START_COMMAND is not configured."


def test_acp_lifecycle_start_spawns_process_when_configured():
    manager = ACPLifecycleManager(
        Settings(
            acp_enabled=True,
            acp_start_command="python -m opencode_acp",
        )
    )

    with patch("execqueue.orchestrator.subprocess.Popen", return_value=FakePopen(pid=42)):
        status = manager.start()

    assert status.state == "running"
    assert status.running is True
    assert status.pid == 42


def test_acp_lifecycle_stop_terminates_running_process():
    manager = ACPLifecycleManager(
        Settings(
            acp_enabled=True,
            acp_start_command="python -m opencode_acp",
        )
    )
    manager.attach_process(FakePopen(pid=42))

    status = manager.stop()

    assert status.state == "stopped"
    assert status.running is False
    assert status.last_exit_code == 0


def test_acp_lifecycle_restart_starts_again_after_stop():
    manager = ACPLifecycleManager(
        Settings(
            acp_enabled=True,
            acp_start_command="python -m opencode_acp",
        )
    )
    manager.attach_process(FakePopen(pid=42))

    with patch("execqueue.orchestrator.subprocess.Popen", return_value=FakePopen(pid=43)):
        status = manager.restart()

    assert status.state == "running"
    assert status.running is True
    assert status.pid == 43
