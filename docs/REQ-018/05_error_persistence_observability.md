# Arbeitspaket 05 - Error Persistence & Observability

## Ziel

Sicherstellen, dass alle Fehlerdaten korrekt persistiert werden und in Logs/Metrics sichtbar sind. Nutzung der bestehenden Observability-Infrastruktur.

## Aufwand

~2h

## Fachlicher Kontext

REQ-018 verlangt:
- Fehler werden in `task_execution.error_message` und `error_type` persistiert
- Fehler-Logs enthalten `workflow_id`, `task_id`, `retry_count`
- Metrics für Retries, Failures, Stale Executions

Die Codebase bietet bereits:
- `TaskExecution` Modell mit `error_type`, `error_message`, `attempt` Feldern
- `StructuredFormatter` für JSON-Logging mit Correlation IDs
- `log_phase_event()` für Phase-Event-Logging
- `ExecutionMetrics` für Metrics-Sammlung

## Codebase-Kontext

### Relevante Artefakte

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/task_execution.py` (277 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/observability/logging.py` (590 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py` (736 Zeilen)

### CODEBASE-INSIGHTS

1. **task_execution.py Line 136-189**: `error_type`, `error_message`, `attempt`, `next_retry_at` Felder
2. **logging.py Line 39-146**: `StructuredFormatter` mit Correlation ID
3. **logging.py Line 159-206**: `log_phase_event()` mit execution_id, task_id, runner_id, phase
4. **logging.py Line 324-460**: `ExecutionMetrics` mit retry/failed counters

### CODEBASE-ASSUMPTIONS

1. Logging wird bereits an allen relevanten Stellen verwendet
2. Metrics werden bereits gesammelt und exportiert

### CODEBASE-RISKS

1. **R-1**: Fehler-Logs könnten fehlende Correlation IDs haben
2. **R-2**: Metrics könnten nicht alle REQ-018 Szenarien abdecken

## Voranalyse

### Anpassungsstellen

1. **`execqueue/runner/recovery.py`**:
   - Logging bei Error Classification
   - Logging bei Retry Decision
   - Logging bei Workflow Abort

2. **`execqueue/observability/logging.py`**:
   - Eventuell zusätzliche Metrics für REQ-018 spezifische Szenarien

### Patterns

- Correlation ID Propagation (workflow_id, task_id, execution_id, runner_id)
- Structured JSON Logging
- Phase Event Logging
- Metrics Counter für Retry/Failed/Stale

### Wiederverwendung

- `StructuredFormatter` direkt verwenden
- `log_phase_event()` direkt verwenden
- `ExecutionMetrics` direkt verwenden

### Risiken

- **R-1**: Logging könnte Performance-Overhead verursachen
- **R-2**: Sensitive Data könnte in Logs泄露 (redaction prüfen)

## Technical Specification

### Änderungen (empfohlen)

**`execqueue/runner/recovery.py` - handle_error()**:

```python
async def handle_error(self, session, execution, exception, phase):
    error_type = classify_error(exception, phase, context)
    decision = calculate_retry_decision(execution, error_type, phase, retry_matrix)
    
    # Logging mit Correlation IDs
    log_phase_event(
        level="ERROR",
        phase=phase,
        event="error_detected",
        execution_id=execution.id,
        task_id=execution.task_id,
        workflow_id=execution.workflow_id,  # Falls verfügbar
        runner_id=execution.runner_uuid,
        error_type=error_type.value,
        retry_count=execution.attempt,
        max_retries=execution.max_attempts,
        should_retry=decision.should_retry,
        delay_seconds=decision.delay_seconds if decision.should_retry else None
    )
    
    # Error Persistence
    execution.error_type = error_type.value
    execution.error_message = str(exception)
    execution.attempt += 1 if decision.should_retry else 0
    
    if decision.should_retry:
        execution.next_retry_at = decision.next_retry_at
        # Metrics: retry_scheduled++
    else:
        execution.status = "FAILED"
        # Metrics: retry_exhausted++ or non_recoverable_error++
    
    session.commit()
```

**Metrics-Erweiterung** (falls nötig):

```python
# In execqueue/observability/logging.py - ExecutionMetrics
@dataclass
class ExecutionMetrics:
    # Existing...
    retries_scheduled: int = 0
    retries_exhausted: int = 0
    stale_detected: int = 0
    non_recoverable_errors: int = 0  # Neu
    workflow_aborts: int = 0  # Neu
```

### Flow-Integration

```
Error Occurs → classify_error() → log_phase_event() (ERROR level)
    ↓
calculate_retry_decision() → log_phase_event() (INFO/WARN level)
    ↓
Persistence (error_type, error_message, attempt) → Metrics Update
```

### Seiteneffekte

- Database Updates für Error-Felder
- Log-Ausgabe (JSON)
- Metrics-Inkrementierung

### Tests

- Unit Test für Logging mit Correlation IDs
- Integration Test für Error Persistence
- Test für Metrics-Sammlung

### Neue Module + Begründung

- **Keine** - bestehende Infrastruktur verwenden
- **Optional**: Neue Metrics-Felder in `ExecutionMetrics`

## Umsetzungsspielraum

### Flexible Bereiche

- Entscheidung: Welche Log-Level für welche Szenarien (ERROR, WARN, INFO)
- Decision: Welche zusätzlichen Metrics eingeführt werden
- Entscheidung: Logging-Format (JSON vs. human-readable)

### Fixe Bereiche

- **Nicht verändern**: `StructuredFormatter` ohne Tests
- **Nicht verändern**: Correlation ID Struktur
- **Muss erhalten bleiben**: `workflow_id`, `task_id`, `retry_count` in Logs

## Umsetzungsschritte

1. **Code Review** von `logging.py` und `recovery.py`
2. **Sicherstellen**, dass `log_phase_event()` an allen Error-Stellen aufgerufen wird
3. **Sicherstellen**, dass `error_type`, `error_message`, `attempt` korrekt persistiert werden
4. **Eventuell**: `ExecutionMetrics` um REQ-018 spezifische Zähler erweitern
5. **Tests schreiben** für Logging und Persistence
6. **Validierung**: Bestehende Tests laufen lassen

## Abhängigkeiten

- **AP-02**: Retry Mechanism muss Logging integrieren
- **AP-03**: Stale Detection muss Logging integrieren
- **AP-04**: Workflow Abort muss Logging integrieren

## Akzeptanzkriterien

- [ ] `error_type` wird in `task_execution` persistiert
- [ ] `error_message` wird in `task_execution` persistiert
- [ ] `retry_count` (attempt) wird bei jedem Error aktualisiert
- [ ] Logs enthalten `workflow_id` (falls verfügbar)
- [ ] Logs enthalten `task_id`
- [ ] Logs enthalten `retry_count`
- [ ] Logs enthalten `error_type`
- [ ] Metrics für retries_scheduled bestehen
- [ ] Metrics für retries_exhausted bestehen
- [ ] Structured JSON Logging funktioniert
- [ ] Correlation IDs werden propagiert

## Entwickler-/Agent-Validierung

### Zu prüfende Dateien

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/task_execution.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/observability/logging.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py`

### Kritische Annahmen

1. `log_phase_event()` wird bereits in `RecoveryService` verwendet
2. Database Schema hat `error_type`, `error_message` Felder

### Manuelle Checks

1. REQ-018 Abschnitt 3.1 ERR-007, ERR-009 mit Implementation abgleichen
2. Logging Output auf Correlation IDs prüfen
3. Database Records nach Error auf Persistierung prüfen

## Risiken

| Risiko | Auswirkung | Gegenmaßnahme |
|--------|------------|---------------|
| Missing Logs | Debugging erschwert | Logging an allen Error-Stellen prüfen |
| Missing Metrics | Monitoring lückenhaft | Metrics-Export prüfen |
| Sensitive Data | Security Issue | Redaction in `StructuredFormatter` prüfen |

## Zielpfad

`/home/ubuntu/workspace/IdeaProjects/ExecQueue/docs/REQ-018/05_error_persistence_observability.md`
