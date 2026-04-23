---
name: api-generator
description: Generate FastAPI endpoints following ExecQueue patterns
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: development
---

## Was ich tue
- Erstelle FastAPI Router-Dateien im `execqueue/api/` Verzeichnis
- Implementiere CRUD-Operationen mit SQLModel
- Integriere mit bestehenden Services
- Füge korrekte Type Hints und Docstrings hinzu
- Erstelle zugehörige Tests
- Dokumentiere APIs mit OpenAPI-Schema
- Stelle Security- und Validation-Konformität sicher

## Wann du mich verwendest
- Neue Ressourcen: "Create a new API endpoint for X"
- CRUD-Operationen: "Add create/read/update/delete for this model"
- Integration: "Connect this endpoint to the existing service layer"
- Filter/Search: "Add filtering and search capabilities to tasks endpoint"
- Bulk Operations: "Create bulk create/update endpoints"

## Projekt-Patterns

### Router-Struktur
```
execqueue/api/
  tasks.py
  requirements.py
  work_packages.py
  queue.py
```

### Endpoint-Template
```python
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import AsyncSession, select, joinedload

from execqueue.db.session import get_session
from execqueue.models.task import Task, TaskCreate, TaskUpdate
from execqueue.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new task.
    
    Creates a new task with the provided data.
    """
    # Validate input
    if not task.title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title is required"
        )
    
    # Use service layer
    created_task = await task_service.create_task(session, task)
    return created_task

@router.get("/", response_model=list[Task])
async def list_tasks(
    skip: int = 0,
    limit: int = 100,
    priority: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """List all tasks with optional filtering.
    
    - **skip**: Number of tasks to skip
    - **limit**: Maximum number of tasks to return
    - **priority**: Filter by priority (HIGH, MEDIUM, LOW)
    """
    stmt = select(Task).offset(skip).limit(limit)
    
    if priority:
        stmt = stmt.where(Task.priority == priority)
    
    # Avoid N+1 queries
    stmt = stmt.options(joinedload(Task.requirements))
    
    result = await session.exec(stmt)
    return result.all()

@router.get("/{task_id}", response_model=Task)
async def get_task(
    task_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific task by ID."""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.exec(stmt)
    task = result.first()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found"
        )
    
    return task

@router.patch("/{task_id}", response_model=Task)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update an existing task."""
    # Manually set updated_at
    from datetime import datetime, timezone
    task_update.updated_at = datetime.now(timezone.utc)
    
    updated_task = await task_service.update_task(session, task_id, task_update)
    
    if not updated_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found"
        )
    
    return updated_task

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Delete a task by ID."""
    deleted = await task_service.delete_task(session, task_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found"
        )
    
    return None
```

### Dependencies
- `get_session()` für Datenbank
- `get_current_user()` für Auth (falls implementiert)
- Custom Dependencies für Filter/Validation

### Services
- Geschäftslogik in `execqueue/services/`
- API-Routers sollten nur HTTP-Handling machen
- Service-Funktionen testbar halten
- Keine direkten DB-Queries in API-Endpoints

### Testing
- Test-DB URL aus `.env`
- `EXECQUEUE_TEST_MODE` setzen
- Test-Fixtures in `tests/conftest.py`
- Alle Tests müssen bestehen
- Coverage ≥ 85% für API

### Dokumentierte Known Issues beachten
1. **`updated_at` manuell setzen**
   → In Update-Endpoints explizit setzen

2. **`is_test` Filter konsistent anwenden**
   → Query-Filterung für Test-Mode

3. **N+1 Queries vermeiden**
   → `joinedload()` für Relationships

4. **SQL Logging bei Bedarf aktivieren**
   → `ECHO_SQL=true` für Debugging

## Security Best Practices

### Input Validation
```python
class TaskCreate(SQLModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    priority: Priority = Priority.MEDIUM
```

### Error Handling
```python
try:
    task = await task_service.create_task(session, task_data)
except ValidationError as e:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=e.errors()
    )
```

### Authentication (wenn implementiert)
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme)
) -> User:
    # Validate JWT token
    pass

@router.get("/me", response_model=User)
async def get_current_user_info(
    user: User = Depends(get_current_user)
):
    return user
```

## Workflow

1. **Anforderung verstehen**: Was soll der Endpoint tun?
2. **Bestehende Patterns analysieren**: Ähnliche Endpoints prüfen
3. **Request/Response Models erstellen**: Falls nicht vorhanden
4. **Service-Layer implementieren**: Geschäftslogik separieren
5. **Endpoint erstellen**: CRUD-Operationen nach Template
6. **Tests schreiben**: Unit- und Integration-Tests
7. **Documentation hinzufügen**: Docstrings und OpenAPI
8. **Review anfordern**: @code-reviewer für Best Practices

## Troubleshooting

### Endpoint nicht erreichbar
→ Router in `execqueue/main.py` korrekt mounten:
```python
app.include_router(tasks_router, prefix="/api")
```

### Validation funktioniert nicht
→ Pydantic/SQLModel Models korrekt definieren
→ Type Hints verwenden

### Async/await Fehler
→ Alle DB-Operationen mit `await`
→ `async def` für alle Endpoint-Funktionen
