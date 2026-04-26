"""Central health aggregation service."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from execqueue.health.models import HealthCheckResult, HealthSummary, HealthStatus
from execqueue.health.registry import get_registered_healthchecks

CHECK_SEPARATOR = "\u2501" * 20
INCOMPLETE_COMPONENT_DETAIL = "Component health data is incomplete."
MISSING_STATUS_DETAIL = "Component health data is incomplete: missing status."


def _derive_component_name(check: Callable[[], object], fallback_index: int) -> str:
    """Infer a stable component name from a health-check callable."""
    raw_name = getattr(check, "__name__", "") or f"component_{fallback_index}"
    component_name = raw_name.removeprefix("get_").removesuffix("_healthcheck")
    return component_name or f"component_{fallback_index}"


def normalize_health_component(component: object, fallback_name: str) -> HealthCheckResult:
    """Normalize arbitrary component data into a safe HealthCheckResult."""
    if isinstance(component, HealthCheckResult):
        normalized = component
    elif isinstance(component, dict):
        normalized = HealthCheckResult.model_construct(
            component=component.get("component") or component.get("name") or fallback_name,
            status=component.get("status"),
            detail=component.get("detail"),
        )
    else:
        normalized = HealthCheckResult.model_construct(
            component=getattr(component, "component", None)
            or getattr(component, "name", None)
            or fallback_name,
            status=getattr(component, "status", None),
            detail=getattr(component, "detail", None),
        )

    if normalized.status is None:
        return HealthCheckResult(
            component=normalized.component or fallback_name,
            status=HealthStatus.DEGRADED,
            detail=MISSING_STATUS_DETAIL,
        )

    try:
        status = HealthStatus(normalized.status)
    except (TypeError, ValueError):
        return HealthCheckResult(
            component=normalized.component or fallback_name,
            status=HealthStatus.ERROR,
            detail=f"Unknown health status: {normalized.status!r}.",
        )

    if not normalized.component or normalized.detail is None:
        degraded_status = HealthStatus.ERROR if status == HealthStatus.ERROR else HealthStatus.DEGRADED
        degraded_detail = (
            "Component reported an error without further detail."
            if status == HealthStatus.ERROR
            else INCOMPLETE_COMPONENT_DETAIL
        )
        return HealthCheckResult(
            component=normalized.component or fallback_name,
            status=degraded_status,
            detail=degraded_detail,
        )

    return HealthCheckResult(
        component=normalized.component,
        status=status,
        detail=normalized.detail,
    )


def aggregate_system_status(components: Iterable[object]) -> HealthStatus:
    """Aggregate component statuses into overall system status."""
    normalized_components = [
        normalize_health_component(component, fallback_name=f"component_{index}")
        for index, component in enumerate(components, start=1)
    ]

    if not normalized_components:
        return HealthStatus.ERROR

    if any(component.status == HealthStatus.ERROR for component in normalized_components):
        return HealthStatus.ERROR

    if any(component.status == HealthStatus.DEGRADED for component in normalized_components):
        return HealthStatus.DEGRADED

    return HealthStatus.OK


def status_to_emoji(status: HealthStatus | str) -> str:
    """Convert HealthStatus to its Telegram-friendly emoji."""
    try:
        normalized_status = HealthStatus(status)
    except (TypeError, ValueError):
        return "\U0001F534"

    mapping = {
        HealthStatus.OK: "\U0001F7E2",
        HealthStatus.DEGRADED: "\U0001F7E1",
        HealthStatus.ERROR: "\U0001F534",
    }
    return mapping[normalized_status]


def format_status_label(status: HealthStatus | str) -> str:
    """Format a status for user-facing output."""
    try:
        normalized_status = HealthStatus(status)
    except (TypeError, ValueError):
        return "Error"

    labels = {
        HealthStatus.OK: "OK",
        HealthStatus.DEGRADED: "Degraded",
        HealthStatus.ERROR: "Error",
    }
    return labels[normalized_status]


def format_component_name(component_name: str) -> str:
    """Format internal component ids for user-facing output."""
    aliases = {
        "api": "API",
        "database": "Database",
        "telegram_bot": "Telegram Bot",
        "acp": "ACP",
    }
    return aliases.get(component_name, component_name.replace("_", " ").title())


def render_health_report(components: list[object]) -> str:
    """Render a compact system health report for Telegram output."""
    normalized_components = [
        normalize_health_component(component, fallback_name=f"component_{index}")
        for index, component in enumerate(components, start=1)
    ]
    system_status = aggregate_system_status(normalized_components)
    header = f"{status_to_emoji(system_status)} *System Health*"
    lines = [
        f"{status_to_emoji(component.status)} {format_component_name(component.component)} \u2014 {format_status_label(component.status)}"
        for component in normalized_components
    ]

    return "\n".join([header, "", CHECK_SEPARATOR, "", *lines])


def get_overall_health() -> HealthSummary:
    """Aggregate all registered component checks into one summary."""
    results: dict[str, HealthCheckResult] = {}

    for index, check in enumerate(get_registered_healthchecks(), start=1):
        component_name = _derive_component_name(check, fallback_index=index)
        try:
            result = normalize_health_component(check(), fallback_name=component_name)
        except TimeoutError:
            result = HealthCheckResult(
                component=component_name,
                status=HealthStatus.ERROR,
                detail="Health check timed out.",
            )
        except Exception as exc:
            result = HealthCheckResult(
                component=component_name,
                status=HealthStatus.ERROR,
                detail=f"Health check failed: {exc}",
            )

        results[result.component] = result

    components = list(results.values())
    overall_status = aggregate_system_status(components)

    return HealthSummary(status=overall_status, checks=results)
