# 1. DB Migration Work Package

## Titel
DB Migration für persistentes Execution-Datenmodell (REQ-010)

## Ziel
Implementieren der Datenbankmigrationen, die alle in REQ-010 geforderten Tabellen und Constraints anlegen.

## Geschätzter Entwickleraufwand
4–6 Stunden

## Fachlicher Kontext / betroffene Domäne
Datenpersistenzschicht der ExecQueue-Pipeline (Requirements, Tasks, Execution Plans, Dependencies, Executions, ACP Events).

## Voranalyse vor Implementierungsbeginn
- **Relevante Dateien / Module**: `execqueue/__init__.py` (Projekt‑Package), eventuell vorhandene Alembic‑Konfiguration (`alembic/`), `pyproject.toml` (Abhängigkeiten).
- **Anpassungsstellen**: Migration‑Ordner, ggf. `alembic/env.py` für neue Modelle, `execqueue/db.py` (SQLAlchemy‑Engine/Session). 
- **Bestehende Patterns**: Nutzung von SQLAlchemy (falls bereits vorhanden) oder `databases` Paket; prüfen vorhandene Migrations‑Tool (Alembic). 
- **Risiken / Unklarheiten**: Projekt enthält derzeit noch keine DB‑Modelle – muss ein Grundgerüst etabliert werden.

## Technical Specification
1. **Erstelle Alembic‑Migrationsskript** `versions/xxxx_add_execqueue_models.py` mit folgenden Tabellen:
   - `requirements` (Spalten: id PK, title, description, status (Enum), created_at, updated_at)
   - `tasks` (id PK, requirement_id FK, plan_id FK nullable, type (Enum), status (Enum), title, prompt TEXT, order_index INT, created_at, updated_at)
   - `execution_plans` (id PK, requirement_id FK, created_by_task_id FK, created_at, content JSONB, status Enum)
   - `task_dependencies` (task_id FK, depends_on_task_id FK, created_at, PK (task_id, depends_on_task_id), Unique constraint)
   - `task_executions` (id PK, task_id FK, runner_id VARCHAR, status Enum, started_at, finished_at, branch_name, worktree_path, commit_sha_before, commit_sha_after, error_message TEXT)
   - `task_execution_events` (id PK, task_execution_id FK, direction VARCHAR, event_type VARCHAR, payload JSONB, created_at)
2. **Constraints**: Foreign Keys, eindeutige Kombinationen, Indexe nach Vorgaben (tasks.status, tasks.type, tasks.order_index, task_dependencies.task_id, task_dependencies.depends_on_task_id, task_executions.task_id).
3. **Cycle‑Prevention**: Ergänze DB‑Trigger oder CHECK (optional – not required jetzt, aber vermerkt als zukünftige Aufgabe).
4. **Rollback‑Tests**: In der Migration den `downgrade`‑Block implementieren, der alle Tabellen wieder entfernt.
5. **Update `pyproject.toml`**: Fügt `alembic` und `SQLAlchemy` (falls nicht vorhanden) zu `dependencies` hinzu.

## Test‑ und Validierungsstrategie
- **Migrationstest**: `alembic upgrade head` ausführen, prüfen, dass alle Tabellen existieren und Constraints aktiv sind.
- **Rollbacktest**: `alembic downgrade base`, prüfen, dass Tabellen entfernt wurden.
- **Automatischer Test**: `tests/test_migrations.py` mit `pytest` und `alembic.command`.

## Bewusst nicht vorgenommene Änderungen
- Keine Implementierung von ORM‑Modellen (wird in eigenem Arbeitspaket behandelt).
- Keine Scheduling‑ oder Runner‑Logik.

## Betroffene Bestandteile
- `alembic/versions/`
- `pyproject.toml`

## Konkrete Umsetzungsschritte
1. Prüfen, ob Alembic konfiguriert ist; ggf. `alembic init alembic`.
2. Erstellen des Migrationsskripts mit `alembic revision -m "add execqueue models"`.
3. Implementieren der `upgrade`‑ und `downgrade`‑Blöcke gemäß Specification.
4. `pyproject.toml` um `alembic` und `SQLAlchemy` erweitern.
5. Testdatei `tests/test_migrations.py` anlegen und prüfen.

## Architektur‑ und Codequalitätsvorgaben
- Nutzung von SQLAlchemy‑Typen, Enum‑Definitionen im Migrationsskript.
- Dokumentation der Tabellen/Spalten im Docstring der Migration.
- Einheitliche Benennung (snake_case).

## Abgrenzung
- Keine Business‑Logik, nur Schema‑Definition.
- Keine Daten‑Seed‑Operationen.

## Abhängigkeiten
- Vorhandenes Alembic‑Setup oder Initialisierung im ersten Schritt.

## Akzeptanzkriterien
- `alembic upgrade head` läuft ohne Fehler.
- Alle geforderten Tabellen und Indexe existieren.
- `alembic downgrade base` entfernt alles wieder.
- Tests im `tests/` Verzeichnis bestehen.

## Begründung für neue Datei
Ein neues Alembic‑Migrationsskript ist nötig, weil das aktuelle Projekt noch keine Persistenz‑Tabellen für die Execution‑Pipeline besitzt.

## Empfohlener Dateiname
`alembic/versions/xxxx_add_execqueue_models.py`

## Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/alembic/versions/`