"""Central health aggregation service."""

from execqueue.health.models import HealthSummary
from execqueue.health.registry import get_registered_healthchecks


def get_overall_health() -> HealthSummary:
    """Aggregate all registered component checks into one summary."""
    results = {}

    for check in get_registered_healthchecks():
        result = check()
        results[result.component] = result

    overall_status = "ok" if all(result.status == "ok" for result in results.values()) else "not_ok"
    return HealthSummary(status=overall_status, checks=results)

