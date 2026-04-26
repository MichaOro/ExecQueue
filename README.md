# ExecQueue

Execution Queue System.

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
