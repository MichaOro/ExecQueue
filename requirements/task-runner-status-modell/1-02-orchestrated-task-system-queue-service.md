# Arbeitspaket 2: Queue-Service mit Blockierungslogik und Status-Management

## 1. Titel
Queue-Service: Blockierungslogik, Parallelisierung und Status-Updates

## 2. Ziel
Implementierung der Queue-Steuerungslogik in einem einzigen Service-Modul. Zentrale Verwaltung von Blockierungsregeln, Parallelisierungssteuerung und Status-Synchronisation zwischen Task, Requirement und WorkPackage.

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: Queue-Verwaltung und Task-Orchestrierung
- **Zweck**: Steuert welche Tasks wann ausgeführt werden dürfen, basierend auf Blockierungs- und Parallelisierungsregeln
- **Bezug**: Anforderungsartefakt Section 7 (Queue- und Scheduling-Modell) und Section 10 (Fachliche Regeln)

## 4. Betroffene Bestandteile

### Zu erweiternde Datei:
- `execqueue/services/queue_service.py` - **ERWEITERUNG** bestehender Service (bereits vorhanden mit `enqueue_requirement()`)

### Zu erweiternde Dateien:
- `execqueue/scheduler/runner.py` - Integration der Queue-Prüflogik
- `execqueue/validation/task_validator.py` - Ergänzende Validation-Functions

### Nicht erforderlich (bewusst nicht erstellt):
- `status_service.py` - Status-Logik bleibt im Queue-Service (zu klein für separate Datei)
- `blocker_service.py` - Blockierungslogik im Queue-Service (keine echte fachliche Grenze)
- Separate Validator-Dateien - Validation im Service oder bestehender Validator

## 5. Konkrete Umsetzungsschritte

### Schritt 1: Queue-Status-Validierung implementieren
**Ziel**: Prüfen, ob ein Status-Übergang erlaubt ist

**Funktionen**:
- `is_valid_status_transition(old_status: str, new_status: str) -> bool`
  - Erlaubte Übergänge: backlog → in_progress → review → done
  - Jeder Status → trash (bei Abbruch)
  - Keine anderen Übergänge

**Umsetzung**:
- Whitelist-basierter Ansatz mit Dictionary oder Set
- Klare Definition aller erlaubten Übergänge
- Logging bei ungültigen Übergängen

### Schritt 2: Queue-Blockierungs-Prüfung implementieren
**Ziel**: Prüfen, ob Queue aktuell blockiert ist

**Funktionen**:
- `is_queue_blocked(session: Session) -> bool`
  - Prüft alle Tasks mit `block_queue=True` und Status `in_progress`
  - Berücksichtigt `is_test` Filter
- `get_blocking_task(session: Session) -> Optional[Task]`
  - Gibt den blockierenden Task zurück (falls vorhanden)

**Umsetzung**:
- Query auf Tasks mit `block_queue=True` und `status="in_progress"`
- Early Return bei erstem Treffer (Performance)
- Index-Nutzung sicherstellen (`block_queue`, `status`)

### Schritt 3: Parallelisierungs-Steuerung implementieren
**Ziel**: Kontrolle gleichzeitiger Task-Execution

**Funktionen**:
- `get_active_parallel_tasks(session: Session) -> int`
  - Zählt Tasks mit `status="in_progress"` und `parallelization_allowed=True`
- `can_start_parallel_task(session: Session, max_parallel: int = 3) -> bool`
  - Prüft, ob weiterer paralleler Task gestartet werden darf
- `get_parallelization_delay(task: Task, session: Session) -> timedelta`
  - Berechnet Delay basierend auf `parallelization_delay` Feld

**Umsetzung**:
- Konfigurierbares `max_parallel` (Default: 3)
- Environment Variable für Konfiguration erwägen
- Delay-Berechnung aus `parallelization_delay` Feld

### Schritt 4: Status-Synchronisation implementieren
**Ziel**: Konsistente Status-Updates über alle Entitäten

**Funktionen**:
- `sync_task_status_to_source(task: Task, session: Session) -> None`
  - Aktualisiert `queue_status` von Requirement oder WorkPackage
  - Kaskadiert zu Requirement bei WorkPackage-Änderung
- `check_requirement_done(requirement_id: int, session: Session) -> bool`
  - Prüft, ob alle WorkPackages eines Requirements done sind
  - Setzt Requirement-Status auf "done" wenn ja

**Umsetzung**:
- `source_type` und `source_id` für Zuordnung nutzen
- Batch-Updates für Performance
- `updated_at` manuell setzen

### Schritt 5: Dependency-Validation implementieren
**Ziel**: WorkPackage-Dependencies prüfen

**Funktionen**:
- `validate_work_package_dependencies(wp_id: int, session: Session) -> bool`
  - Prüft, ob alle Dependencies des WorkPackages done sind
  - Erkennt zyklische Dependencies (Tiefensuche)
- `get_unmet_dependencies(wp_id: int, session: Session) -> list[WorkPackage]`
  - Gibt alle nicht erfüllten Dependencies zurück

**Umsetzung**:
- Rekursive Zyklus-Erkennung mit Besucherset
- Early Return bei Zyklus-Erkennung
- Logging bei Zyklen

### Schritt 6: Queue-Query erweitern (in runner.py)
**Ziel**: Scheduler berücksichtigt neue Flags

**Änderungen in `get_next_queued_task()`**:
- Prüfen auf `block_queue` Tasks (früher return wenn blockiert)
- Parallelisierungs-Check vor Task-Auswahl
- `order_number` in Sortierung berücksichtigen
- `scheduled_after` weiterhin beachten
- `schedulable` Flag prüfen (nur automatische Tasks)

