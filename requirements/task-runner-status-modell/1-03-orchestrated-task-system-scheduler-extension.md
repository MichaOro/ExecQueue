# Arbeitspaket 3: Scheduler-Erweiterung mit Queue-Steuerung

## 1. Titel
Scheduler-Erweiterung: Queue-Prüfung mit Blockierungs- und Parallelisierungslogik

## 2. Ziel
Erweiterung des bestehenden Scheduler-Runners um die Berücksichtigung der neuen Queue-Flags. Der Scheduler soll blockierende Tasks respektieren, Parallelisierungslimits einhalten und die OrderNumber für die Reihenfolge nutzen.

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: Task-Scheduling und Queue-Verarbeitung
- **Zweck**: Implementierung der Queue-Steuerungslogik im Scheduler-Loop
- **Bezug**: Anforderungsartefakt Section 7 (Queue- und Scheduling-Modell)

## 4. Betroffene Bestandteile

### Zu erweiternde Dateien:
- `execqueue/scheduler/runner.py` - Haupt-Scheduler-Logik
- `execqueue/services/queue_service.py` - Queue-Helper Functions (AP-2)

### Bestehende Komponenten (keine Änderungen):
- `execqueue/workers/opencode_adapter.py` - bleibt unverändert
- `execqueue/validation/task_validator.py` - bleibt unverändert

## 5. Konkrete Umsetzungsschritte

### Schritt 1: Queue-Blockierungs-Check in `get_next_queued_task()` integrieren
**Ziel**: Scheduler prüft vor Task-Auswahl ob Queue blockiert ist

**Umsetzung**:
- Vor der Task-Auswahl `is_queue_blocked(session)` aufrufen (aus AP-2)
- Wenn blockiert: Early Return mit `None` und Logging
- Blockierenden Task in Log-Ausgabe erwähnen
- Keine Task-Auswahl wenn blockiert

**Änderungen in `get_next_queued_task()`**:
```python
# Am Anfang der Funktion
if is_queue_blocked(session):
    blocking = get_blocking_task(session)
    logger.info("Queue blocked by task %d", blocking.id)
    return None
```

### Schritt 2: Parallelisierungs-Check implementieren
**Ziel**: Scheduler hält sich an Parallelisierungs-Limits

**Umsetzung**:
- Vor Task-Auswahl `can_start_parallel_task(session, max_parallel)` prüfen
- Wenn Task `parallelization_allowed=True` aber Limit erreicht: Delay + Retry
- Delay basierend auf `parallelization_delay` Feld berechnen
- Nicht-blockierender Return mit angemessenem Logging

**Logik**:
```python
if task.parallelization_allowed:
    if not can_start_parallel_task(session, max_parallel=3):
        # Delay und späterer Retry
        delay = get_parallelization_delay(task, session)
        task.scheduled_after = utcnow() + timedelta(seconds=delay)
        session.commit()
        return None
```

### Schritt 3: OrderNumber in Sortierung integrieren
**Ziel**: Tasks werden nach `order_number` sortiert

**Änderungen in `get_next_queued_task()`**:
- `order_by(Task.order_number, Task.execution_order, Task.id)`
- `order_number` hat Priorität vor `execution_order`
- Bei gleichem `order_number`: `execution_order` als Tie-Breaker

### Schritt 4: Schedulable-Flag prüfen
**Ziel**: Nur Tasks mit `schedulable=True` werden vom Scheduler verarbeitet

**Änderungen in `get_next_queued_task()`**:
- Filter hinzufügen: `Task.schedulable == True`
- Manuelle Tasks (`schedulable=False`) bleiben in Queue
- API-gesteuerte Ausführung bleibt möglich

### Schritt 5: Status-Synchronisation erweitern
**Ziel**: Task-Status wird auf Parent synchronisiert

**Änderungen in `_mark_source_done()`**:
- `queue_status` statt `status` verwenden
- `sync_task_status_to_source()` aus AP-2 aufrufen
- Kaskadierung zu Requirement bei WorkPackage-Abschluss
- `updated_at` manuell setzen auf allen Entities

### Schritt 6: Delay-Logik für Parallelisierung
**Ziel**: Configurable Delay zwischen parallelen Tasks

**Umsetzung**:
- `parallelization_delay` aus Requirement/WorkPackage lesen
- Default: 0 Sekunden (kein Delay)
- Delay vor Task-Start warten oder `scheduled_after` setzen
- Environment Variable für globales Default

### Schritt 7: Logging und Monitoring erweitern
**Ziel**: Nachvollziehbare Queue-Entscheidungen

**Logging-Punkte**:
- Queue-Blockierung erkannt (welcher Task blockiert)
- Parallelisierungs-Limit erreicht (wie viele laufen)
- OrderNumber-basierte Auswahl
- Schedulable-Filter (manuelle Tasks übersprungen)
- Delay-Anwendung (wie lange gewartet)

## 6. Architektur- und Codequalitätsvorgaben

### Minimal Invasivität
- **Bestehende Functions erweitern** - `get_next_queued_task()` und `_mark_source_done()`
- **Keine neuen Haupt-Functions** - nur Helper aus AP-2 nutzen
- **Pattern-Konsistenz** - bestehende Logging- und Error-Handling Muster verwenden

