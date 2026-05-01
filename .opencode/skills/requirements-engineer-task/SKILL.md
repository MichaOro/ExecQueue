---
name: requirements-engineer-task
description: Create structured requirement artifacts (user stories, acceptance criteria, functional specs) from stakeholder input.
---

Use this skill when transforming high-level requests or stakeholder descriptions into formal requirement artifacts.

Workflow:

1. **Clarify Input**: Ask the user for the raw requirement description, target system context, and any known constraints.
2. **Extract Entities**: Inspect the existing code base with normal repository search and file reads to identify relevant domain concepts (e.g., `execqueue/` packages, models, API routes, runner and orchestrator modules).
3. **Structure the Artifact**:
   - Create a **User Story** in the format: "As a [role], I want [feature] so that [benefit]."
   - Define **Acceptance Criteria** (Given/When/Then format) with clear pass/fail conditions.
   - Optionally add **Non-Functional Requirements** (performance, security, availability).
4. **Validate Consistency**: Cross-check with existing code using repository search to ensure no contradictions with current architecture.
5. **Output Format**: Return a structured markdown block with:
   - Title
   - User Story
   - Acceptance Criteria (numbered list)
   - Related Code Areas (file paths or module names)
   - Open Questions (if any)

Checks:

- Are acceptance criteria testable and unambiguous?
- Do the requirements align with the project's current architecture and delivery priorities without over-engineering?
- Is the artifact concise enough for direct use in planning or review?

Recommended tools:

- repository search and file reads to discover relevant code areas and domain models
- `sequential-thinking` to structure the requirement elicitation and validation steps
- concise clarification questions only when stakeholder input is genuinely ambiguous

Output Example:

```markdown
## Requirement: REQ-001 - Multi-Tenant Task Queue

### User Story
As a system operator, I want to isolate task executions by tenant ID so that data leakage between tenants is prevented.

### Acceptance Criteria
1. Given a task execution request with `X-Tenant-ID` header, when the task is queued, then it must be tagged with that tenant ID in the database.
2. Given two different tenant IDs, when querying task executions, then results must not cross tenant boundaries.
3. Given no `X-Tenant-ID` header, when submitting a task, then the system must reject the request with HTTP 400.

### Related Code Areas
- `execqueue/api/routes/` (future tenant-aware endpoints)
- `execqueue/models/task_execution.py` (tenant_id field)

### Open Questions
- Should tenant ID be mandatory for all API endpoints or only specific ones?
```
