# ExecQueue Engineering Rules

- Treat this repository as a growing Python 3.10+ backend with FastAPI, orchestrator, runner, OpenCode integration, observability, and Telegram worker surfaces already in play.
- Keep production code in the existing package layout under `execqueue/`; do not introduce a `src/` layout unless the repository explicitly moves there.
- Prefer small, concrete modules over speculative abstractions. Add a new abstraction only when there are at least two clear call sites or a real testing need.
- Preserve the current API organization:
  - routing and endpoint wiring in `execqueue/api/`
  - route handlers in `execqueue/api/routes/`
  - domain-oriented code in package-specific modules such as `execqueue/health/`
- Add or update tests in `tests/` whenever behavior changes. For new backend behavior, default to focused pytest coverage rather than broad scaffolding.
- Use type hints on new Python code unless there is a strong reason not to.
- Keep FastAPI additions forward-compatible: lightweight request models, explicit response shapes, and minimal hidden magic.
- If a change affects installation, runtime dependencies, or test tooling, update `pyproject.toml`.
- If a change affects setup or operator workflow, update `README.md`.
- Prefer the smallest coherent change that leaves the codebase easier to extend than before, but do not underestimate cross-module effects in runner, orchestrator, workflow, and worker code.
