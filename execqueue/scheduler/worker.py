"""Background Worker für automatische Task-Abarbeitung."""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Any, NoReturn

from sqlmodel import Session

from execqueue.db.engine import get_session
from execqueue.runtime import (
    is_scheduler_enabled,
    get_scheduler_task_delay,
    get_scheduler_shutdown_timeout,
)
from execqueue.scheduler.runner import run_next_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s (%(filename)s:%(lineno)s)",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

_shutdown_requested = False
_shutdown_timeout = 30


def _handle_shutdown_signal(signum: int, frame: Any) -> None:
    global _shutdown_requested
    _shutdown_requested = True

    signal_name = signal.Signals(signum).name
    logger.info("Received %s, initiating graceful shutdown...", signal_name)


def _worker_loop() -> None:
    logger.info("Worker loop started")

    while not _shutdown_requested:
        try:
            with get_session() as session:
                task = run_next_task(session)

                if task:
                    logger.info(
                        "Processed task %s (status: %s, retry: %s)",
                        task.id,
                        task.status,
                        task.retry_count,
                    )
                else:
                    logger.debug("No queued task available, waiting...")
                    time.sleep(get_scheduler_task_delay())

        except Exception as e:
            logger.error("Error in worker loop: %s", e, exc_info=True)
            time.sleep(get_scheduler_task_delay())

    logger.info("Worker loop exited")


def _perform_shutdown() -> None:
    logger.info("Performing graceful shutdown...")

    start_time = time.time()
    while _shutdown_requested and (time.time() - start_time) < _shutdown_timeout:
        time.sleep(0.1)

    logger.info("Shutdown complete")


def main() -> NoReturn:
    global _shutdown_timeout

    if not is_scheduler_enabled():
        logger.info("Scheduler is disabled (SCHEDULER_ENABLED=false). Exiting.")
        sys.exit(0)

    _shutdown_timeout = get_scheduler_shutdown_timeout()

    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)

    logger.info("Starting ExecQueue Background Worker")
    logger.info("Task delay: %ds", get_scheduler_task_delay())
    logger.info("Shutdown timeout: %ds", _shutdown_timeout)

    try:
        _worker_loop()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
    finally:
        _perform_shutdown()

    sys.exit(0)


if __name__ == "__main__":
    main()
