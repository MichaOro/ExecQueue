"""Shared FastAPI dependencies."""

from dataclasses import dataclass

from fastapi import Header


@dataclass(frozen=True)
class RequestContext:
    """Request-scoped execution context.

    The current release runs locally in a single-tenant mode. We still resolve
    context per request so later shared multi-project or multi-tenant modes do
    not require a different API shape.
    """

    tenant_id: str | None
    project_id: str | None
    mode: str


def resolve_request_context(
    tenant_id: str | None = None,
    project_id: str | None = None,
) -> RequestContext:
    """Resolve request context without enforcing shared-mode headers yet."""
    mode = "shared" if tenant_id or project_id else "single-tenant-local"
    return RequestContext(
        tenant_id=tenant_id,
        project_id=project_id,
        mode=mode,
    )


def get_request_context(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    x_project_id: str | None = Header(default=None, alias="X-Project-ID"),
) -> RequestContext:
    """FastAPI dependency wrapper for request context resolution."""
    return resolve_request_context(
        tenant_id=x_tenant_id,
        project_id=x_project_id,
    )
