---
name: pytest-task
description: Expand or repair the ExecQueue pytest suite with focused coverage that matches the repository's current architecture and delivery stage.
---

Use this skill when creating, updating, or debugging tests.

Workflow:

1. Start from the smallest test that proves the intended behavior.
2. Keep tests near the current repository scope: API checks, runner/orchestrator behavior tests, and focused regression tests.
3. Prefer clear fixture-free tests unless reuse is real.
4. Use async tests only when the code path truly needs them.
5. Run `pytest` after meaningful test changes when feasible.

Checks:

- Does each test describe one behavior clearly?
- Is the test scope proportional to the current code maturity and execution complexity?
- Did the change avoid speculative test architecture?
