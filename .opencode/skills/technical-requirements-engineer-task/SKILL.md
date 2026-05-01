---
name: technical-requirements-engineer-task
description: Translate requirement artifacts into technical implementation plans, code snippets, and lint-aware validation.
---

Use this skill when converting requirement artifacts (from `requirements-engineer-task`) into concrete technical specifications, code proposals, and quality checks.

Workflow:

1. **Ingest Requirement**: Read the requirement artifact (title, user story, acceptance criteria).
2. **Code Base Analysis**:
   - Use `explore` to locate relevant modules, existing patterns, and extension points.
   - Use `grep` to identify existing implementations of similar features (e.g., tenant handling, task queuing).
3. **Technical Specification**:
   - Define the **implementation scope** (new files, modified files, deleted files).
   - Specify **data model changes** (new fields, tables, indexes).
   - Outline **API contract changes** (new endpoints, request/response models).
4. **Code Snippet Generation**:
   - Generate minimal, type-hinted Python code snippets for critical paths.
   - Ensure snippets follow the project's bootstrap-stage philosophy (no premature abstraction).
5. **Lint & Quality Checks**:
   - Integrate `ruff` (or `flake8`) to validate code style and catch common errors.
   - Use `sequential-thinking` to structure the lint workflow: prepare → execute → analyze → report.
   - If lint errors are found, propose fixes or flag them as open tasks.
6. **TODO Generation**:
   - Use `todo-write` to create actionable work items from the technical spec.
   - Each TODO should reference the requirement ID and include a short description.

Checks:

- Do the code snippets compile (syntax check) and follow existing project conventions?
- Are lint warnings addressed or explicitly documented as known issues?
- Is the technical spec scoped small enough for iterative delivery?

MCP Integration:

- `explore`: Map requirement to existing code structure.
- `grep`: Find similar patterns and avoid reinventing the wheel.
- `sequential-thinking`: Orchestrate the technical analysis and lint workflow.
- `todo-write`: Generate structured work items for implementation.
- `question`: Ask for clarification on technical trade-offs (e.g., "Should we use async or sync for this handler?").

Lint Integration (Optional but Recommended):

- Install `ruff` as a dev dependency if not already present.
- Run `ruff check <file>` on generated snippets.
- Report lint results as:
  - **Errors**: Must be fixed before implementation.
  - **Warnings**: Should be reviewed.
  - **Info**: Style suggestions.

Output Example:

```markdown
## Technical Spec: REQ-001 - Multi-Tenant Task Queue

### Implementation Scope
- **New Files**: `execqueue/models/tenant.py` (tenant model stub)
- **Modified Files**: `execqueue/models/task_execution.py` (add `tenant_id` field)

### Data Model Changes
```python
# execqueue/models/task_execution.py
class TaskExecution(Base):
    __tablename__ = "task_executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # NEW
    # ... other fields
```

### API Contract Changes
- **New Endpoint**: `POST /api/tasks` (requires `X-Tenant-ID` header)
- **Request Model**:
  ```python
  class TaskSubmitRequest(BaseModel):
      name: str
      payload: dict
  ```
- **Response Model**:
  ```python
  class TaskSubmitResponse(BaseModel):
      id: int
      tenant_id: str
      status: str
  ```

### Lint Results
- `ruff check execqueue/models/task_execution.py`:
  - ✅ No errors
  - ⚠️ Warning: `RUF001` - Consider using `str` instead of `String` for clarity (info only)

### Generated TODOs
1. [REQ-001] Add `tenant_id` field to `TaskExecution` model.
2. [REQ-001] Implement `POST /api/tasks` endpoint with tenant validation.
3. [REQ-001] Write pytest tests for tenant isolation.
```
