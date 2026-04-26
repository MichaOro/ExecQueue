---
name: fastapi-route-task
description: Add or change FastAPI routes in ExecQueue while keeping router wiring, response shape, and tests aligned.
---

Use this skill when touching HTTP endpoints, routers, request handling, or API wiring.

Workflow:

1. Identify the route module under `execqueue/api/routes/`.
2. Confirm router registration remains correct in `execqueue/api/router.py` or nearby wiring.
3. Keep endpoint behavior explicit and lightweight.
4. Prefer stable response models or predictable response dictionaries over hidden behavior.
5. Add or update endpoint tests in `tests/`, especially for status codes and response payloads.

Checks:

- Is the endpoint in the right route module?
- Does the route remain easy to discover from the router wiring?
- Are happy-path and basic edge-case tests covered?
