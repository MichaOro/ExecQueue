# AGENTS.md

ExecQueue - FastAPI Task Queue für Requirements und Work Packages

**Version**: 2.0.0  
**Last Updated**: 2026-04-23  
**OpenCode Version**: Kompatibel mit v1.x

---

## Quick Start

**Server starten:**
```sh
uvicorn execqueue.main:app --reload
```
Server läuft auf `127.0.0.1:8000`.

**Tests ausführen:**
```sh
pytest
```
Tests verwenden `TEST_DATABASE_URL` aus `.env`.

**Datenbank initialisieren:**
```sh
python -c "import execqueue.db.engine as e; e.create_db_and_tables()"
```

**Agent starten:**
```sh
opencode
/init  # Erstmalige Initialisierung
```

---

## OpenCode Best Practices

### Agent-Wechsel (Plan vs Build)

Verwende **Tab** zum Wechseln zwischen Primary Agents:

- **Build Mode** (Standard): Vollständiger Zugriff für Code-Entwicklung
- **Plan Mode**: Read-Only für Analyse und Planung ohne Änderungen

```
<TAB>  # Wechsel zwischen Build und Plan
```

### Undo/Redo Änderungen

Falls Änderungen nicht gewünscht sind:

```
/undo  # Letzte Änderung rückgängig
/redo  # Rückgängige Änderung wiederherstellen
```

### Session-Management mit Subagenten

Wenn Subagenten Child-Sessions erstellen:

- **`<Leader>+Down`**: In erste Child-Session gehen
- **`Right`**: Zur nächsten Child-Session wechseln
- **`Left`**: Zur vorherigen Child-Session wechseln
- **`Up`**: Zurück zur Parent-Session

### @ Mentioning von Subagenten

Subagenten können manuell aufgerufen werden:

```
@code-reviewer Bitte review diesen PR
@test-engineer Erstelle Tests für die neue Funktion
```

## Environment

Required in `.env` (repo root):
- `DATABASE_URL` - PostgreSQL connection string (Neon)
- `TEST_DATABASE_URL` - Test database (used by pytest)

Optional:
- `EXECQUEUE_TEST_MODE` - Enable test mode
- `SCHEDULER_ENABLED` - Enable background scheduler (default: false)
- `OPENCODE_BASE_URL` - OpenCode API endpoint
- `ECHO_SQL` - Enable SQL logging for debugging (default: false)

---

## Architecture

```
execqueue/
  api/          FastAPI routers (tasks, queue, requirements, work-packages)
  models/       SQLModel domain entities
  services/     Business logic
  db/           Database engine, sessions
  scheduler/    Background job runner (runner.py)
  workers/      External adapters (opencode_adapter, telegram)
  validation/   Input validation
```

**Key entrypoints:**
- `execqueue/main.py` - FastAPI app, router mounting
- `execqueue/scheduler/runner.py` - Task execution loop
- `execqueue/db/engine.py` - Database connection

## Testing Conventions

- `asyncio_mode = auto` in `pytest.ini`
- Tests use `EXECQUEUE_TEST_MODE` or auto-detect via `PYTEST_CURRENT_TEST`
- Test data gets `test_` prefix via `apply_test_label()` helper
- All tests must pass before committing

## Known Gotchas & Solutions

### Database & Models

1. **`updated_at` not auto-updated:** Models haben `default_factory` aber kein `onupdate`.  
   → **Lösung:** Scheduler setzt es manuell; API-Endpoints müssen es explizit setzen

2. **`is_test` Filter wiederholt:** Jede Query filtert `is_test == is_test_mode()`.  
   → **Lösung:** Zentralisierung in `execqueue/validation/test_mode.py` erwägen

3. **No Alembic migrations:** Schema via `SQLModel.metadata.create_all()`.  
   → **Lösung:** Manuelle Synchronisation bei Schema-Änderungen erforderlich

### Testing

4. **SQL Logging disabled:** `echo=False` in `engine.py`.  
   → **Lösung:** Temporär via `ECHO_SQL=true` für Debugging aktivieren

5. **OpenCode Adapter tests:** 4 Tests benötigen `httpx.MockTransport` Setup.  
   → **Lösung:** In `tests/test_opencode_adapter.py` Mock-Transport konfigurieren

6. **DLQ tests need `client` fixture:** `tests/conftest.py` fehlt `TestClient` Fixture.  
   → **Lösung:** `client` Fixture in `conftest.py` hinzufügen

