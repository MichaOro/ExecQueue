# Integration Tests für ExecQueue

## Überblick

Dieses Verzeichnis enthält Integrationstests für ExecQueue. Im Gegensatz zu Unit-Tests verwenden Integrationstests echte externe Services (APIs, Datenbanken, etc.).

## Voraussetzungen

### Environment Variables

Für OpenCode Integrationstests muss `OPENCODE_BASE_URL` gesetzt sein:

```bash
export OPENCODE_BASE_URL="https://your-opencode-api.local"
```

Optional:
```bash
export OPENCODE_TIMEOUT=120        # Timeout in Sekunden (default: 120)
export OPENCODE_MAX_RETRIES=3      # Max retries (default: 3)
```

## Tests ausführen

### Alle Integrationstests

```bash
# Nur wenn OPENCODE_BASE_URL gesetzt ist
pytest tests/integration/ -v
```

### Integrationstests ausschließen

```bash
# Alle Tests außer Integrationstests
pytest -m "not integration"

# Oder explizit integration tests skippen
SKIP_INTEGRATION_TESTS=true pytest
```

### Spezifische Integrationstests

```bash
# Einzelnen Test ausführen
pytest tests/integration/test_opencode_adapter.py::test_real_api_call -v

# Alle OpenCode Integrationstests
pytest tests/integration/test_opencode_adapter.py -v
```

## Test-Struktur

### Verzeichnisstruktur

```
tests/integration/
├── __init__.py
├── test_opencode_adapter.py    # OpenCode API Integration
└── README.md                   # Diese Datei
```

### Test-Markers

- `@pytest.mark.integration` – Markiert Tests als Integrationstests
- Tests ohne Marker werden standardmäßig ausgeführt
- Integrationstests können mit `-m "not integration"` ausgeschlossen werden

## Skip-Verhalten

Integrationstests werden **automatisch übersprungen** wenn:

1. `OPENCODE_BASE_URL` nicht gesetzt ist
2. Externe API nicht erreichbar ist (Timeout/ConnectionError)
3. `SKIP_INTEGRATION_TESTS=true` gesetzt ist

**Beispiel:**
```python
@pytest.mark.integration
def test_real_api_call():
    if not os.getenv("OPENCODE_BASE_URL"):
        pytest.skip("OPENCODE_BASE_URL not set")
    # Test logic...
```

## Expected Runtime

| Test-Typ | Typische Duration |
|----------|-------------------|
| Unit Tests | 0.1-2 Sekunden |
| Integration Tests | 5-60 Sekunden (API-abhängig) |

**Hinweis:** Integrationstests sind langsamer und sollten nicht bei jedem Commit ausgeführt werden.

## CI/CD Integration

### GitHub Actions Beispiel

```yaml
jobs:
  test:
    steps:
      # Unit Tests (immer)
      - run: pytest -m "not integration"
      
      # Integration Tests (nur wenn API konfiguriert)
      - name: Run Integration Tests
        if: env.OPENCODE_BASE_URL != ''
        run: pytest tests/integration/ -v
        env:
          OPENCODE_BASE_URL: ${{ secrets.OPENCODE_BASE_URL }}
```

## Troubleshooting

### "OPENCODE_BASE_URL not set"

Test wird übersprungen. Setze die Variable:
```bash
export OPENCODE_BASE_URL="https://your-api.local"
```

### Connection Timeout

- Prüfe Netzwerkverbindung
- Erhöhe Timeout: `export OPENCODE_TIMEOUT=300`
- Test ist als "flaky" markiert – erneut ausführen

### API Error (4xx/5xx)

- Prüfe API-Status
- Prüfe Authentifizierung (falls nötig)
- Logs anzeigen: `pytest -v --log-cli-level=INFO`

## Wartung

### Neue Integrationstests hinzufügen

1. Neue Datei in `tests/integration/` erstellen
2. Mit `@pytest.mark.integration` dekorieren
3. Skip-Logik für fehlende Config implementieren
4. Zu README hinzufügen

### Tests aktualisieren

Bei API-Änderungen:
1. Tests anpassen
2. README aktualisieren
3. Changelog eintragen

---

**Erstellt:** 2026-04-23 (Arbeitspaket 1-04)
**Status:** ⏳ Ready for Implementation
