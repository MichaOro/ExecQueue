"""CLI Entry Point für execqueue Module."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from execqueue.scheduler.worker import main as worker_main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> int:
    """CLI Entry Point mit Subcommands."""
    parser = argparse.ArgumentParser(
        prog="execqueue",
        description="ExecQueue Task Management System",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    worker_parser = subparsers.add_parser(
        "worker",
        help="Start the background worker",
    )
    worker_parser.add_argument(
        "--enable",
        action="store_true",
        help="Enable scheduler (sets SCHEDULER_ENABLED=true)",
    )

    args = parser.parse_args()

    if args.command == "worker":
        if args.enable:
            os.environ["SCHEDULER_ENABLED"] = "true"

        worker_main()
        return 0

    elif args.command is None:
        parser.print_help()
        return 0

    else:
        logger.error("Unknown command: %s", args.command)
        return 1


if __name__ == "__main__":
    sys.exit(main())
