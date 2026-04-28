# ExecQueue

Execution Queue System.

## API

The project exposes a minimal FastAPI application with tenant-neutral system
routes and a reserved `/api` namespace for later domain APIs.

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
- OpenCode is never started, stopped, or restarted by ExecQueue. It is treated as an optional external HTTP service.

### Restart

Global restart via script:

```bash
./ops/scripts/global_restart.sh
```

Restarts the following services in order:
1. API
2. Telegram Bot

Note: OpenCode is never restarted by ExecQueue. It must be managed separately.

### OpenCode

ExecQueue supports only an external OpenCode endpoint contract.

Configuration:

```bash
OPENCODE_MODE=disabled
OPENCODE_BASE_URL=http://127.0.0.1:4096
OPENCODE_TIMEOUT_MS=1000
```

Valid modes:

- `disabled`
- `external_endpoint`

Example local OpenCode start command:

```bash
opencode serve --hostname 127.0.0.1 --port 4096
```

ExecQueue never starts, stops, or restarts OpenCode. When enabled, it only
checks whether the configured HTTP endpoint is reachable.

### Endpoints

- `GET /health` returns the aggregated system health
- `GET /api/health` returns the API component health
- `GET /db/health` returns the database component health
- `GET /telegram-bot/health` returns the Telegram bot component health
- `GET /opencode/health` returns the OpenCode endpoint reachability
- `GET /docs` exposes Swagger UI
- `GET /openapi.json` exposes the generated OpenAPI document

#### Health Status Semantics

The `/health` endpoint returns:
- `status`: Core system status (OK, DEGRADED, ERROR) based only on required components (API, Database, Telegram Bot)
- `checks`: Detailed status for all components including optional integrations

OpenCode is treated as an optional integration. Its status is reported in the
`checks.opencode` object but does not affect the core `status` field.

OpenCode reachability states:
- `disabled`: OpenCode integration is not configured
- `invalid_config`: OpenCode URL configuration is malformed
- `available`: OpenCode endpoint is reachable and responding with 2xx
- `unreachable`: Connection refused or DNS failure
- `timeout`: Probe exceeded the configured timeout
- `unexpected_response`: Endpoint responded with 4xx or 5xx status

An unreachable, timed-out, or misconfigured OpenCode endpoint does not degrade
the core system status. OpenCode is isolated from API, DB, and Telegram
lifecycle management.

### Telegram Bot

The Telegram bot runs as a separate process and is disabled by default.

#### Configuration

Copy `.env.example` to `.env` and configure:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_BOT_ENABLED=false
TELEGRAM_POLLING_TIMEOUT=30
TELEGRAM_SHUTDOWN_TIMEOUT=8
```

#### Installation

```bash
pip install -e ".[dev,telegram]"
```

#### Start

```bash
python -m execqueue.workers.telegram.bot
```

#### Available Commands

- `/start` - Shows welcome message and command list
- `/health` - Shows the aggregated system health report
- `/restart` - Admin-only restart command for API and Telegram runtime

The `/api` router namespace is reserved for later fachliche endpoints. No
business routes are implemented there yet.

### Context Headers

The current API does not require context headers. To keep later shared domain
endpoints forward-compatible, `X-Tenant-ID` is the reserved request header
convention for future tenant-aware handlers under `/api`.

## Setup

### Installation

```bash
pip install -e ".[dev]"
```

### Environment

Copy `.env.example` to `.env` and set separate PostgreSQL URLs for normal
runtime and tests.

```bash
APP_ENV=development
DATABASE_URL=postgresql+psycopg://execqueue:change-me@localhost:5432/execqueue
DATABASE_URL_TEST=postgresql+psycopg://execqueue_test:change-me@localhost:5432/execqueue_test
```

The runtime never falls back from `DATABASE_URL_TEST` to `DATABASE_URL`. Tests
must use the dedicated test database URL exclusively.

## Database Runtime Base

`execqueue.settings.Settings` exposes:

- `APP_ENV` with `development`, `test`, and `production`
- `DATABASE_URL` for non-test runtime
- `DATABASE_URL_TEST` for pytest or explicit `APP_ENV=test`
- `OPENCODE_MODE`, `OPENCODE_BASE_URL`, and `OPENCODE_TIMEOUT_MS` for external OpenCode checks

## Database Migrations

Alembic is configured in `alembic/` and uses the same settings-based database
selection as the runtime.

Common commands:

```bash
py -m alembic upgrade head
py -m alembic downgrade base
```

## Tests

Minimal test setup with pytest.

### Run

```bash
py -m pytest
```

### Validation focus

- Tests must never run with `APP_ENV=production`.
- `DATABASE_URL_TEST` must stay separate from `DATABASE_URL`.
- OpenCode tests cover `disabled`, `external_endpoint + unreachable`, and `external_endpoint + reachable`.
