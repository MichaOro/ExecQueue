#!/usr/bin/env python3
"""Diagnostic CLI for Observability (REQ-012-10).

Provides commands for:
- Tracing executions by correlation ID
- Listing stale executions
- Inspecting execution details and events
- Viewing metrics
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any

import click

from execqueue.db.engine import get_engine
from execqueue.db.session import get_session
from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent
from execqueue.observability import get_metrics


def format_datetime(dt: datetime | None) -> str:
    """Format datetime for display."""
    if dt is None:
        return "N/A"
    return dt.isoformat()


def print_json(data: Any, pretty: bool = True) -> None:
    """Print data as JSON."""
    if pretty:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(json.dumps(data, default=str))


@click.group()
@click.option("--json", "use_json", is_flag=True, help="Output in JSON format")
@click.pass_context
def cli(ctx: click.Context, use_json: bool):
    """ExecQueue Observability CLI.

    Diagnostic tools for tracing executions, finding stale tasks, and viewing metrics.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json


@cli.command()
@click.option("--correlation-id", required=True, help="Correlation ID to trace")
@click.option("--json", "use_json", is_flag=True, help="Output in JSON format")
def trace(correlation_id: str, use_json: bool):
    """Trace all events for a correlation ID.

    Shows complete timeline of an execution from claim to completion.
    """
    session = get_session()
    try:
        # Find execution by correlation ID
        execution = session.query(TaskExecution).filter(
            TaskExecution.correlation_id == correlation_id
        ).first()

        if not execution:
            if use_json:
                print_json({"error": f"No execution found with correlation_id: {correlation_id}"})
            else:
                click.echo(f"Error: No execution found with correlation_id: {correlation_id}")
            sys.exit(1)

        # Get all events for this execution
        events = session.query(TaskExecutionEvent).filter(
            TaskExecutionEvent.task_execution_id == execution.id
        ).order_by(TaskExecutionEvent.sequence).all()

        if use_json:
            result = {
                "execution": execution.to_dict(),
                "events": [
                    {
                        "sequence": e.sequence,
                        "event_type": e.event_type,
                        "direction": e.direction,
                        "payload": e.payload,
                        "created_at": format_datetime(e.created_at),
                    }
                    for e in events
                ],
                "timeline": [
                    {
                        "timestamp": format_datetime(e.created_at),
                        "event": e.event_type,
                        "sequence": e.sequence,
                    }
                    for e in events
                ],
            }
            print_json(result)
        else:
            click.echo(f"\n=== Execution {execution.id} ===")
            click.echo(f"Correlation ID: {execution.correlation_id}")
            click.echo(f"Task ID: {execution.task_id}")
            click.echo(f"Status: {execution.status}")
            click.echo(f"Phase: {execution.phase or 'N/A'}")
            click.echo(f"Runner: {execution.runner_id or 'N/A'}")
            click.echo(f"Started: {format_datetime(execution.started_at)}")
            click.echo(f"Dispatched: {format_datetime(execution.dispatched_at)}")
            click.echo(f"Finished: {format_datetime(execution.finished_at)}")
            click.echo(f"Attempt: {execution.attempt}/{execution.max_attempts}")

            if execution.error_type:
                click.echo(f"Error Type: {execution.error_type}")
                click.echo(f"Error Message: {execution.error_message}")

            click.echo(f"\n=== {len(events)} Events ===")
            for event in events:
                click.echo(f"  [{event.sequence}] {event.event_type} ({event.direction})")
                click.echo(f"      Created: {format_datetime(event.created_at)}")

    finally:
        session.close()


@cli.command()
@click.option("--limit", default=10, help="Maximum number of stale executions to show")
@click.option("--json", "use_json", is_flag=True, help="Output in JSON format")
def list_stale(limit: int, use_json: bool):
    """List stale executions.

    Shows executions that have exceeded their timeout thresholds.
    """
    from execqueue.observability.logging import DEFAULT_STALE_THRESHOLDS
    from execqueue.runner.error_classification import find_stale_executions

    session = get_session()
    try:
        stale = find_stale_executions(session, limit=limit)

        if use_json:
            result = {
                "count": len(stale),
                "executions": [
                    {
                        "id": str(e.id),
                        "task_id": str(e.task_id),
                        "correlation_id": e.correlation_id,
                        "status": e.status,
                        "phase": e.phase,
                        "heartbeat_at": format_datetime(e.heartbeat_at),
                        "updated_at": format_datetime(e.updated_at),
                        "started_at": format_datetime(e.started_at),
                        "attempt": e.attempt,
                    }
                    for e in stale
                ],
            }
            print_json(result)
        else:
            click.echo(f"\n=== {len(stale)} Stale Executions ===")
            for exc in stale:
                click.echo(f"\n  Execution: {exc.id}")
                click.echo(f"    Correlation ID: {exc.correlation_id}")
                click.echo(f"    Task ID: {exc.task_id}")
                click.echo(f"    Status: {exc.status}")
                click.echo(f"    Phase: {exc.phase or 'N/A'}")
                click.echo(f"    Heartbeat: {format_datetime(exc.heartbeat_at)}")
                click.echo(f"    Updated: {format_datetime(exc.updated_at)}")
                click.echo(f"    Attempt: {exc.attempt}")

    finally:
        session.close()


