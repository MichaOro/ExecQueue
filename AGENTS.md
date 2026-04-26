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
