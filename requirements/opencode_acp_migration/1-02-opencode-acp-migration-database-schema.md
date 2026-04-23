# Arbeitspaket 1-02: Datenbank-Schema-Erweiterung

## 1. Titel
**Erweiterung der Task/WorkPackage-Modelle um OpenCode Session-Metadaten**

## 2. Ziel
Persistierung von OpenCode Session-IDs, Projekt-Pfaden und Status-Informationen in den bestehenden Datenbank-Modellen.

## 3. Fachlicher Kontext / betroffene Domäne
- **Domain**: Datenmodell / Persistence
- **Verantwortlichkeit**: Abbildung von Session-Zuständen in der Datenbank
- **Zielgruppe**: Session-Management Service, API-Endpoints

## 4. Betroffene Bestandteile
- **Erweiterung**: `execqueue/models/task.py`
  - Neue Felder: `opencode_session_id`, `opencode_project_path`, `opencode_status`
- **Erweiterung**: `execqueue/models/work_package.py`
  - Gleiche Felder wie Task (falls WorkPackages auch von OpenCode ausgeführt werden)
- **Keine neuen Modelle**: Erweiterung der bestehenden Modelle reicht aus

## 5. Konkrete Umsetzungsschritte
1. **Enum für Session-Status definieren** (`execqueue/models/task.py`):
   ```python
   from enum import Enum
   
   class OpenCodeSessionStatus(str, Enum):
       PENDING = "pending"
       RUNNING = "running"
       WAITING = "waiting"  # Wartet auf Bestätigung/Wake-up
       COMPLETED = "completed"
       FAILED = "failed"
   ```

2. **Task-Modell erweitern** (`execqueue/models/task.py`):
   - `opencode_session_id: str | None = None` (SQLModel: `index=True`)
   - `opencode_project_path: str | None = None`
   - `opencode_status: OpenCodeSessionStatus = OpenCodeSessionStatus.PENDING`
   - `opencode_last_ping: datetime | None = None` (für Timeout-Tracking)

3. **WorkPackage-Modell erweitern** (`execqueue/models/work_package.py`):
   - Gleiche Felder wie Task (falls relevant)

4. **Datenbank-Schema synchronisieren**:
   - Manuell ausführen: `python -c "import execqueue.db.engine as e; e.create_db_and_tables()"`
   - **Keine Alembic-Migration** (Projekt-Konvention)

5. **Defaults setzen**:
   - Neue Tasks haben `opencode_status = PENDING`
   - `opencode_session_id` ist `None` bis Session gestartet

## 6. Architektur- und Codequalitätsvorgaben
- **Minimal Invasivität**: Nur neue Felder, keine Änderungen an bestehenden Feldern
- **Backward Compatibility**: Alle neuen Felder sind nullable oder haben Defaults
- **Indexing**: `opencode_session_id` wird indiziert für schnelle Lookups
- **Typ Safety**: Verwendung von `str | None` und Enum statt Strings

## 7. Abgrenzung: Was nicht Teil des Pakets ist
- **Keine API-Änderungen**: Die neuen Felder werden nicht automatisch via API exponiert (kann später kommen)
- **Kein Migration-Skript**: Manuelles `create_db_and_tables()` reicht
- **Kein Cleanup-Job**: Automatisches Löschen alter Sessions ist Teil von AP-3

## 8. Abhängigkeiten
- **Blockiert durch**: Keine
- **Blockiert**: AP-3 (Session-Management Service benötigt die Felder)

## 9. Akzeptanzkriterien
- [ ] `OpenCodeSessionStatus` Enum existiert in `task.py`
- [ ] `Task`-Modell hat 4 neue Felder mit korrekten Typen
- [ ] `WorkPackage`-Modell hat gleiche Felder (falls relevant)
- [ ] Datenbank-Schema wurde manuell aktualisiert
- [ ] Bestehende Tests laufen weiterhin (keine Breaking Changes)
- [ ] Neue Tasks haben korrekte Defaults

## 10. Risiken / Prüfpunkte
- **Datenbank-Lock**: Bei existierenden Daten kann `create_db_and_tables()` Probleme machen
  - *Lösung*: Vorher Backup der DB, oder manuelle `ALTER TABLE` Statements
- **Index-Kollision**: Falls `opencode_session_id` bereits existiert (unwahrscheinlich)
  - *Lösung*: `DROP INDEX IF EXISTS` vor `CREATE INDEX`

## 11. Begründung für neue Dateien/Module
**Keine neuen Dateien!**  
Die Felder werden direkt in `execqueue/models/task.py` und `work_package.py` hinzugefügt, da:
- Es sich um Entity-Erweiterungen handelt, nicht um neue Domänen
- Bestehende Patterns (SQLModel) verwendet werden
- Keine fachliche Grenze erreicht wird

## 12. Empfohlener Dateiname
`execqueue/models/task.py` und `execqueue/models/work_package.py` (erweitert)

## 13. Zielpfad
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/task.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/work_package.py`

EXECQUEUE.STATUS.FINISHED
