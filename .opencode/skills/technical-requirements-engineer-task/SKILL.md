---
name: technical-requirements-engineer-task
description: Translate requirement artifacts into technical implementation plans, code snippets, and lint-aware validation.
---

Use this skill when converting requirement artifacts from `requirements-engineer-task` into concrete technical specifications, code proposals, and quality checks.

Workflow:

1. **Ingest Requirement**: Read the requirement artifact including title, user story, and acceptance criteria.
2. **Code Base Analysis**:
   - Use repository search and targeted file reads to locate relevant modules, existing patterns, and extension points.
   - Identify existing implementations of similar features such as tenant handling, task queuing, workflow persistence, or OpenCode integration.
3. **Technical Specification**:
   - Define the **implementation scope** including new files, modified files, and any intentionally untouched areas.
   - Specify **data model changes** such as new fields, tables, or indexes.
   - Outline **API contract changes** such as endpoints, request models, and response models.
4. **Code Snippet Generation**:
   - Generate minimal, type-hinted Python code snippets only for the critical paths.
   - Ensure snippets follow the project's preference for explicit, readable code over speculative abstraction.
5. **Lint & Quality Checks**:
   - Integrate `ruff` or `flake8` to validate code style and catch common issues.
   - Use `sequential-thinking` to structure the lint workflow: prepare -> execute -> analyze -> report.
   - If lint errors are found, propose fixes or flag them as open tasks.
6. **Work Breakdown**:
   - End with a short actionable implementation checklist.
   - Each checklist item should reference the requirement ID and include a short description.

Checks:

- Do the code snippets compile and follow existing project conventions?
- Are lint warnings addressed or explicitly documented as known issues?
- Is the technical spec scoped small enough for iterative delivery?

Recommended tools:

- repository search and file reads to map the requirement to existing code structure
- `sequential-thinking` to orchestrate the technical analysis and lint workflow
- concise clarification questions when technical trade-offs are still open

Lint Integration (Optional but Recommended):

- Ensure `ruff` is available as a dev dependency.
- Run `ruff check <file>` on generated snippets where feasible.
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
  - No errors
  - Warning: `RUF001` - Consider using `str` instead of `String` for clarity (info only)

### Implementation Checklist
1. [REQ-001] Add `tenant_id` field to `TaskExecution` model.
2. [REQ-001] Implement `POST /api/tasks` endpoint with tenant validation.
3. [REQ-001] Write pytest tests for tenant isolation.
```
