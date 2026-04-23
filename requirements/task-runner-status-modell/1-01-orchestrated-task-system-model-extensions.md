# Arbeitspaket 1: Model-Erweiterungen für Queue-Steuerung und Statusmodell

## 1. Titel
Model-Erweiterungen: Queue-Status, Blockierung und Parallelisierung

## 2. Ziel
Erweiterung der bestehenden Models `Task`, `Requirement` und `WorkPackage` um alle notwendigen Felder für Queue-Steuerung, Kanban-Status und Parallelisierungslogik. Keine neuen Models erstellen.

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: Task-Queue-Verwaltung
- **Zweck**: Ermöglicht Queue-Blockierung, Parallelisierungssteuerung und Kanban-Status-Tracking
- **Bezug**: Anforderungsartefakt Section 9 (Datenmodell-Anforderungen)

## 4. Betroffene Bestandteile

### Zu erweiternde Dateien (keine neuen Dateien):
- `execqueue/models/task.py`
- `execqueue/models/requirement.py`
- `execqueue/models/work_package.py`

### Datenbank-Synchronisation:
- `execqueue/db/engine.py` (bereits vorhanden, keine Änderungen)
- Manuelle Schema-Aktualisierung via `SQLModel.metadata.create_all()`

## 5. Konkrete Umsetzungsschritte

### Schritt 1: Requirement-Model erweitern
**Ziel**: Felder für Queue-Status, Typ, Reihenfolge und Scheduler-Steuerung

**Neue Felder**:
- `queue_status: str` - Default "backlog", Werte: backlog, in_progress, review, done, trash
- `type: str` - Default "artifact", Werte: transcript, artifact
- `has_work_packages: bool` - Default False
- `order_number: int` - Default 0
- `scheduler_enabled: bool` - Default True
- `parallelization_delay: int` - Default 0 (Sekunden)

**Umsetzung**:
- Felder als `Field()` mit `default_factory` oder festen Defaults
- `queue_status` mit `index=True` für Query-Performance
- Type-Hints korrekt setzen (str, bool, int)

### Schritt 2: WorkPackage-Model erweitern
**Ziel**: Felder für Queue-Status, Dependencies und Parallelisierung

**Neue Felder**:
- `queue_status: str` - Default "backlog", index=True
- `order_number: int` - Default 0
- `dependency_id: Optional[int]` - Foreign Key zu work_packages.id
- `parallelization_enabled: bool` - Default False

**Umsetzung**:
- `dependency_id` als Foreign Key definieren (optional)
- Index auf `queue_status` für Queue-Queries
- Type-Hints mit `Optional` für nullable Felder

### Schritt 3: Task-Model erweitern
**Ziel**: Felder für Queue-Blockierung und Parallelisierungserlaubnis

**Neue Felder**:
- `block_queue: bool` - Default False
- `parallelization_allowed: bool` - Default True
- `schedulable: bool` - Default True (ob Task vom Scheduler verarbeitet werden darf)
- `queue_status: str` - Default "backlog", index=True

**Umsetzung**:
- `block_queue` und `parallelization_allowed` als einfache Boolean-Felder
- `schedulable` für manuelle vs. automatische Tasks
- `queue_status` mit index für Queue-Filterung
- Synchronisation mit Requirement/WorkPackage Queue-Status

### Schritt 4: Datenbank-Schema synchronisieren
**Ziel**: Schema-Änderungen in Datenbank anwenden

**Umsetzung**:
- `python -c "import execqueue.db.engine as e; e.create_db_and_tables()"` ausführen
- Bestehende Daten nicht löschen (Test-Datenbank verwenden)
- Schema-Änderungen dokumentieren

### Schritt 5: Bestehende Queries prüfen
**Ziel**: Sicherstellen, dass `is_test` Filter konsistent bleibt

**Umsetzung**:
- Alle Queries in `services/`, `api/` und `scheduler/` auf `is_test` Filter prüfen
- Keine Query ohne `is_test == is_test_mode()` Filter

## 6. Architektur- und Codequalitätsvorgaben

### Minimal Invasivität
- **Keine neuen Models** - nur bestehende erweitern
- **Keine Breaking Changes** - alle neuen Felder mit Defaults
- **Keine Refactorings** - nur Feld-Ergänzungen

