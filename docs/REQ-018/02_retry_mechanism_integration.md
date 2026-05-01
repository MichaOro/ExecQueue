# Arbeitspaket 02 - Retry Mechanism Integration

## Ziel

Integration des Retry-Mechanismus in den Runner-Execution-Flow. Nutzung der bestehenden `RecoveryService` und `RetryMatrix` Infrastruktur.

## Aufwand

~2h

## Fachlicher Kontext

REQ-018 verlangt:
- Pro-Task Retry bis `max_retries` (aus DB)
- Exponentielles Backoff zwischen Retries
- Nach Überschreiten von `max_retries`: Workflow-Abort

Die Codebase bietet bereits:
- `RecoveryService.handle_error()` mit Retry-Entscheidungslogik
- `RetryMatrix` mit phasen-spezifischen Policies
- `calculate_retry_decision()` für Exponential Backoff
- `TaskExecution` Modell mit `attempt`, `max_attempts`, `next_retry_at`

## Codebase-Kontext

### Relevante Artefakte

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py` (736 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/main.py` (331 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/task_execution.py` (277 Zeilen)

### CODEBASE-INSIGHTS

1. **recovery.py Line 81-199**: `RecoveryService.handle_error()` implementiert bereits die Retry-Logik
2. **recovery.py Line 281-362**: `calculate_retry_decision()` berechnet Exponential Backoff
3. **main.py Line 113-169**: `_process_execution()` ist der Execution-Flow-Hook
4. **task_execution.py Line 136-189**: Retry-Felder sind bereits im Modell

### CODEBASE-ASSUMPTIONS

1. `RecoveryService` wird bereits im Runner verwendet
2. Die `attempt` Zählung wird bei jedem Retry inkrementiert

### CODEBASE-RISKS

1. **R-1**: `RecoveryService` ist möglicherweise nicht in den Haupt-Execution-Flow integriert
2. **R-2**: Die `next_retry_at` Scheduling-Logik ist möglicherweise nicht aktiv

## Voranalyse

### Anpassungsstellen

1. **`execqueue/runner/main.py`**:
   - Integration von `RecoveryService.handle_error()` in `_process_execution()`
   - Exception Handling um Retry-Logik erweitern

2. **`execqueue/models/task_execution.py`**:
   - Sicherstellen, dass `attempt`, `max_attempts`, `next_retry_at` korrekt aktualisiert werden

### Patterns

- Phase-specific Retry Policies (claim, session, dispatch, stream, result, adoption)
- Exponential Backoff mit `base_delay * (2 ^ retry_count)`
- `next_retry_at` für zeitgesteuerte Retries

### Wiederverwendung

- `RecoveryService` direkt verwenden
- `RetryMatrix` direkt verwenden
- `calculate_retry_decision()` direkt verwenden

### Risiken

- **R-1**: Integration könnte bestehende Error-Handling-Logik brechen
- **R-2**: Race Conditions bei gleichzeitigen Retries

## Technical Specification

### Änderungen (empfohlen)

**`execqueue/runner/main.py`**:

```python
# In _process_execution() oder initialize_execution():
try:
    result = await execute_task(task)
    return result
except Exception as e:
    # RecoveryService nutzen
    recovery_service = RecoveryService()
    decision = await recovery_service.handle_error(
        session=session,
        execution=execution,
        exception=e,
        phase=current_phase
    )
    
    if decision.should_retry:
        # Execution updaten
        execution.attempt += 1
        execution.next_retry_at = decision.next_retry_at
        execution.error_type = decision.error_type
        execution.error_message = str(e)
        session.commit()
        return None  # Retry scheduled
    else:
        # Max retries exceeded oder non-recoverable
        execution.status = "FAILED"
        execution.error_type = decision.error_type
        execution.error_message = str(e)
        session.commit()
        raise WorkflowAbortError(...)
```

### Flow-Integration

```
Task Execution → Exception → RecoveryService.handle_error()
    ↓
calculate_retry_decision() → should_retry?
    ↓
YES: attempt++, next_retry_at, commit, retry
NO: status=FAILED, WorkflowAbortError
```

### Seiteneffekte

- Database Updates für `attempt`, `error_type`, `error_message`, `next_retry_at`
- Eventuelle Workflow-Status-Änderung auf "FAILED"

### Tests

- Unit Tests für Retry-Entscheidungslogik
- Integration Test für Retry-Flow im Runner
- Test für Max-Retry Exhaustion

### Neue Module + Begründung

- **Keine** - bestehende Infrastruktur verwenden

## Umsetzungsspielraum

### Flexible Bereiche

- Entscheidung, ob Retry-Logik in `_process_execution()` oder separater Methode integriert wird
- Entscheidung, ob `RecoveryService` als Singleton oder pro-Request instanziiert wird
- Timing der Database Updates (vor oder nach Retry-Entscheidung)

### Fixe Bereiche

- **Nicht verändern**: `RecoveryService.handle_error()` Signatur ohne zwingenden Grund
- **Nicht verändern**: `TaskExecution` Modell-Felder
- **Muss erhalten bleiben**: `attempt` Inkrementierung vor Retry

## Umsetzungsschritte

1. **Code Review** von `execqueue/runner/main.py` und `execqueue/runner/recovery.py`
2. **Identifizieren** des optimalen Integration Points im Execution-Flow
3. **Implementieren** der Exception-Handling-Logik mit `RecoveryService`
4. **Sicherstellen**, dass Database Updates korrekt durchgeführt werden
5. **Tests schreiben** für Retry- und Exhaustion-Flows
6. **Validierung**: Bestehende Tests laufen lassen

## Abhängigkeiten

- **AP-01**: Error Classification muss vollständig sein
- **DB**: `TaskExecution` Modell muss `attempt`, `max_attempts`, `next_retry_at` Felder haben

## Akzeptanzkriterien

- [ ] Recoverable Fehler führen zu Retry (bis `max_retries`)
- [ ] Non-recoverable Fehler führen zu sofortigem Abort
- [ ] Bei `retry_count >= max_retries`: Workflow-Abort
- [ ] `attempt` wird bei jedem Retry inkrementiert
- [ ] `next_retry_at` wird mit Exponential Backoff berechnet
- [ ] `error_type` und `error_message` werden persistiert
- [ ] Unit Tests für Retry-Logik bestehen
- [ ] Integration Test für Max-Retry Exhaustion besteht

## Entwickler-/Agent-Validierung

### Zu prüfende Dateien

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/main.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/task_execution.py`

### Kritische Annahmen

1. `RecoveryService.handle_error()` wird bereits korrekt aufgerufen
2. Die Database Session ist korrekt verwaltet (commit/Rollback)

### Manuelle Checks

1. REQ-018 Abschnitt 5 "Retry-Logik" mit Implementation abgleichen
2. `RetryMatrix` Konfiguration mit REQ-018 "Exponentielles Backoff" abgleichen

## Risiken

| Risiko | Auswirkung | Gegenmaßnahme |
|--------|------------|---------------|
| Race Condition | Doppelte Ausführung | Optimistic Locking auf `attempt` |
| Zu lange Backoff | Workflow-Dauer | `max_delay` Konfiguration prüfen |
| Missing Integration | Retry funktioniert nicht | End-to-End Test schreiben |

## Zielpfad

`/home/ubuntu/workspace/IdeaProjects/ExecQueue/docs/REQ-018/02_retry_mechanism_integration.md`
