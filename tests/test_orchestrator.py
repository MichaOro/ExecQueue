"""Tests for the local process orchestrator."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from execqueue.orchestrator import (
    LaunchPlan,
    ManagedProcess,
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


@dataclass
class FakePopen:
    pid: int
    poll_result: int | None = None

    def poll(self) -> int | None:
        return self.poll_result


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
