---
description: Refresh the continuation-safe working state for the current task or phase.
agent: context-curator
subtask: true
---

Create or refresh `@docs/agent-state/CURRENT_STATE.md` for the current task or phase.

Rules:

1. Read the current repository state before writing.
2. Treat the repository and git facts as the source of truth.
3. Compress only decision-relevant context.
4. Do not include long logs, full diffs, or chat history.
5. If a fact is uncertain, mark it as `UNVERIFIED`.
6. Overwrite the file in the exact structure already defined there.
7. Keep the result short enough that a fresh session can resume from it safely.

Minimum content to preserve:

- goal of the current work
- current implementation or analysis state
- relevant files and why they matter
- decisions already made
- open risks or blockers
- next concrete steps
- validation status

If repository state and prior state conflict, prefer repository truth and record the conflict in `Recovery Notes`.