**Umsetzung**:
- Erweiterte Query-Logik in `runner.py`
- Keine neuen Functions, nur Erweiterung bestehender
- Logging bei Blockierung oder Delay

## 6. Architektur- und Codequalitätsvorgaben

### Minimal Invasivität
- **Bestehenden Service erweitern** - `queue_service.py` existiert bereits
- **Keine neuen Services** - alle Logik in einem Modul
- **Scheduler-Integration** - nur `runner.py` erweitern, keine neuen Runner

### Code-Qualität
- Type-Hints für alle Functions
- Docstrings im Google-Style für öffentliche APIs
- German Comments für komplexe Logik
- Early Returns für bessere Lesbarkeit

### Performance
- **Keine N+1 Queries** - `joinedload()` bei Relationships
- **Index-Nutzung** - Queries auf indizierte Felder optimieren
- **Early Returns** - bei Blockierung sofort zurück

### Testbarkeit
- Pure Functions wo möglich (Status-Transition, Dependency-Check)
- Session als Parameter (nicht global)
- Mockable External Calls

## 7. Abgrenzung: Was nicht Teil des Pakets ist

**Nicht enthalten**:
- API-Endpoints (siehe AP-4)
- Scheduler-Hauptlogik (siehe AP-3)
- UI-Integration (nicht vorgesehen)
- Metrics-Reporting (siehe AP-6)
- Retry-Logik (bereits in `runner.py`)

**Explizite Entscheidungen**:
- **Keine separate Status-Service-Datei** - zu kleine Logik, bleibt im Queue-Service
- **Keine Event-basierte Architektur** - direkte Function-Calls (einfacher, konsistent)
- **Keine Caching-Schicht** - direkte DB-Queries (Single-Instance, kein Caching nötig)

## 8. Abhängigkeiten

### Vor diesem Paket:
- **AP-1 (Model-Erweiterungen)** - benötigt neue Model-Felder

### Nach diesem Paket:
- **AP-3 (Scheduler-Erweiterung)** - nutzt Queue-Service
- **AP-4 (API-Erweiterungen)** - nutzt Queue-Service Functions
- **AP-5 (Tests)** - testet Queue-Service

## 9. Akzeptanzkriterien

### Funktionale Kriterien
- [ ] Status-Übergänge werden korrekt validiert
- [ ] Queue-Blockierung wird erkannt und verhindert Tasks
- [ ] Parallelisierungs-Limit wird eingehalten
- [ ] Status-Synchronisation funktioniert (Task → Requirement/WorkPackage)
- [ ] Dependency-Validation erkennt Zyklen
- [ ] `order_number` beeinflusst Queue-Reihenfolge
- [ ] `schedulable` Flag wird beachtet

### Technische Kriterien
- [ ] Keine N+1 Queries (joinedload bei Relationships)
- [ ] `is_test` Filter in allen Queries
- [ ] `updated_at` manuell gesetzt
- [ ] Alle Functions sind testbar (Session als Parameter)
- [ ] `pytest` besteht für neue Functions

### Qualitätskriterien
- [ ] Keine neuen Dateien (nur `queue_service.py` erweitert)
- [ ] Minimal invasive Änderungen
- [ ] Docstrings für öffentliche APIs
- [ ] German Comments bei komplexer Logik

## 10. Risiken / Prüfpunkte

### Technische Risiken
- **Race Conditions**: Bei mehreren Scheduler-Instances
  - **Lösung**: Optimistic Locking wie in `runner.py` bereits vorhanden
  
- **Zyklische Dependencies**: Unendliche Schleife bei Zyklus-Erkennung
  - **Lösung**: Besucherset in DFS, Max-Depth-Limit

- **Performance bei vielen Tasks**: Queue-Queries langsam
  - **Lösung**: Indizes auf `block_queue`, `status`, `order_number`

### Prüfpunkte vor Merge
- [ ] Dependency-Zyklus-Test mit künstlichen Zyklen
- [ ] Blockierungs-Test mit parallelen Requests
- [ ] Performance-Test mit 100+ Tasks in Queue
- [ ] Code-Review (@code-reviewer)

## 11. Begründung für neue Dateien/Module

**Keine neuen Dateien** - Erweiterung von `execqueue/services/queue_service.py`:
- Datei existiert bereits mit `enqueue_requirement()`
- Neue Functions passen fachlich in existierende Struktur
- Maximal 150-200 Zeilen nach Erweiterung (noch gut lesbar)

**Begründung**: Die Queue-Logik ist eng gekoppelt (Blockierung, Parallelisierung, Status-Sync) und sollte zusammen bleiben. Separate Files würden unnötige Komplexität ohne Mehrwert hinzufügen.

**Nicht erstellte Module und warum**:
- `status_service.py` - Status-Logik ist zu klein (3-4 Functions), bleibt im Queue-Service
- `blocker_service.py` - Blockierung ist Teil der Queue-Logik, keine eigene Domäne
- `dependency_service.py` - Dependency-Check wird nur an 2-3 Stellen benötigt

## 12. Empfohlener Dateiname
`1-02-orchestrated-task-system-queue-service.md`

## 13. Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/requirements/task-runner-status-modell/1-02-orchestrated-task-system-queue-service.md`

---

**Arbeitspaket Version**: 1.0  
**Erstellt**: 2026-04-23  
**Priorität**: HIGH (Kern-Logik für Queue-Steuerung)  
**Geschätzter Aufwand**: 6-8 Stunden  
**Verantwortlich**: Build Agent (ExecQueue)

EXECQUEUE.STATUS.FINISHED
