"""Local process orchestrator for the API and optional Telegram bot."""

from __future__ import annotations

import logging
import shlex
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
    acp_command: list[str] | None = None
    configuration_errors: tuple[str, ...] = ()


@dataclass
class ManagedProcess:
    """Runtime information for a started child process."""

    name: str
    process: subprocess.Popen[bytes]
    required: bool


@dataclass(frozen=True)
class ACPStatus:
    """Snapshot of the ACP runtime state."""

    name: str
    enabled: bool
    auto_start: bool
    running: bool
    state: str
    pid: int | None = None
    command: tuple[str, ...] = ()
    message: str = ""
    last_error: str | None = None
    last_exit_code: int | None = None


class ACPLifecycleManager:
    """Manage ACP as an optional local child process."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._process: subprocess.Popen[bytes] | None = None
        self._last_error: str | None = None
        self._last_exit_code: int | None = None
        self._state = "disabled" if not settings.acp_enabled else "stopped"

    def status(self) -> ACPStatus:
        """Return the current ACP runtime status."""
        process = self._process
        pid: int | None = None
        running = False

        if not self._settings.acp_enabled:
            self._state = "disabled"
            return self._snapshot(message="ACP integration is disabled.")

        if process is not None:
            return_code = process.poll()
            if return_code is None:
                running = True
                pid = process.pid
                self._state = "running"
            else:
                self._process = None
                self._last_exit_code = return_code
                if self._state not in {"error", "stopping"}:
                    self._state = "stopped"

        message = self._status_message()
        return self._snapshot(
            pid=pid,
            running=running,
            message=message,
        )

    def start(self) -> ACPStatus:
        """Start ACP when enabled and configured."""
        current = self.status()
        if not current.enabled:
            return current
        if current.running:
            return self._snapshot(
                pid=current.pid,
                running=True,
                message="ACP process is already running.",
            )

        command = build_acp_command(self._settings)
        if command is None:
            self._state = "error"
            self._last_error = (
                "ACP is enabled but ACP_START_COMMAND is not configured."
            )
            logger.error(self._last_error)
            return self._snapshot(message=self._last_error, last_error=self._last_error)

        self._state = "starting"
        self._last_error = None
        logger.info("Starting ACP process: %s", " ".join(command))

        try:
            process = subprocess.Popen(command)
        except OSError as exc:
            self._state = "error"
            self._last_error = str(exc)
            logger.exception("Failed to start ACP process.")
            return self._snapshot(message="Failed to start ACP process.", last_error=str(exc))

        return_code = process.poll()
        if return_code is not None:
            self._state = "error"
            self._process = None
            self._last_exit_code = return_code
            self._last_error = f"ACP process exited immediately with code {return_code}."
            logger.error(self._last_error)
            return self._snapshot(message=self._last_error, last_error=self._last_error)

        self._process = process
        self._last_exit_code = None
        self._state = "running"
        logger.info("ACP process started successfully (pid=%s).", process.pid)
        return self._snapshot(
            pid=process.pid,
            running=True,
            message="ACP process started successfully.",
        )

    def stop(self) -> ACPStatus:
        """Stop ACP when it is running."""
        current = self.status()
        if not current.enabled:
            return current
        if not current.running or self._process is None:
            self._state = "stopped"
            return self._snapshot(message="ACP process is not running.")

        self._state = "stopping"
        try:
            terminate_process(
                ManagedProcess(name="acp", process=self._process, required=False),
                grace_seconds=float(self._settings.acp_timeout),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._state = "error"
            self._last_error = str(exc)
            logger.exception("Failed to stop ACP process cleanly.")
            return self._snapshot(message="Failed to stop ACP process.", last_error=str(exc))

        self._process = None
        self._last_exit_code = 0
        self._last_error = None
        self._state = "stopped"
        logger.info("ACP process stopped.")
        return self._snapshot(message="ACP process stopped.")

    def restart(self) -> ACPStatus:
        """Restart ACP using the current configuration."""
        current = self.status()
        if not current.enabled:
            return current

        if current.running:
            stopped = self.stop()
            if stopped.state == "error":
                return stopped

        return self.start()

    def attach_process(self, process: subprocess.Popen[bytes]) -> ACPStatus:
        """Adopt an already-started ACP process into the lifecycle manager."""
        self._process = process
        self._last_error = None
        self._last_exit_code = None
        self._state = "running"
        return self.status()

    def _snapshot(
        self,
        *,
        pid: int | None = None,
        running: bool | None = None,
        message: str | None = None,
        last_error: str | None = None,
    ) -> ACPStatus:
        command = build_acp_command(self._settings) or []
        return ACPStatus(
            name="acp",
            enabled=self._settings.acp_enabled,
            auto_start=self._settings.acp_auto_start,
            running=self._state == "running" if running is None else running,
            state=self._state,
            pid=pid,
            command=tuple(command),
            message=message or self._status_message(),
            last_error=self._last_error if last_error is None else last_error,
            last_exit_code=self._last_exit_code,
        )

    def _status_message(self) -> str:
        if self._state == "disabled":
            return "ACP integration is disabled."
        if self._state == "running":
            return "ACP process is running."
        if self._state == "starting":
            return "ACP process is starting."
        if self._state == "stopping":
            return "ACP process is stopping."
        if self._state == "error" and self._last_error:
            return self._last_error
        if build_acp_command(self._settings) is None:
            return "ACP is enabled but ACP_START_COMMAND is not configured."
        return "ACP process is stopped."


def build_acp_command(settings: Settings) -> list[str] | None:
    """Return the configured ACP start command, if available."""
    if not settings.acp_start_command:
        return None

    return shlex.split(
        settings.acp_start_command,
        posix=not sys.platform.startswith("win"),
    )


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

    configuration_errors: list[str] = []

    acp_command: list[str] | None = None
    if settings.acp_enabled and settings.acp_auto_start:
        acp_command = build_acp_command(settings)
        if acp_command is None:
            configuration_errors.append(
                "ACP auto-start is enabled but ACP_START_COMMAND is not set. "
                "Skipping ACP startup."
            )

    bot_command: list[str] | None = None
    if settings.telegram_bot_enabled:
        if not settings.telegram_bot_token:
            configuration_errors.append(
                "Telegram bot is enabled but TELEGRAM_BOT_TOKEN is not set. "
                "Skipping bot startup."
            )
        else:
            bot_command = [python_bin, "-m", "execqueue.workers.telegram.bot"]

    return LaunchPlan(
        api_command=api_command,
        bot_command=bot_command,
        acp_command=acp_command,
        configuration_errors=tuple(configuration_errors),
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
    acp_manager = ACPLifecycleManager(runtime_settings)
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

    if plan.acp_command is not None:
        acp_process = spawn_process("acp", plan.acp_command, required=False)
        managed_processes.append(acp_process)
        acp_manager.attach_process(acp_process.process)
    else:
        logger.info("ACP process not started.")

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
