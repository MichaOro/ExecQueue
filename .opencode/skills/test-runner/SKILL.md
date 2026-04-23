---
name: test-runner
description: Run tests with proper setup and verify all tests pass before committing
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: testing
---

## Was ich tue
- Führe Tests mit der korrekten Konfiguration aus (EXECQUEUE_TEST_MODE, TEST_DATABASE_URL)
- Stelle sicher, dass Test-Database-Setup korrekt erfolgt
- Prüfe ob alle Tests bestehen bevor Commits erlaubt werden
- Identifiziere flüchtige Tests (flaky tests) bei wiederholter Ausführung
- Analysiere Test-Abdeckung und empfiehlt Verbesserungen
- Repariere fehlerhafte Tests mit klaren Fixes

## Wann du mich verwendest
- Vor jedem Commit: "Run tests and ensure they all pass"
- Nach Code-Änderungen: "Verify tests still pass after my changes"
- Bei Test-Fehlern: "Fix the failing tests in <file>"
- Für neue Features: "Add tests for the new functionality"
- Für Coverage-Reports: "Check test coverage and identify gaps"

## Test-Konventionen im Projekt
- `asyncio_mode = auto` in pytest.ini
- Tests verwenden `EXECQUEUE_TEST_MODE` oder auto-detect via `PYTEST_CURRENT_TEST`
- Test-Daten erhalten `test_` Prefix via `apply_test_label()` Helper
- Alle Tests müssen bestehen bevor commited wird
- AAA-Struktur (Arrange-Act-Assert) für alle Tests

## Coverage Targets
- **Models**: 95%
- **Services**: 90%
- **API**: 85%
- **Scheduler**: 80%

## Test-Ausführung
```bash
# Alle Tests
pytest

# Mit Detail-Output
pytest -v

# Spezifischer Test-File
pytest tests/test_tasks.py

# Mit Coverage-Report
pytest --cov=execqueue --cov-report=term-missing

# Nur bestimmte Test
pytest -k test_task_creation
```

## Bekannte Issues & Fixes

### OpenCode Adapter Tests
**Problem**: 4 Tests fehlen MockTransport Setup  
**Lösung**:
```python
from httpx import MockTransport

def mock_opencode_request(request):
    # Return mock response
    return Response(200, json={"result": "mocked"})

transport = MockTransport({"https://api.opencode.ai/*": mock_opencode_request})
```

### DLQ Tests
**Problem**: DLQ Tests benötigen `client` fixture in conftest.py  
**Lösung**:
```python
@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

### Async Test Issues
**Problem**: Async Tests laufen nicht korrekt  
**Lösung**:
```python
import pytest

@pytest.mark.asyncio
async def test_something():
    # Async test code
    pass
```

## Troubleshooting

### Tests fail with "no such table"
→ Stelle sicher, dass `create_db_and_tables()` vor Tests aufgerufen wird

### Tests fail with connection errors
→ `TEST_DATABASE_URL` in `.env` prüfen

### Flaky Tests
→ Bei Race Conditions: `asyncio.Lock()` oder bessere Isolation verwenden

### Coverage zu niedrig
→ Edge Cases und Error-Pfade testen
