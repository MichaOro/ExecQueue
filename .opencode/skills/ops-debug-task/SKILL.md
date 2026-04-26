---
name: ops-debug-task
description: Inspect ExecQueue operational scripts and logs carefully without overwriting local operator changes or introducing unsafe automation.
---

Use this skill when investigating `ops/` scripts, logs, pid files, or restart helpers.

Workflow:

1. Inspect existing script behavior before changing anything.
2. Treat files under `ops/scripts/` as operator-owned and potentially locally customized.
3. Prefer explaining the current script flow before proposing edits.
4. If changes are needed, keep them minimal and preserve existing invocation patterns.
5. Avoid deleting logs or pid files unless the user explicitly asks.

Checks:

- Did the investigation preserve current operator workflow?
- Were unrelated local script edits left intact?
- Is the proposed change safer than the current behavior?
