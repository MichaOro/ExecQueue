"""Central health aggregation service."""

from execqueue.health.models import HealthCheckResult, HealthSummary, HealthStatus
from execqueue.health.registry import get_registered_healthchecks


def aggregate_system_status(components: list[HealthCheckResult]) -> HealthStatus:
    """Aggregate component statuses into overall system status."""
    if not components:
        return "ERROR"

    valid_statuses = {"OK", "DEGRADED", "ERROR"}

    for component in components:
        if component.status not in valid_statuses:
            return "ERROR"

    if any(component.status == "ERROR" for component in components):
        return "ERROR"

    if any(component.status == "DEGRADED" for component in components):
        return "DEGRADED"

    return "OK"


def status_to_emoji(status: HealthStatus) -> str:
    """Convert HealthStatus to its Telegram-friendly emoji."""
    mapping = {
        "OK": "\U0001F7E2",
        "DEGRADED": "\U0001F7E1",
        "ERROR": "\U0001F534",
    }
    return mapping.get(status, "\U0001F534")


def render_health_report(components: list[HealthCheckResult]) -> str:
    """Render a system health report for Telegram output."""
    system_status = aggregate_system_status(components)
    header = f"{status_to_emoji(system_status)} *System Health*"
    lines = [
        f"{status_to_emoji(component.status)} {component.component} - {component.status}"
        for component in components
    ]

    return "\n".join(
        [
            header,
            "━━━━━━━━━━━━━━━━━━━",
            *lines,
            "",
            "\U0001F534 = mindestens ein Service DOWN / ERROR",
            "\U0001F7E1 = kein Fehler, aber mindestens ein Service DEGRADED",
            "\U0001F7E2 = alle Services OK",
        ]
    )


def get_overall_health() -> HealthSummary:
    """Aggregate all registered component checks into one summary."""
    results = {}

    for check in get_registered_healthchecks():
        result = check()
        results[result.component] = result

    components = list(results.values())
    overall_status = aggregate_system_status(components)

    return HealthSummary(status=overall_status, checks=results)
