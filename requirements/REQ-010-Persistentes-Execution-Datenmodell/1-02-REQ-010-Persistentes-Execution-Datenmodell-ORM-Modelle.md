# 2. ORM Model Definition Work Package

## Titel
SQLAlchemy‑Modelle für persistentes Execution‑Datenmodell (REQ‑010)

## Ziel
Definieren der Python‑SQLAlchemy‑Klassen, die den in Arbeitspaket 1 erstellten Datenbanktabellen entsprechen, inkl. Enum‑Typen und Beziehungen.

## Geschätzter Entwickleraufwand
4–6 Stunden

## Fachlicher Kontext / betroffene Domäne
Datenzugriffsschicht (Data‑Access‑Layer) der ExecQueue‑Pipeline.

## Voranalyse vor Implementierungsbeginn
- **Relevante Dateien / Module**: `execqueue/db.py` (Engine/Session‑Setup), evtl. vorhandene Modelle in `execqueue/models/` (derzeit nicht existent).
- **Anpassungsstellen**: Neue Datei `execqueue/models.py` oder Unterpaket `execqueue/models/` mit einzelnen Modell‑Dateien.
- **Bestehende Patterns**: Nutzung von SQLAlchemy 1.4‑Declarative‑Base, ggf. bereits genutztes `databases`‑Package – prüfen im Code‑Base.
- **Risiken / Unklarheiten**: Keine bestehenden Modelle -> Introduktion des Base‑Objekts und ggf. Alembic‑Auto‑generation muss berücksichtigt werden.

## Technical Specification
1. **Erstelle Basis‑Modul** `execqueue/models/__init__.py` mit:
   ```python
   from sqlalchemy.ext.declarative import declarative_base
   Base = declarative_base()
   ```
2. **Enum‑Definitionen** in `execqueue/models/enums.py`:
   - `RequirementStatus` (new, planning, ready_for_execution, in_progress, done, failed)
   - `TaskStatus` (new, pending, in_progress, done, failed)
   - `TaskType` (planning, execution, analyze, implement, review)
   - `ExecutionStatus` (pending, running, succeeded, failed)
3. **Modelle** in `execqueue/models/requirement.py` etc. mit Feldern laut REQ‑010 F01‑F06, inkl. `ForeignKey`‑Beziehungen und `relationship`‑Deklarationen.
4. **Tabellen‑Argumente**: `__tablename__`, `Column`‑Typen (`String`, `Text`, `Enum`, `DateTime`, `JSONB` (PostgreSQL) → fallback zu `JSON` wenn DB‑Abstraktion nötig).
5. **Index‑Deklarationen** über `Index`‑Klasse für die geforderten Felder.
6. **Import‑Kurzweg**: In `execqueue/models/__init__.py` alle Modelle exportieren für einfache Nutzung (`from .requirement import Requirement`, …).
7. **Update `execqueue/db.py`**: Sicherstellen, dass `Base.metadata.create_all(bind=engine)` optional für Tests benutzt wird.
8. **Dokumentation**: Jede Modell‑Datei mit Docstring, Beschreibung der Spalten.

## Test‑ und Validierungsstrategie
- **Unit‑Tests** in `tests/test_models.py` prüfen, dass die Klassen importierbar sind und das `__table__`‑Objekt die erwarteten Spalten enthält.
- **Schema‑Reflexionstest**: Mit einer in‑Memory‑SQLite‑Datenbank (`engine = create_engine('sqlite:///:memory:')`) `Base.metadata.create_all` ausführen und prüfen, dass Tabellen angelegt werden.
- **Enum‑Wert‑Test**: Validieren, dass ungültige Enum‑Werte nicht persistiert werden (SQLAlchemy wirft `ValueError`).

## Bewusst nicht vorgenommene Änderungen
- Keine Repository‑Klassen oder Service‑Logik – wird in eigenem Arbeitspaket behandelt.
- Keine Migration‑Ausführungs‑Logik – bereits im ersten Paket abgedeckt.

## Betroffene Bestandteile
- `execqueue/models/`
- `execqueue/db.py`

## Konkrete Umsetzungsschritte
1. Anlegen des Pakets `execqueue/models/` und `__init__.py`.
2. Implementieren der Enum‑Datei.
3. Implementieren der sechs Modell‑Dateien (`requirement.py`, `task.py`, `execution_plan.py`, `task_dependency.py`, `task_execution.py`, `task_execution_event.py`).
4. Exportieren im `__init__.py`.
5. Anpassungen in `execqueue/db.py` für Base‑Import.
6. Schreiben der Tests `tests/test_models.py`.

## Architektur‑ und Codequalitätsvorgaben
- Verwende `typing`‑Annotationen für Felder.
- Halte Beziehungen (`relationship`) lazy='select' oder `back_populates` passend.
- Nutze `sqlalchemy.dialects.postgresql` für `JSONB` mit Fallback‑Import.
- Einheitliche Benennung nach PEP8.

## Abgrenzung
- Keine CRUD‑Service‑Klassen, keine API‑Endpoints.
- Keine Migrations‑Logik (schon erledigt).

## Abhängigkeiten
- Arbeitspaket 1 (Migration) muss vorhanden sein, damit die Tabellenstruktur definiert ist.

## Akzeptanzkriterien
- Alle Modelle lassen sich importieren.
- `Base.metadata.create_all` erzeugt die Tabellen ohne Fehler.
- Enums sind korrekt definiert und restrictiv.
- Tests im `tests/`‑Verzeichnis bestehen.

## Begründung für neue Dateien
Ein dediziertes `models`‑Paket ist notwendig, um die Datenbankstruktur programmgesteuert zu repräsentieren und für ORM‑Zugriff zu nutzen.

## Empfohlener Dateiname
`execqueue/models/README.md` (Beschreibung) – eigentliche Dateien werden einzeln angelegt.

## Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/`