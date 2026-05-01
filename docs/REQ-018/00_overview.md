# REQ-018 - Arbeitspaket Übersicht

## Zusammenfassung

Dieses Dokument fasst alle Arbeitspakete für REQ-018 (Error Handling & Retry Mechanism) zusammen.

## Arbeitspakete

| # | Titel | Aufwand | Status | Abhängigkeiten |
|---|-------|---------|--------|----------------|
| 01 | Error Classification & Typen | ~2h | pending | - |
| 02 | Retry Mechanism Integration | ~2h | pending | AP-01 |
| 03 | Stale Execution Detection & Recovery | ~2h | pending | AP-01 |
| 04 | Workflow Abort & Orchestrator Notification | ~2h | pending | AP-02 |
| 05 | Error Persistence & Observability | ~2h | pending | AP-02, AP-03, AP-04 |
| 06 | API Endpoints für Error/Retry Management | ~2h | optional | - |

**Gesamtaufwand**: ~10h (ohne AP-06)

## Codebase Insights

### Bereits existierende Infrastruktur

Die Codebase bietet eine **umfassende Error Handling & Retry Infrastruktur**:

1. **Error Classification** (`execqueue/runner/error_classification.py` - 578 Zeilen):
   - `ErrorType` Enum (TRANSIENT, PERMANENT, CONFLICT, TIMEOUT, etc.)
   - `classify_error()` mit Pattern-basiertem Matching
   - `is_retryable` Property
   - `RetryMatrix` mit phasen-spezifischen Policies
   - `calculate_retry_decision()` für Exponential Backoff
   - `is_execution_stale()` und `find_stale_executions()`
   - Custom Exceptions (ConflictError, ValidationError, ContractViolationError, WorkflowAbortError)

2. **Recovery Service** (`execqueue/runner/recovery.py` - 736 Zeilen):
   - `RecoveryService.handle_error()` mit Retry-Entscheidungslogik
   - `RecoveryService.handle_stale_execution()` für Stale Recovery
   - `RecoveryService.process_stale_executions()` für Batch-Verarbeitung
   - `WriteTaskRecovery` mit Git Pre-Checks

3. **Database Models**:
   - `TaskExecution` mit `attempt`, `max_attempts`, `error_type`, `error_message`, `next_retry_at`
   - `Workflow` mit `status` (RUNNING, DONE, FAILED)
   - Indexe für Stale Detection (`heartbeat_at`, `updated_at`)

4. **Observability** (`execqueue/observability/logging.py` - 590 Zeilen):
   - `StructuredFormatter` mit Correlation IDs
   - `log_phase_event()` für Phase-Event-Logging
   - `ExecutionMetrics` mit retry/failed counters

### Haupt-Gaps

1. **API Exposure**: Keine Endpoints für Error/Retry Management
2. **Workflow-Level Integration**: Workflow-Status-Update bei Error nicht vollständig
3. **Automation**: Stale Detection nicht automatisiert
4. **Integration**: `RecoveryService` nicht vollständig in Runner-Loop integriert

## Empfohlene Reihenfolge

1. **AP-01** (Error Classification) - Basis für alle anderen Pakete
2. **AP-02** (Retry Mechanism) - Kern-Logik
3. **AP-03** (Stale Detection) - Parallel zu AP-02 möglich
4. **AP-04** (Workflow Abort) - Nach AP-02
5. **AP-05** (Error Persistence) - Nach AP-02, AP-03, AP-04
6. **AP-06** (API Endpoints) - Optional, kann später kommen

## Risikofaktoren

| Risiko | Auswirkung | Gegenmaßnahme |
|--------|------------|---------------|
| Falsche Fehler-Klassifizierung | Unnötige Retries oder vorzeitiger Abort | Tests schreiben, Logging aktivieren |
| Race Conditions | Doppelte Ausführung oder Status-Konflikte | Optimistic Locking, Transaction isolation |
| Missing Integration | Retry/Recovery funktioniert nicht | End-to-End Tests schreiben |
| Performance-Impact | Stale Detection verlangsamt System | Batch-Größe limitieren, Indexe prüfen |

## Akzeptanzkriterien (gesamt)

### Funktionale Anforderungen (REQ-018)

- [x] ERR-001: Runner erkennt Task-Fehler und klassifiziert sie
- [ ] ERR-002: Recoverable Fehler: Retry bis `max_retries`
- [ ] ERR-003: Non-recoverable Fehler: Sofortiger Workflow-Abort
- [ ] ERR-004: Bei `retry_count >= max_retries`: Workflow-Abort
- [ ] ERR-005: Workflow-Status wird auf `failed` aktualisiert
- [ ] ERR-006: Orchestrator wird über Workflow-Abort informiert
- [x] ERR-007: Fehler werden in `task_execution.error_message` und `error_type` persistiert
- [ ] ERR-008: Exponentielles Backoff zwischen Retries (configurable)
- [ ] ERR-009: Fehler-Logs enthalten `workflow_id`, `task_id`, `retry_count`

### Nicht-Funktionale Anforderungen (REQ-018)

- [ ] NFA-001: Fehlerbehandlung muss performant sein (kein Overhead bei Erfolg)
- [ ] NFA-002: Fehler-Klassifizierung muss klar und testbar sein
- [ ] NFA-003: Retry-Logik muss konfigurierbar sein (max_retries, backoff)

## Decision Log

| Entscheidung | Option A | Option B | Empfohlen |
|--------------|----------|----------|-----------|
| Error Classification | Neue Enum | Bestehende verwenden | Bestehende verwenden |
| Retry Integration | Neue Module | Bestehende RecoveryService | Bestehende RecoveryService |
| Stale Detection | Separater Scheduler | Runner-Loop Integration | Runner-Loop Integration |
| API Endpoints | Vollständige Implementierung | Minimal (nur Status Query) | Minimal beginnen |

## Offene Fragen

1. **OF-01**: Wie soll mit "Conflict"-Fehlern umgegangen werden?
   - Antwort: Retry mit Wartezeit oder Abort (abhängig vom Kontext) - siehe `ErrorType.CONFLICT`

2. **OF-02**: Soll es ein "Manual Retry" nach Workflow-Abort geben?
   - Antwort: Out of Scope für MS-002, aber API-Endpoint (AP-06) vorbereitet

## Test-Strategie

1. **Unit Tests**:
   - Error Classification Tests
   - Retry Decision Tests
   - Stale Detection Tests

2. **Integration Tests**:
   - Retry-Flow im Runner
   - Stale Recovery Flow
   - Workflow Abort Flow

3. **End-to-End Tests**:
   - Max-Retry Exhaustion
   - Non-Recoverable Error → Abort
   - Stale Detection → Recovery

## Rollback-Plan

Falls Probleme auftreten:

1. **AP-01**: Keine Änderungen an bestehender Codebase
2. **AP-02**: Retry-Logik revertieren durch Entfernen der Integration
3. **AP-03**: Stale Detection deaktivieren durch Config-Flag
4. **AP-04**: Workflow Abort durch Exception-Handler deaktivieren
5. **AP-05**: Logging deaktivieren durch Config-Flag
6. **AP-06**: Router-Registrierung entfernen

## Zielpfad

`/home/ubuntu/workspace/IdeaProjects/ExecQueue/docs/REQ-018/00_overview.md`
