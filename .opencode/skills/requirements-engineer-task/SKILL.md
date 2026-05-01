---
name: requirements-engineer-task
description: Create structured requirement artifacts (user stories, acceptance criteria, functional specs) from stakeholder input.
---

Use this skill when transforming high-level requests or stakeholder descriptions into formal requirement artifacts.

Workflow:

1. **Clarify Input**: Ask the user for the raw requirement description, target system context, and any known constraints.
2. **Extract Entities**: Use `explore` to identify relevant domain concepts in the existing code base (e.g., `execqueue/` packages, models, API routes).
3. **Structure the Artifact**:
   - Create a **User Story** in the format: "As a [role], I want [feature] so that [benefit]."
   - Define **Acceptance Criteria** (Given/When/Then format) with clear pass/fail conditions.
   - Optionally add **Non-Functional Requirements** (performance, security, availability).
4. **Validate Consistency**: Cross-check with existing code using `grep` to ensure no contradictions with current architecture.
5. **Output Format**: Return a structured markdown block with:
   - Title
   - User Story
   - Acceptance Criteria (numbered list)
   - Related Code Areas (file paths or module names)
   - Open Questions (if any)

Checks:

- Are acceptance criteria testable and unambiguous?
- Do the requirements align with the project's bootstrap stage (avoid over-engineering)?
- Is the artifact concise enough for direct use in planning or review?

MCP Integration:

- `explore`: Discover relevant code areas and domain models.
- `grep`: Verify terminology and detect potential conflicts.
- `sequential-thinking`: Structure the requirement elicitation and validation steps.
- `question`: Ask clarifying questions when stakeholder input is ambiguous.

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
