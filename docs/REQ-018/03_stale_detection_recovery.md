# Arbeitspaket 03 - Stale Execution Detection & Recovery

## Ziel

Implementierung der Stale Execution Detection und automatisierten Recovery. Nutzung der bestehenden `is_execution_stale()` und `find_stale_executions()` Funktionen.

## Aufwand

~2h

## Fachlicher Kontext

REQ-018 verlangt implizit:
- Erkennung von hängigen/fehlgeschlagenen Executions
- Automatische Recovery oder manuelle Intervention

Die Codebase bietet bereits:
- `is_execution_stale(execution, thresholds, now)` in `error_classification.py`
- `find_stale_executions(session, thresholds, statuses)` in `error_classification.py`
- `RecoveryService.handle_stale_execution()` in `recovery.py`
- `RecoveryService.process_stale_executions()` für Batch-Verarbeitung

## Codebase-Kontext

### Relevante Artefakte

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/error_classification.py` (578 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py` (736 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/orchestrator/recovery.py` (262 Zeilen)

### CODEBASE-INSIGHTS

1. **error_classification.py Line 368-520**: `is_execution_stale()` und `find_stale_executions()`
2. **recovery.py Line 201-307**: `RecoveryService.handle_stale_execution()`
3. **recovery.py Line 309-339**: `RecoveryService.process_stale_executions()`
4. **orchestrator/recovery.py**: Separate Stale Recovery für Orchestrator

### CODEBASE-ASSUMPTIONS

1. Stale Detection wird bereits periodisch ausgeführt
2. Die `heartbeat_at` und `updated_at` Felder werden korrekt aktualisiert

### CODEBASE-RISKS

1. **R-1**: Stale Detection ist möglicherweise nicht automatisiert
2. **R-2**: Die Thresholds (300s heartbeat, 600s update, 3600s max duration) sind hardcoded

## Voranalyse

### Anpassungsstellen

1. **`execqueue/runner/main.py`**:
   - Periodische Stale Detection im Runner-Loop integrieren
   - Oder separaten Scheduler für Stale Processing

2. **`execqueue/orchestrator/main.py`**:
   - `recover_running_workflows()` mit Stale Detection verbinden

### Patterns

- Heartbeat Timeout (300s default)
- Update Timeout (600s default)
- Max Duration (3600s default)
- Batch-Verarbeitung via `find_stale_executions()`

### Wiederverwendung

- `is_execution_stale()` direkt verwenden
- `find_stale_executions()` direkt verwenden
- `RecoveryService.handle_stale_execution()` direkt verwenden

### Risiken

- **R-1**: Stale Detection könnte aktive Executions fälschlich markieren
- **R-2**: Race Condition zwischen Heartbeat-Update und Stale Detection

## Technical Specification

### Änderungen (empfohlen)

**Option A: Periodischer Scheduler im Runner**

```python
# In execqueue/runner/main.py - Runner class
async def _poll_cycle(self):
    # Existing polling logic
    await self.claimer.poll()
    
    # Stale Detection (alle X Sekunden)
    if self._should_check_stale():
        await self._process_stale_executions()

async def _process_stale_executions(self):
    async with self.db.sessionmaker() as session:
        recovery_service = RecoveryService()
        await recovery_service.process_stale_executions(session)
        await session.commit()
```

**Option B: Separater Background Task**

```python
# Neue Datei: execqueue/runner/stale_scheduler.py
class StaleDetectionScheduler:
    async def start(self):
        while True:
            async with sessionmaker() as session:
                recovery = RecoveryService()
                await recovery.process_stale_executions(session)
            await asyncio.sleep(60)  # Alle 60 Sekunden
```

### Flow-Integration

```
Scheduler/Runner Loop → find_stale_executions() → [List of Stale Executions]
    ↓
For each execution: RecoveryService.handle_stale_execution()
    ↓
Decision: Retry (schedule) or Fail (mark as failed)
```

### Seiteneffekte

- Database Queries für Stale Executions
- Database Updates für status/error_type
- Eventuelle Runner-Restarts für recoverable Stale Executions

### Tests

- Unit Test für `is_execution_stale()` mit verschiedenen Timeouts
- Integration Test für `process_stale_executions()`
- Test für verschiedene Stale Szenarien (heartbeat timeout, max duration exceeded)

### Neue Module + Begründung

- **Optional**: `execqueue/runner/stale_scheduler.py` für separaten Scheduler
- **Alternative**: Integration in bestehenden Runner-Loop

## Umsetzungsspielraum

### Flexible Bereiche

- Entscheidung: Periodischer Scheduler vs. Runner-Loop Integration
- Entscheidung: Stale Detection Frequency (60s, 300s, etc.)
- Entscheidung: Thresholds konfigurierbar machen oder hardcoded lassen

### Fixe Bereiche

- **Nicht verändern**: `is_execution_stale()` Logik ohne Tests
- **Nicht verändern**: `find_stale_executions()` Query ohne Validierung
- **Muss erhalten bleiben**: Heartbeat/Update/Duration Checks

## Umsetzungsschritte

1. **Code Review** von `error_classification.py` (Stale Detection) und `recovery.py` (Stale Recovery)
2. **Entscheidung**: Scheduler vs. Runner-Loop Integration
3. **Implementieren** der Stale Detection Automation
4. **Konfigurieren** der Thresholds (hardcoded oder config)
5. **Tests schreiben** für Stale Szenarien
6. **Validierung**: Bestehende Tests laufen lassen

## Abhängigkeiten

- **AP-01**: Error Classification muss vollständig sein
- **DB**: `heartbeat_at`, `updated_at`, `started_at` Felder müssen existieren

## Akzeptanzkriterien

- [ ] Stale Executions werden erkannt (heartbeat timeout, update timeout, max duration)
- [ ] Stale Executions werden automatisch verarbeitet (RecoveryService)
- [ ] Recoverable Stale: Retry scheduled mit `next_retry_at`
- [ ] Non-recoverable Stale: Status = FAILED
- [ ] Logging enthält `workflow_id`, `task_id`, `stale_type`
- [ ] Unit Tests für Stale Detection bestehen
- [ ] Integration Test für Stale Recovery besteht

## Entwickler-/Agent-Validierung

### Zu prüfende Dateien

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/error_classification.py` (Line 368-520)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py` (Line 201-339)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/orchestrator/recovery.py`

### Kritische Annahmen

1. `heartbeat_at` wird regelmäßig aktualisiert während Execution
2. Die `find_stale_executions()` Query ist performant (Index auf `heartbeat_at`, `status`)

### Manuelle Checks

1. REQ-018 Abschnitt 5 "Retry-Logik" mit Stale Detection abgleichen
2. Database Indexe für `heartbeat_at` und `updated_at` prüfen

## Risiken

| Risiko | Auswirkung | Gegenmaßnahme |
|--------|------------|---------------|
| Falsche Stale-Erkennung | Aktive Executions werden abgebrochen | Thresholds carefully configure, Logging |
| Performance-Impact | Stale Detection verlangsamt System | Batch-Größe limitieren, Indexe prüfen |
| Race Condition | Heartbeat während Stale Check | Optimistic Locking, Transaction isolation |

## Zielpfad

`/home/ubuntu/workspace/IdeaProjects/ExecQueue/docs/REQ-018/03_stale_detection_recovery.md`
