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

## Tests

Minimaler Testansatz mit pytest.

### Ausführung

```bash
pytest
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
