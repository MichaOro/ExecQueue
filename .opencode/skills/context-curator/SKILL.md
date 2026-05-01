---
name: context-curator
description: Create compact, continuation-safe working state for long OpenCode sessions without implementing code.
---

Use this skill when a session is getting large, drifting, or about to cross a phase boundary such as analysis, implementation, review, or restart.

Workflow:

1. Inspect the current repository, relevant files, and recent git facts before summarizing anything.
2. Prefer durable facts over session memory.
3. Write or refresh `docs/agent-state/CURRENT_STATE.md` using the fixed project template.
4. Preserve only what the next session needs to continue safely.
5. Mark anything uncertain as `UNVERIFIED` instead of guessing.

Do:

- keep the state short and restart-friendly
- preserve decisions, blockers, and next steps
- reference concrete files, branches, or commits when known
- note when the current state may be stale

Do not:

- implement code
- add long logs or full diffs
- retell the whole chat
- invent decisions or claim validation that did not happen

Checks:

- Could a fresh session resume from this file alone plus the repo?
- Does the file separate facts from uncertainty?
- Does it help reduce token load instead of recreating it?
