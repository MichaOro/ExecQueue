# Arbeitspaket 06 - API Endpoints für Error/Retry Management

## Ziel

Ergänzung der API um Endpoints für Error/Retry Management. Dies ist optional und nicht direkt in REQ-018 gefordert, aber hilfreich für Operational Visibility.

## Aufwand

~2h

## Fachlicher Kontext

REQ-018 fordert keine API-Endpoints explizit, aber für Operational Visibility wären folgende hilfreich:
- Query von Execution-Status mit Error-Details
- Trigger von Manual Retry (optional)
- Query von Stale Executions
- Trigger von Stale Processing

Die Codebase bietet bereits:
- FastAPI Router-Struktur in `execqueue/api/routes/`
- Bestehende Endpoints in `domain.py` und `system.py`
- Database Models für TaskExecution und Workflow

## Codebase-Kontext

### Relevante Artefakte

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/api/router.py` (16 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/api/routes/domain.py` (284 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/api/routes/system.py` (173 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/task_execution.py` (277 Zeilen)

### CODEBASE-INSIGHTS

1. **router.py Line 1-16**: Router-Registrierung für `system_router` und `domain_router`
2. **domain.py Line 130-256**: Task creation endpoint
3. **domain.py Line 260-284**: Task status endpoint
4. **system.py Line 1-173**: System restart endpoints

### CODEBASE-ASSUMPTIONS

1. FastAPI ist als Dev-Dependency installiert
2. Bestehende Endpoints folgen einem konsistenten Pattern

### CODEBASE-RISKS

1. **R-1**: FastAPI könnte nicht vollständig installiert sein (optional dependency)
2. **R-2**: Neue Endpoints könnten bestehende Routes brechen

## Voranalyse

### Anpassungsstellen

1. **`execqueue/api/routes/`**:
   - Neue Datei `error.py` oder `recovery.py` für Error/Retry Endpoints
   - Oder Erweiterung von `system.py`

2. **`execqueue/api/router.py`**:
   - Registrieren des neuen Routers

### Patterns

- RESTful Endpoints (GET, POST)
- Pydantic Request/Response Models
- Dependency Injection für Database Session

### Wiederverwendung

- Bestehende Router-Struktur verwenden
- Bestehende Pydantic Models verwenden (falls vorhanden)
- Database Session Dependency verwenden

### Risiken

- **R-1**: API-Endpoints könnten Race Conditions mit Runner-Logik verursachen
- **R-2**: Auth/Authorization ist möglicherweise nicht implemented

## Technical Specification

### Änderungen (empfohlen)

**`execqueue/api/routes/error.py`** (neu):

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from execqueue.db.session import get_session
from execqueue.models.task_execution import TaskExecution

router = APIRouter(prefix="/api/error", tags=["error-management"])

@router.get("/executions/{execution_id}")
async def get_execution_status(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """Get execution status with error details."""
    execution = await session.get(TaskExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return {
        "id": execution.id,
        "task_id": execution.task_id,
        "status": execution.status,
        "error_type": execution.error_type,
        "error_message": execution.error_message,
        "attempt": execution.attempt,
        "max_attempts": execution.max_attempts,
        "next_retry_at": execution.next_retry_at,
        "phase": execution.phase
    }

@router.post("/executions/{execution_id}/retry")
async def trigger_retry(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """Trigger manual retry for an execution."""
    # Validation: Check if retry is safe
    execution = await session.get(TaskExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    if execution.status != "FAILED":
        raise HTTPException(status_code=400, detail="Can only retry failed executions")
    
    # Reset execution for retry
    execution.status = "PENDING"
    execution.attempt = 0
    execution.error_type = None
    execution.error_message = None
    execution.next_retry_at = None
    session.commit()
    
    return {"message": "Retry scheduled", "execution_id": execution.id}

@router.get("/stale")
async def list_stale_executions(
    session: AsyncSession = Depends(get_session)
):
    """List all stale executions."""
    from execqueue.runner.error_classification import find_stale_executions
    
    stale = await find_stale_executions(session, thresholds=DEFAULT_THRESHOLDS)
    return {
        "count": len(stale),
        "executions": [
            {
                "id": e.id,
                "task_id": e.task_id,
                "status": e.status,
                "heartbeat_at": e.heartbeat_at,
                "updated_at": e.updated_at
            }
            for e in stale
        ]
    }

@router.post("/recovery/stale")
async def trigger_stale_processing(
    session: AsyncSession = Depends(get_session)
):
    """Trigger stale execution processing."""
    from execqueue.runner.recovery import RecoveryService
    
    recovery = RecoveryService()
    await recovery.process_stale_executions(session)
    session.commit()
    
    return {"message": "Stale processing completed"}
```

**`execqueue/api/router.py`**:

```python
from fastapi import APIRouter
from execqueue.api.routes.system import system_router
from execqueue.api.routes.domain import domain_router
from execqueue.api.routes.error import router as error_router  # Neu

router = APIRouter()

router.include_router(system_router)
router.include_router(domain_router)
router.include_router(error_router)  # Neu
```

### Flow-Integration

```
API Request → Router → Handler → Database Query/Update → Response
    ↓
Optional: Trigger RecoveryService → Process Executions
```

### Seiteneffekte

- Database Queries für Execution-Status
- Database Updates für Manual Retry
- RecoveryService-Aufruf für Stale Processing

### Tests

- Unit Tests für API Endpoints
- Integration Tests mit Test-Database
- Test für Error-Handling in Endpoints

### Neue Module + Begründung

- **`execqueue/api/routes/error.py`**: Neue Route für Error/Retry Management

## Umsetzungsspielraum

### Flexible Bereiche

- Entscheidung: Separate Route (`error.py`) vs. Erweiterung von `system.py`
- Entscheidung: Welche Endpoints implementiert werden (nicht alle müssen)
- Decision: Request/Response Models (Pydantic vs. dict)

### Fixe Bereiche

- **Nicht verändern**: Bestehende Router-Struktur
- **Nicht verändern**: Bestehende Endpoints
- **Muss erhalten bleiben**: Consistente Naming Convention

## Umsetzungsschritte

1. **Code Review** von `router.py`, `domain.py`, `system.py`
2. **Entscheidung**: Welche Endpoints implementiert werden
3. **Implementieren** von `execqueue/api/routes/error.py`
4. **Registrieren** des neuen Routers in `router.py`
5. **Tests schreiben** für neue Endpoints
6. **Validierung**: Bestehende Tests laufen lassen

## Abhängigkeiten

- **FastAPI**: Muss installiert sein (optional dependency)
- **DB**: `TaskExecution` Modell muss verfügbar sein

## Akzeptanzkriterien

- [ ] Endpoint `GET /api/error/executions/{id}` funktioniert
- [ ] Endpoint `POST /api/error/executions/{id}/retry` funktioniert (optional)
- [ ] Endpoint `GET /api/error/stale` funktioniert (optional)
- [ ] Endpoint `POST /api/error/recovery/stale` funktioniert (optional)
- [ ] Neue Route ist in `router.py` registriert
- [ ] Unit Tests für Endpoints bestehen
- [ ] Integration Tests bestehen

## Entwickler-/Agent-Validierung

### Zu prüfende Dateien

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/api/router.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/api/routes/domain.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/api/routes/system.py`

### Kritische Annahmen

1. FastAPI ist importierbar
2. Database Session Dependency ist korrekt konfiguriert

### Manuelle Checks

1. API mit `curl` oder `httpie` testen
2. OpenAPI Docs (`/docs`) auf neue Endpoints prüfen

## Risiken

| Risiko | Auswirkung | Gegenmaßnahme |
|--------|------------|---------------|
| Missing Dependency | FastAPI nicht installiert | In pyproject.toml prüfen |
| Race Condition | API + Runner Konflikt | Optimistic Locking, Validation |
| Missing Auth | Unauthorised Access | Auth/Authorization prüfen (falls existent) |

## Zielpfad

`/home/ubuntu/workspace/IdeaProjects/ExecQueue/docs/REQ-018/06_api_endpoints.md`
