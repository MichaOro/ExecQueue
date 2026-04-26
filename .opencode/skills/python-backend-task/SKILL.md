---
name: python-backend-task
description: Implement or refactor ExecQueue Python backend code with small, test-backed changes and minimal abstraction overhead.
---

Use this skill when working on normal Python application code in this repository.

Workflow:

1. Inspect the target package layout under `execqueue/` before editing.
2. Keep new code close to the feature area instead of introducing broad shared layers too early.
3. Prefer explicit functions, small classes, and direct data flow.
4. Add or update pytest coverage in `tests/` for behavior changes.
5. Run relevant validation, usually `pytest`, before closing the task when feasible.

Checks:

- Do imports stay clean and local to the feature?
- Is the added abstraction justified by real reuse?
- Does the change keep the bootstrap-stage codebase easier to understand?