@cli.command()
@click.option("--execution-id", required=True, help="Execution ID to inspect")
@click.option("--json", "use_json", is_flag=True, help="Output in JSON format")
def inspect(execution_id: str, use_json: bool):
    """Inspect execution details and events.

    Shows full details of a specific execution.
    """
    from uuid import UUID

    session = get_session()
    try:
        execution = session.query(TaskExecution).filter(
            TaskExecution.id == UUID(execution_id)
        ).first()

        if not execution:
            if use_json:
                print_json({"error": f"No execution found with id: {execution_id}"})
            else:
                click.echo(f"Error: No execution found with id: {execution_id}")
            sys.exit(1)

        # Get all events
        events = session.query(TaskExecutionEvent).filter(
            TaskExecutionEvent.task_execution_id == execution.id
        ).order_by(TaskExecutionEvent.sequence).all()

        if use_json:
            result = {
                "execution": execution.to_dict(),
                "events": [
                    {
                        "sequence": e.sequence,
                        "event_type": e.event_type,
                        "direction": e.direction,
                        "external_event_id": e.external_event_id,
                        "payload": e.payload,
                        "created_at": format_datetime(e.created_at),
                    }
                    for e in events
                ],
            }
            print_json(result)
        else:
            click.echo(f"\n=== Execution {execution.id} ===")
            for key, value in execution.to_dict().items():
                if value is not None:
                    click.echo(f"  {key}: {value}")

            click.echo(f"\n=== {len(events)} Events ===")
            for event in events:
                click.echo(f"  [{event.sequence}] {event.event_type}")
                click.echo(f"      Direction: {event.direction}")
                if event.payload:
                    click.echo(f"      Payload: {json.dumps(event.payload, default=str)}")

    finally:
        session.close()


@cli.command()
@click.option("--json", "use_json", is_flag=True, help="Output in JSON format")
def metrics(use_json: bool):
    """Show current metrics.

    Displays execution metrics collected during runtime.
    """
    metrics_data = get_metrics().to_dict()

    if use_json:
        print_json(metrics_data)
    else:
        click.echo("\n=== Execution Metrics ===")
        click.echo(f"Executions Claimed: {metrics_data['executions_claimed']}")
        click.echo(f"Executions Completed: {metrics_data['executions_completed']}")
        click.echo(f"Executions Failed: {metrics_data['executions_failed']}")
        click.echo(f"Success Rate: {metrics_data['success_rate']:.1%}")
        click.echo(f"Retries Scheduled: {metrics_data['retries_scheduled']}")
        click.echo(f"Retries Exhausted: {metrics_data['retries_exhausted']}")
        click.echo(f"Retry Rate: {metrics_data['retry_rate']:.1%}")
        click.echo(f"Stale Executions Detected: {metrics_data['stale_executions_detected']}")
        click.echo(f"Adoption Conflicts: {metrics_data['adoption_conflicts']}")

        click.echo("\n=== Average Phase Durations ===")
        for phase, duration in metrics_data['average_phase_durations'].items():
            click.echo(f"  {phase}: {duration:.2f}s")

        click.echo(f"\nFirst Execution: {metrics_data['first_execution']}")
        click.echo(f"Last Update: {metrics_data['last_update']}")


@cli.command()
@click.option("--limit", default=20, help="Number of recent executions to show")
@click.option("--status", help="Filter by status")
@click.option("--json", "use_json", is_flag=True, help="Output in JSON format")
def recent(limit: int, status: str | None, use_json: bool):
    """Show recent executions.

    Lists the most recent executions with optional status filter.
    """
    session = get_session()
    try:
        query = session.query(TaskExecution).order_by(
            TaskExecution.updated_at.desc()
        ).limit(limit)

        if status:
            query = query.filter(TaskExecution.status == status)

        executions = query.all()

        if use_json:
            result = {
                "count": len(executions),
                "executions": [e.to_dict() for e in executions],
            }
            print_json(result)
        else:
            click.echo(f"\n=== {len(executions)} Recent Executions ===")
            for exc in executions:
                click.echo(f"\n  {exc.id}")
                click.echo(f"    Task: {exc.task_id}")
                click.echo(f"    Correlation ID: {exc.correlation_id}")
                click.echo(f"    Status: {exc.status}")
                click.echo(f"    Phase: {exc.phase or 'N/A'}")
                click.echo(f"    Updated: {format_datetime(exc.updated_at)}")

    finally:
        session.close()


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
