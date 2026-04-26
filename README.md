# ExecQueue

Execution Queue System.

## API

The project now includes a minimal FastAPI setup that keeps technical system
endpoints separate from a future domain API area for tenant-aware features.

### Start

```bash
uvicorn execqueue.main:app --reload
```

### Endpoints

- `GET /health` returns `{ "status": "ok" }`
- `GET /docs` exposes Swagger UI
- `GET /openapi.json` exposes the generated OpenAPI document

Technical endpoints stay global and do not require tenant headers.

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
