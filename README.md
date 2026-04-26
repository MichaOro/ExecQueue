# ExecQueue

Execution Queue System.

## API

The project now includes a minimal FastAPI setup for the current
`single-tenant-local` mode while keeping request-scoped context handling ready
for later shared multi-project or multi-tenant evolution.

### Start

```bash
uvicorn execqueue.main:app --reload
```

### Endpoints

- `GET /health` returns `{ "status": "ok" }`
- `GET /docs` exposes Swagger UI
- `GET /openapi.json` exposes the generated OpenAPI document

Technical endpoints stay global and do not require tenant or project headers.

### Context Headers

The current local mode does not require context headers. To keep the API shape
forward-compatible, later shared endpoints can use:

- `X-Project-ID`
- `X-Tenant-ID`

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
