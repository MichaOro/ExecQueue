"""Local process orchestrator for the API and optional Telegram bot."""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from threading import Event

from execqueue.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LaunchPlan:
    """Concrete commands and configuration warnings for a local run."""

    api_command: list[str]
    bot_command: list[str] | None
    configuration_errors: tuple[str, ...] = ()


@dataclass
class ManagedProcess:
    """Runtime information for a started child process."""

    name: str
    process: subprocess.Popen[bytes]
    required: bool


def build_launch_plan(
    settings: Settings,
    python_executable: str | None = None,
) -> LaunchPlan:
    """Build the command plan for the local orchestrator."""
    python_bin = python_executable or sys.executable
    api_command = [
        python_bin,
        "-m",
        "uvicorn",
        settings.execqueue_api_app,
        "--host",
        settings.execqueue_api_host,
        "--port",
        str(settings.execqueue_api_port),
    ]

    if not settings.telegram_bot_enabled:
        return LaunchPlan(api_command=api_command, bot_command=None)

    if not settings.telegram_bot_token:
        return LaunchPlan(
            api_command=api_command,
            bot_command=None,
            configuration_errors=(
                "Telegram bot is enabled but TELEGRAM_BOT_TOKEN is not set. "
                "Skipping bot startup.",
            ),
        )

    return LaunchPlan(
        api_command=api_command,
        bot_command=[python_bin, "-m", "execqueue.workers.telegram.bot"],
    )


def spawn_process(name: str, command: list[str], required: bool) -> ManagedProcess:
    """Start a child process and keep stderr/stdout attached to the console."""
    logger.info("Starting %s process: %s", name, " ".join(command))
    process = subprocess.Popen(command)
    return ManagedProcess(name=name, process=process, required=required)


def terminate_process(managed_process: ManagedProcess, grace_seconds: float = 10.0) -> None:
    """Terminate a child process gracefully, then force-kill if needed."""
    process = managed_process.process
    if process.poll() is not None:
        return

    logger.info("Stopping %s process (pid=%s)", managed_process.name, process.pid)
    process.terminate()
    deadline = time.monotonic() + grace_seconds

    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.1)

    logger.warning(
        "%s process did not stop within %.1f seconds, killing it.",
        managed_process.name,
        grace_seconds,
    )
    process.kill()
    process.wait(timeout=grace_seconds)


def monitor_processes(
    processes: list[ManagedProcess],
    stop_event: Event,
    poll_interval: float = 0.5,
) -> int:
    """Keep the orchestrator alive until the API exits or a stop signal arrives."""
    watched_processes = list(processes)

    while not stop_event.is_set():
        for managed_process in list(watched_processes):
            return_code = managed_process.process.poll()
            if return_code is None:
                continue

            if managed_process.required:
                logger.info(
                    "%s process exited with code %s. Shutting down orchestrator.",
                    managed_process.name,
                    return_code,
                )
                stop_event.set()
                return return_code

            logger.warning(
                "%s process exited with code %s. API continues to run.",
                managed_process.name,
                return_code,
            )
            watched_processes.remove(managed_process)

        time.sleep(poll_interval)

    return 0


def run_orchestrator(settings: Settings | None = None) -> int:
    """Run the local process orchestrator."""
    runtime_settings = settings or get_settings()
    plan = build_launch_plan(runtime_settings)
    for error in plan.configuration_errors:
        logger.error(error)

    stop_event = Event()

    def handle_shutdown(signum: int, _frame: object) -> None:
        signal_name = signal.Signals(signum).name
        logger.info("Received %s. Stopping child processes...", signal_name)
        stop_event.set()

    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(shutdown_signal, handle_shutdown)

    managed_processes = [spawn_process("api", plan.api_command, required=True)]

    if plan.bot_command is not None:
        managed_processes.append(
            spawn_process("telegram-bot", plan.bot_command, required=False)
        )
    else:
        logger.info("Telegram bot process not started.")

    exit_code = 0
    try:
        exit_code = monitor_processes(managed_processes, stop_event=stop_event)
    finally:
        for managed_process in reversed(managed_processes):
            terminate_process(managed_process)

    return exit_code


def main() -> int:
    """CLI entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return run_orchestrator()


if __name__ == "__main__":
    raise SystemExit(main())
