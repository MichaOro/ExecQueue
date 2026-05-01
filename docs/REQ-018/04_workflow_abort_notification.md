# Arbeitspaket 04 - Workflow Abort & Orchestrator Notification

## Ziel

Implementierung des Workflow-Abort-Mechanismus bei Max-Retry-Exhaustion oder Non-Recoverable Errors. Integration mit dem Orchestrator für Benachrichtigung.

## Aufwand

~2h

## Fachlicher Kontext

REQ-018 verlangt:
- Bei `retry_count >= max_retries`: Workflow-Abort
- Non-recoverable Fehler: Sofortiger Workflow-Abort
- Workflow-Status wird auf `failed` aktualisiert
- Orchestrator wird über Workflow-Abort informiert

Die Codebase bietet bereits:
- `WorkflowAbortError` Exception (in `error_classification.py`)
- `Workflow` Modell mit `status` (RUNNING, DONE, FAILED)
- Orchestrator Recovery mit `recover_running_workflows()`
- `RunnerManager` für Runner-Steuerung

## Codebase-Kontext

### Relevante Artefakte

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/error_classification.py` (578 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/orchestrator/main.py` (492 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/orchestrator/workflow_models.py` (84 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py` (736 Zeilen)

### CODEBASE-INSIGHTS

1. **error_classification.py Line 540-552**: `WorkflowAbortError` Exception definiert
2. **workflow_models.py Line 19-26**: `WorkflowStatus` enum mit FAILED
3. **orchestrator/main.py Line 256-349**: `recover_running_workflows()` für Recovery
4. **recovery.py Line 81-199**: `RecoveryService.handle_error()` entscheidet über Abort

### CODEBASE-ASSUMPTIONS

1. `WorkflowAbortError` wird bereits irgendwo raised
2. Der Orchestrator fängt `WorkflowAbortError` und aktualisiert Workflow-Status

### CODEBASE-RISKS

1. **R-1**: `WorkflowAbortError` ist definiert, aber nicht im Execution-Flow verwendet
2. **R-2**: Workflow-Status-Update ist möglicherweise nicht implementiert
3. **R-3**: Orchestrator-Notification ist möglicherweise nicht integriert

## Voranalyse

### Anpassungsstellen

1. **`execqueue/runner/recovery.py`**:
   - In `handle_error()`: Bei Max-Retry-Exhaustion oder Non-Recoverable `WorkflowAbortError` raise
   - Workflow-Status auf FAILED setzen

2. **`execqueue/orchestrator/main.py`**:
   - Exception Handler für `WorkflowAbortError`
   - Workflow-Status-Update bei Error

3. **`execqueue/runner/main.py`**:
   - Exception Propagation von `WorkflowAbortError` zum Orchestrator

### Patterns

- Exception-based Abort Signal (`WorkflowAbortError`)
- Workflow-Status-Transition RUNNING → FAILED
- Orchestrator Notification via Exception oder Callback

### Wiederverwendung

- `WorkflowAbortError` direkt verwenden
- `Workflow` Modell direkt verwenden
- `recover_running_workflows()` für Recovery nutzen

### Risiken

- **R-1**: Workflow-Status-Update könnte Race Conditions verursachen
- **R-2**: Orchestrator könnte nicht auf Abort reagieren

## Technical Specification

### Änderungen (empfohlen)

**`execqueue/runner/recovery.py` - handle_error()**:

```python
async def handle_error(self, session, execution, exception, phase):
    error_type = classify_error(exception, phase, context)
    decision = calculate_retry_decision(execution, error_type, phase, retry_matrix)
    
    if not decision.should_retry:
        # Max retries exceeded oder non-recoverable
        execution.status = "FAILED"
        execution.error_type = error_type.value
        execution.error_message = str(exception)
        session.commit()
        
        # Workflow-Status aktualisieren
        workflow = await self._get_workflow_for_execution(session, execution)
        if workflow:
            workflow.status = "FAILED"
            workflow.error_message = f"Task {execution.task_id} failed: {str(exception)}"
            session.commit()
        
        # WorkflowAbortError raise für Propagation
        raise WorkflowAbortError(
            message=f"{error_type.value} error: {exception}",
            workflow_id=workflow.id if workflow else None,
            task_id=execution.task_id
        )
    
    # Retry logic...
```

**`execqueue/orchestrator/main.py` - Exception Handler**:

```python
# In _prepare_task_context() oder workflow processing loop:
try:
    result = await runner.execute()
except WorkflowAbortError as e:
    # Workflow bereits auf FAILED gesetzt von RecoveryService
    # Orchestrator wird informiert
    logger.error(f"Workflow aborted: {e.workflow_id}, task: {e.task_id}")
    # Optional: Cleanup, Alerting, etc.
```

### Flow-Integration

```
Task Error → RecoveryService.handle_error()
    ↓
calculate_retry_decision() → should_retry = NO
    ↓
execution.status = FAILED
workflow.status = FAILED
WorkflowAbortError raised
    ↓
Orchestrator catches → Logging/Cleanup
```

### Seiteneffekte

- Database Updates für `execution.status`, `workflow.status`
- Exception Propagation zum Orchestrator
- Eventuelle Runner-Terminierung

### Tests

- Unit Test für `WorkflowAbortError` raise bei Max-Retry
- Integration Test für Workflow-Status-Transition RUNNING → FAILED
- Test für Non-Recoverable Error → immediate Abort

### Neue Module + Begründung

- **Keine** - bestehende Infrastruktur verwenden

## Umsetzungsspielraum

### Flexible Bereiche

- Entscheidung: Workflow-Status-Update in `RecoveryService` oder im Exception Handler
- Entscheidung: Wie Orchestrator informiert wird (Exception, Callback, Polling)
- Decision: Additional Cleanup-Actions bei Workflow-Abort

### Fixe Bereiche

- **Nicht verändern**: `WorkflowStatus` enum ohne zwingenden Grund
- **Nicht verändern**: `WorkflowAbortError` Signatur
- **Muss erhalten bleiben**: Workflow-Status auf FAILED bei Abort

## Umsetzungsschritte

1. **Code Review** von `recovery.py`, `orchestrator/main.py`, `workflow_models.py`
2. **Implementieren** von `WorkflowAbortError` raise in `RecoveryService.handle_error()`
3. **Implementieren** von Workflow-Status-Update auf FAILED
4. **Implementieren** von Orchestrator Exception Handler
5. **Tests schreiben** für Abort-Flow
6. **Validierung**: Bestehende Tests laufen lassen

## Abhängigkeiten

- **AP-02**: Retry Mechanism muss vollständig sein
- **DB**: `Workflow` Modell muss `status` Feld haben

## Akzeptanzkriterien

- [ ] Bei `retry_count >= max_retries`: `WorkflowAbortError` wird raised
- [ ] Bei Non-Recoverable Error: Sofortiger `WorkflowAbortError`
- [ ] Workflow-Status wird auf FAILED aktualisiert
- [ ] Orchestrator wird über `WorkflowAbortError` informiert
- [ ] `error_message` wird in Workflow persistiert
- [ ] Logging enthält `workflow_id`, `task_id`, `error_type`
- [ ] Unit Test für Max-Retry Abort besteht
- [ ] Integration Test für Workflow-Status-Transition besteht

## Entwickler-/Agent-Validierung

### Zu prüfende Dateien

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/orchestrator/main.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/orchestrator/workflow_models.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/error_classification.py` (WorkflowAbortError)

### Kritische Annahmen

1. `WorkflowAbortError` wird korrekt vom Orchestrator gefangen
2. Database Transaction für Execution + Workflow Update ist atomar

### Manuelle Checks

1. REQ-018 Abschnitt 3.1 ERR-003, ERR-004, ERR-005, ERR-006 mit Implementation abgleichen
2. Workflow-Status-Transition Diagramm prüfen (RUNNING → FAILED)

## Risiken

| Risiko | Auswirkung | Gegenmaßnahme |
|--------|------------|---------------|
| Missing Abort | Workflow läuft weiter | Exception Handler testen |
| Race Condition | Status-Konflikt | Optimistic Locking, Transaction |
| Lost Notification | Orchestrator weiß nicht | Logging, Monitoring aktivieren |

## Zielpfad

`/home/ubuntu/workspace/IdeaProjects/ExecQueue/docs/REQ-018/04_workflow_abort_notification.md`