### Code-Qualität
- Type-Hints für alle neuen Parameter
- Docstrings für erweiterte Functions
- German Comments bei komplexer Queue-Logik
- Early Returns für bessere Lesbarkeit

### Performance
- **Keine zusätzlichen Queries** - Blockierungs-Check in bestehende Query integrieren
- **Index-Nutzung** - Alle Queries auf indizierte Felder
- **Early Returns** - Bei Blockierung sofort zurück

### Fehlerbehandlung
- **Graceful Degradation** - Bei Fehlern in Queue-Check Task überspringen
- **Retry-Logik** - Bei temporären Blockierungen späterer Retry
- **Logging** - Alle Queue-Entscheidungen protokollieren

## 7. Abgrenzung: Was nicht Teil des Pakets ist

**Nicht enthalten**:
- Queue-Service-Logik (siehe AP-2)
- API-Endpoints (siehe AP-4)
- Model-Erweiterungen (siehe AP-1)
- Test-Erweiterungen (siehe AP-5)
- Metrics-Reporting (siehe AP-6)

**Explizite Entscheidungen**:
- **Keine neue Scheduler-Architecture** - Erweiterungen in bestehendem `runner.py`
- **Keine Konfigurations-Datei** - Environment Variables für Konfiguration
- **Keine Admin-Endpoints** - Queue-Steuerung nur über Flags

## 8. Abhängigkeiten

### Vor diesem Paket:
- **AP-1 (Model-Erweiterungen)** - benötigt neue Model-Felder
- **AP-2 (Queue-Service)** - benötigt Queue-Helper Functions

### Nach diesem Paket:
- **AP-4 (API-Erweiterungen)** - nutzt Scheduler für manuelle Tasks
- **AP-5 (Tests)** - testet Scheduler-Logik
- **AP-6 (Metrics)** - nutzt Scheduler-Events

## 9. Akzeptanzkriterien

### Funktionale Kriterien
- [ ] Queue-Blockierung wird erkannt und verhindert Task-Auswahl
- [ ] Parallelisierungs-Limit wird eingehalten
- [ ] OrderNumber bestimmt Ausführungsreihenfolge
- [ ] Schedulable-Flag filtert manuelle Tasks
- [ ] Status-Synchronisation funktioniert korrekt
- [ ] Delay wird bei parallelen Tasks angewendet

### Technische Kriterien
- [ ] Keine N+1 Queries (joinedload bei Relationships)
- [ ] `is_test` Filter in allen Queries
- [ ] `updated_at` manuell gesetzt
- [ ] Alle neuen Log-Punkte vorhanden
- [ ] `pytest` besteht für Scheduler-Tests

### Qualitätskriterien
- [ ] Keine neuen Dateien (nur `runner.py` erweitert)
- [ ] Minimal invasive Änderungen
- [ ] Docstrings für erweiterte Functions
- [ ] German Comments bei komplexer Logik

## 10. Risiken / Prüfpunkte

### Technische Risiken
- **Scheduler-Stillstand**: Bei permanenter Blockierung
  - **Lösung**: Timeout für Blockierung, Manual Override
  
- **Deadlock**: Zyklische Dependencies blockieren sich gegenseitig
  - **Lösung**: Dependency-Validation vor Task-Erstellung (AP-2)

- **Performance**: Zu viele Queries für Queue-Checks
  - **Lösung**: Queries in bestehende Transaktion integrieren

### Prüfpunkte vor Merge
- [ ] Blockierungs-Test mit künstlich blockierendem Task
- [ ] Parallelisierungs-Test mit 3+ gleichzeitigen Tasks
- [ ] OrderNumber-Test mit gemischter Reihenfolge
- [ ] Schedulable-Test mit manuellen Tasks
- [ ] Code-Review (@code-reviewer)

## 11. Begründung für neue Dateien/Module

**Keine neuen Dateien** - Erweiterung von `execqueue/scheduler/runner.py`:
- Datei existiert bereits mit 305 Zeilen
- Erweiterungen fügen maximal 50-70 Zeilen hinzu
- Fachliche Einheit bleibt erhalten (Scheduler-Logik)

**Begründung**: Der Scheduler ist eine klar abgegrenzte Komponente. Erweiterungen passen in bestehende Struktur ohne Lesbarkeitsverlust. Keine Notwendigkeit für separate "scheduler_core.py" oder "queue_checker.py".

**Nicht erstellte Module und warum**:
- `scheduler_core.py` - Keine Trennung nötig, alles ist Scheduler-Logik
- `queue_checker.py` - Queue-Check ist Teil des Schedulers, keine eigene Domäne
- `parallelization_manager.py` - Zu klein, bleibt im Runner

## 12. Empfohlener Dateiname
`1-03-orchestrated-task-system-scheduler-extension.md`

## 13. Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/requirements/task-runner-status-modell/1-03-orchestrated-task-system-scheduler-extension.md`

---

**Arbeitspaket Version**: 1.0  
**Erstellt**: 2026-04-23  
**Priorität**: HIGH (Scheduler ist Kern-Komponente)  
**Geschätzter Aufwand**: 4-6 Stunden  
**Verantwortlich**: Build Agent (ExecQueue)

EXECQUEUE.STATUS.FINISHED