### Performance

7. **N+1 Queries bei Relationships:** SQLModel lädt Related Objects nicht automatisch.  
   → **Lösung:** `joinedload()` in allen Queries mit Relationships verwenden

## Reference Documents

- `/requirements/requirements_code_improvements.md` - Code improvement requirements
- `/requirements/0-offene_punkte_restarbeiten.md` - Open points and remaining work
- `/requirements/` - Alle Anforderungsdokumente
- `/opencode.json` - Agent configuration and subagent definitions
- `/.opencode/rules/coding-standards.md` - **CRITICAL**: Coding standards and guidelines (always loaded)
- `/.opencode/skills/*/SKILL.md` - Reusable agent skills

---

## Agent Skills

OpenCode Skills sind im `.opencode/skills/` Verzeichnis definiert:

- `test-runner` - Tests ausführen und validieren vor Commits
- `db-migration` - Datenbank-Schema-Änderungen ohne Alembic handhaben
- `code-review` - Code-Reviews für FastAPI/SQLModel Best Practices
- `api-generator` - FastAPI-Endpoints nach Projekt-Patterns erstellen

Skills werden über das `skill` Tool geladen, z.B.:
```
skill({ name: "test-runner" })
```

## Agent Versioning

Alle Agent-Definitionen verwenden ein Versioning-Schema für nachvollziehbare Updates:

**Format**: `MAJOR.MINOR.PATCH` (SemVer)

- **MAJOR**: Breaking changes in Agent-Prompts oder Permissions
- **MINOR**: Neue Features, zusätzliche Zuständigkeiten
- **PATCH**: Bugfixes, kleinere Verbesserungen

**Version Tracking**:
- Jede Agent-Datei hat Frontmatter mit `version` und `last_updated`
- Changelog wird in `.opencode/CHANGELOG.md` geführt
- Rollback via Git-Checkout der vorherigen Version

**Aktuelle Versionen**:
| Agent | Version | Last Updated |
|-------|---------|--------------|
| code-reviewer | 1.0.0 | 2026-04-23 |
| test-engineer | 1.0.0 | 2026-04-23 |
| db-specialist | 1.0.0 | 2026-04-23 |
| documentation-writer | 1.0.0 | 2026-04-23 |
| security-auditor | 1.0.0 | 2026-04-23 |

---

## Subagenten (Task-Tool)

Spezialisierte Subagenten für komplexe, mehrschrittige Aufgaben:

| Subagent | Expertise | Trigger Keywords |
|----------|-----------|------------------|
| `code-reviewer` | Code Quality, Best Practices, Security | "review", "quality", "best practices", "check code" |
| `test-engineer` | Test-Erstellung, Coverage, CI/CD | "test", "coverage", "pytest", "unit test" |
| `db-specialist` | Datenbank-Design, Migrations, Performance | "database", "schema", "migration", "model" |
| `documentation-writer` | API-Docs, User Guides, Docstrings | "docs", "documentation", "readme", "api docs" |

### Nutzung

Für komplexe Aufgaben startet OpenCode automatisch Subagenten:

```
"Erstelle einen neuen API Endpoint und erstelle dazu Tests"
→ task(description="Add API endpoint with tests", subagent_type="general", ...)
```

Oder explizit anfragen:
```
"Bitte erstelle Tests für die neuen Modelle"
→ task(description="Create comprehensive tests", subagent_type="test-engineer")
```

---

## Permission Configuration

**Skills** in `opencode.json`:
- `*`: "allow" - Alle Skills standardmäßig erlaubt
- Spezifische Skills können auf "ask" oder "deny" gesetzt werden

**Subagenten** werden automatisch in `agent` definiert und können Tools einschränken:
- `code-reviewer`: `edit: false, write: false` (read-only review)

**Permission Levels**:
| Level | Meaning | Examples |
|-------|---------|----------|
| **allow** | Automatisch erlaubt | Read files, pytest, git diff |
| **ask** | Benutzer-Frage erforderlich | pip install, force push |
| **deny** | Blockiert | rm -rf, drop database |

---

## Agent Usage Guidelines

### Agent Overview

ExecQueue verwendet ein mehrstufiges Agent-System für optimale Ergebnisqualität:

#### Primary Agents