### Code-Qualität
- Type-Hints für alle neuen Felder
- Docstrings für neue Felder (falls komplex)
- German Comments wo sinnvoll
- Konsistente Feld-Reihenfolge (Status-Felder zusammen, Flags zusammen)

### Datenbank-Konformität
- `index=True` für häufig gefilterte Felder (`queue_status`)
- `ForeignKey` für `dependency_id` korrekt setzen
- `default_factory` oder feste Defaults für alle Felder

### Test-Konformität
- `is_test` Filter in allen neuen Queries
- Test-Daten erhalten `test_` Prefix

## 7. Abgrenzung: Was nicht Teil des Pakets ist

**Nicht enthalten**:
- Queue-Logik-Implementierung (siehe AP-2)
- Scheduler-Änderungen (siehe AP-3)
- API-Endpoints (siehe AP-4)
- Validation-Logik (siehe AP-5)
- Migration von Bestandsdaten (manuell, nicht automatisiert)

**Explizite Entscheidungen**:
- **Keine Enums** - Strings mit Validierung statt Pydantic Enums (einfacher, konsistent mit bestehendem `status` Feld)
- **Keine OnDelete-Regeln** - Foreign Keys ohne CASCADE (manuelle Bereinigung)
- **Keine Unique Constraints** - `order_number` kann dupliziert sein (später validieren)

## 8. Abhängigkeiten

### Vor diesem Paket:
- **Keine** - kann als erstes Paket umgesetzt werden

### Nach diesem Paket:
- **AP-2 (Queue-Service)** - benötigt neue Felder
- **AP-3 (Scheduler-Erweiterung)** - benötigt neue Felder
- **AP-4 (API-Erweiterungen)** - benötigt neue Felder

## 9. Akzeptanzkriterien

### Funktionale Kriterien
- [ ] Requirement hat alle 6 neuen Felder mit korrekten Defaults
- [ ] WorkPackage hat alle 4 neuen Felder mit korrekten Defaults
- [ ] Task hat alle 4 neuen Felder mit korrekten Defaults
- [ ] Alle neuen Felder sind in Datenbank vorhanden
- [ ] `queue_status` ist auf allen 3 Models indexiert

### Technische Kriterien
- [ ] `pytest` läuft ohne Fehler (bestehende Tests)
- [ ] Keine Breaking Changes für bestehende Code
- [ ] Type-Hints vollständig
- [ ] Code-Review bestanden (@code-reviewer)

### Qualitätskriterien
- [ ] Keine neuen Dateien erstellt
- [ ] Minimal invasive Änderungen
- [ ] German Comments wo angemessen
- [ ] Konsistente Code-Struktur

## 10. Risiken / Prüfpunkte

### Technische Risiken
- **Schema-Konflikte**: Bestehende Daten könnten konfliktär sein
  - **Lösung**: Test-Datenbank zuerst testen, Defaults sicher setzen
  
- **Index-Performance**: Zu viele Indizes können Write-Performance beeinträchtigen
  - **Lösung**: Nur wirklich benötigte Indizes (`queue_status`)

### Prüfpunkte vor Merge
- [ ] Datenbank-Schema mit `DESCRIBE` oder `\d` prüfen
- [ ] Bestehende Tests erneut ausführen
- [ ] Git-Diff auf unbeabsichtigte Änderungen prüfen

## 11. Begründung für neue Dateien/Module

**Keine neuen Dateien erforderlich** - alle Änderungen erfolgen in bestehenden Model-Dateien:
- `task.py` - bereits vorhanden, wird erweitert
- `requirement.py` - bereits vorhanden, wird erweitert
- `work_package.py` - bereits vorhanden, wird erweitert

**Begründung**: Die Models sind bereits fachlich korrekt zugeordnet und die Erweiterung um wenige Felder beeinträchtigt nicht die Lesbarkeit. Keine Notwendigkeit für separate "Field"- oder "Schema"-Dateien.

## 12. Empfohlener Dateiname
`1-01-orchestrated-task-system-model-extensions.md`

## 13. Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/requirements/task-runner-status-modell/1-01-orchestrated-task-system-model-extensions.md`

---

**Arbeitspaket Version**: 1.0  
**Erstellt**: 2026-04-23  
**Priorität**: HIGH (Blocker für alle anderen Pakete)  
**Geschätzter Aufwand**: 2-4 Stunden  
**Verantwortlich**: Build Agent (ExecQueue)

EXECQUEUE.STATUS.FINISHED
