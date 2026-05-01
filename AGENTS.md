# ExecQueue - Agent Instructions

## Project Type
Python 3.10+ application under initial setup. No production code yet.

## Installation
```bash
pip install -e ".[dev]"
```

## Testing
- **Framework**: pytest with pytest-asyncio (auto mode)
- **Command**: `pytest`
- **Location**: `tests/`
- **Current scope**: Infrastructure smoke tests only

## Key Files
- `pyproject.toml` - Build config, dependencies, pytest settings
- `README.md` - Setup and test documentation
- `tests/test_smoke.py` - Current test suite

## Architecture Notes
- Project is in bootstrap phase
- FastAPI/httpx are optional dev dependencies (future use)
- No unit/integration separation yet
- No CI/CD configured
- No coverage requirements

## When Adding Code
1. Create modules in appropriate location (no `src/` layout currently)
2. Add tests alongside or in `tests/`
3. Update `pyproject.toml` dependencies if needed

## Available Agents

### Implementation Agents
- **python-backend-task**: Implement or refactor Python backend code with small, test-backed changes.
- **fastapi-route-task**: Add or change FastAPI routes while keeping router wiring and tests aligned.
- **pytest-task**: Expand or repair the pytest suite with focused coverage.
- **ops-debug-task**: Inspect operational scripts and logs without introducing unsafe automation.

### Analysis & Planning Agents
- **requirements-engineer-task**: Transform stakeholder input into structured requirement artifacts (user stories, acceptance criteria, functional specs).
- **technical-requirements-engineer-task**: Translate requirements into technical specs, code snippets, and lint-aware validation plans.
