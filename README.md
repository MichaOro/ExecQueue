# ExecQueue

Execution Queue System.

## API

The project now includes a minimal FastAPI setup that keeps technical system
endpoints separate from a future domain API area for tenant-aware features.

### Start

```bash
uvicorn execqueue.main:app --reload
```

### Local Orchestrator

Run the API plus the optional Telegram bot through the Python orchestrator:

```bash
python -m execqueue.orchestrator
```

Behavior:

- The API always starts.
- The Telegram bot starts only when `TELEGRAM_BOT_ENABLED=true` and `TELEGRAM_BOT_TOKEN` is set.
- If Telegram is enabled without a token, the orchestrator logs a clear configuration error and keeps the API startup path available.

### Endpoints

- `GET /health` returns `{ "status": "ok" }`
- `GET /docs` exposes Swagger UI
- `GET /openapi.json` exposes the generated OpenAPI document

Technical endpoints stay global and do not require tenant headers.

### Telegram Bot

The Telegram bot runs as a separate process and is disabled by default.

#### Configuration

Copy `.env.example` to `.env` and configure:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_BOT_ENABLED=false
TELEGRAM_POLLING_TIMEOUT=30
```

#### Installation

```bash
pip install -e ".[dev,telegram]"
```

#### Start

Run the bot as a separate process:

```bash
python -m execqueue.workers.telegram.bot
```

The bot starts polling only when `TELEGRAM_BOT_ENABLED=true` and `TELEGRAM_BOT_TOKEN` is set.

#### Available Commands

- `/start` - Shows welcome message and command list
- `/health` - Placeholder (planned, currently inactive)
- `/restart` - Placeholder (planned, currently inactive)

#### Manual Validation

1. Set a valid Telegram bot token in `.env`
2. Set `TELEGRAM_BOT_ENABLED=true`
3. Start the bot process
4. Send `/start` to the bot in Telegram
5. Verify the response contains the command list

#### Notes

- `/health` and `/restart` commands return placeholder messages and do not perform any system actions yet.
- The bot uses long-polling for updates.
- Token is never logged or exposed in runtime output.

The `/api` router namespace is reserved for later fachliche endpoints. No
business routes are implemented there yet.

### Context Headers

The current API does not require context headers. To keep later shared domain
endpoints forward-compatible, `X-Tenant-ID` is the reserved request header
convention for future tenant-aware handlers under `/api`.

This package intentionally does not implement tenant middleware, tenant
resolution, or deployment-based tenant defaults yet.

## Setup

### Installation

```bash
pip install -e ".[dev]"
```

### Environment

Copy `.env.example` to `.env` and set separate PostgreSQL URLs for normal runtime
and tests.

```bash
APP_ENV=development
DATABASE_URL=postgresql+psycopg://execqueue:change-me@localhost:5432/execqueue
DATABASE_URL_TEST=postgresql+psycopg://execqueue_test:change-me@localhost:5432/execqueue_test
```

The runtime never falls back from `DATABASE_URL_TEST` to `DATABASE_URL`. Tests
must use the dedicated test database URL exclusively.
PostgreSQL URLs must declare the driver explicitly with `postgresql+psycopg://`
so runtime, health checks, and Alembic all consume the same value unchanged.

### Database Runtime Base

`execqueue.settings.Settings` now exposes:

- `APP_ENV` with `development`, `test`, and `production`
- `DATABASE_URL` for non-test runtime
- `DATABASE_URL_TEST` for pytest or explicit `APP_ENV=test`

`execqueue.db.runtime.describe_database_target()` returns only a redacted DSN for
safe diagnostics. Credentials are not logged.

### Database Migrations

Alembic is configured in `alembic/` and uses the same settings-based database
selection as the runtime. There is no productive schema creation via
`create_all()`.

Common commands:

```bash
py -m alembic upgrade head
py -m alembic downgrade base
```

The initial migration creates the `project` table with UUID primary key, unique
`key`, runtime timestamps, and an `is_active` flag.

## Tests

Minimaler Testansatz mit pytest.

### Ausführung

```bash
py -m pytest
```

### DB-Validierung

Für den DB-bezogenen Validierungslauf gilt:

- Tests dürfen nie mit `APP_ENV=production` laufen.
- `DATABASE_URL_TEST` muss von `DATABASE_URL` getrennt sein.
- Alembic- und Health-Validierung laufen ausschließlich gegen die Testdatenbank.

Empfohlene Kommandos:

```bash
py -m pytest
py -m pytest tests/test_settings.py tests/test_db_runtime.py tests/test_db_engine_session.py tests/test_alembic_project_migration.py tests/test_db_health.py tests/test_validation_guard.py
py -m alembic upgrade head
py -m alembic downgrade base
```

### Testinfrastruktur

- **Framework**: pytest mit pytest-asyncio für async-Tests
- **Konfiguration**: `pyproject.toml`
- **Testverzeichnis**: `tests/`
- **Aktueller Umfang**: Smoke-Tests zur Infrastrukturvalidierung

### Bewusste Entscheidungen

- Keine Aufteilung in `unit/`, `integration/`, `e2e/` – erfolgt erst bei entsprechender fachlicher Codebasis
- Keine Coverage-Pflicht im initialen Setup
- Keine CI-Pipeline im aktuellen Scope
- Keine künstlichen Test-Fixtures ohne konkrete Wiederverwendung

### Erweiterbarkeit

Tests werden erst bei Vorliegen relevanter produktiver Module eingeführt. Der aktuelle Minimalansatz dient ausschließlich der Validierung der Testinfrastruktur selbst.