| Agent | Model | Purpose | When to Use |
|-------|-------|---------|-------------|
| **build** | adesso/qwen-3.5-122b-sovereign | Code-Entwicklung und Implementierung | Für alle Coding-Aufgaben, Feature-Entwicklung, Bug-Fixes |
| **plan** | adesso/gpt-oss-120b-sovereign | Architektur und Design-Planung | Vor großen Änderungen, für technische Design-Dokumente |

#### Subagents

| Subagent | Expertise | Trigger Keywords |
|----------|-----------|------------------|
| **code-reviewer** | Code Quality, Best Practices, Security | "review", "quality", "best practices", "check code" |
| **test-engineer** | Test-Erstellung, Coverage, CI/CD | "test", "coverage", "pytest", "unit test" |
| **db-specialist** | Datenbank-Design, Migrations, Performance | "database", "schema", "migration", "model" |
| **documentation-writer** | API-Docs, User Guides, Docstrings | "docs", "documentation", "readme", "api docs" |
| **security-auditor** | Security Reviews, OWASP, Vulnerabilities | "security", "vulnerability", "owasp", "auth" |

### Workflow Guidelines

#### Standard Development Workflow

```
1. PLAN (optional für große Features)
   → "Erstelle einen Implementierungsplan für [Feature]"
   
2. BUILD
   → "Implementiere [Feature] nach Plan"
   
3. TEST
   → "Erstelle Tests für [Feature]"
   → "Führe Tests aus und prüfe Coverage"
   
4. REVIEW
   → "Review den Code auf Best Practices"
   
5. COMMIT
   → Alle Tests müssen grün sein
   → Git-Commit mit aussagekräftiger Message
```

#### When to Use Each Agent

**Use `build` agent for:**
- Neue Features implementieren
- Bug Fixes
- Code Refactoring
- API Endpoint Erstellung

**Use `plan` agent for:**
- Architektur-Entscheidungen
- Technische Design-Dokumente
- Complex Feature Planning
- Before major refactoring

**Use `code-reviewer` subagent for:**
- Pull Request Reviews
- Code Quality Checks
- Before committing critical code
- Security-focused reviews

**Use `test-engineer` subagent for:**
- Neue Tests erstellen
- Coverage verbessern
- Flaky Tests reparieren
- Test-Strategie entwickeln

**Use `db-specialist` subagent for:**
- Neue Models erstellen
- Schema-Änderungen
- Migration Planning
- Performance Optimization

**Use `documentation-writer` subagent for:**
- API Documentation aktualisieren
- Neue Features dokumentieren
- Docstrings schreiben
- README updates

**Use `security-auditor` subagent for:**
- Security Reviews
- Authentication/Authorization Checks
- Vulnerability Assessments
- Before deploying to production

### Best Practices

1. **Immer zuerst lesen**: AGENTS.md und relevante requirements/*.md Dateien lesen
2. **Tests vor Commit**: Immer `pytest` ausführen vor dem Committen
3. **Skills nutzen**: Passende Skills laden für spezialisierte Aufgaben
4. **German Comments**: Wo angemessen deutsche Kommentare verwenden
5. **Pattern-Konsistenz**: Bestehende Projekt-Patterns folgen
6. **Documentation**: Docstrings für neue Funktionen schreiben
7. **Security**: Security-Auditor vor Production-Deployments konsultieren

### Agent Communication

Für optimale Ergebnisse klare, kontextreiche Anfragen stellen:

**Good:**
```
"Implementiere einen neuen API Endpoint für Task-Filterung nach Priority.
Folge dem bestehenden Pattern in execqueue/api/tasks.py.
Erstelle Unit Tests mit test-engineer.
Lies zuerst requirements/1. Background Worker.md für Kontext."
```

**Bad:**
```
"Mach Task-Filterung."
```

### Troubleshooting

**Tests fail after changes:**
→ Load `test-runner` skill und führe `pytest -v` aus
→ Prüfe spezifische Test-Logs für Fehlerursache

**Database schema issues:**
→ Load `db-migration` skill
→ Prüfe `execqueue/db/engine.py` für Connection-Config
→ Stelle sicher, dass TEST_DATABASE_URL in .env gesetzt ist

**Code quality warnings:**
→ Load `code-review` skill
→ Führe Code-Review durch
→ Implementiere empfohlene Verbesserungen

**Security concerns:**
→ Load `security-auditor` subagent
→ Führe Security-Scan durch
→ Addressiere kritische Issues vor Deployment
