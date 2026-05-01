# Arbeitspaket 01 - Error Classification & Typen

## Ziel

Etablierung der Fehlerklassifizierungs-Infrastruktur gemäß REQ-018. Nutzung der bereits existierenden `ErrorType`-Enum und `classify_error()`-Funktion aus `execqueue/runner/error_classification.py`.

## Aufwand

~2h

## Fachlicher Kontext

REQ-018 erfordert eine klare Trennung zwischen **recoverable** und **non-recoverable** Fehlern. Die Codebase bietet bereits eine umfassende Infrastruktur mit:

- `ErrorType` Enum (TRANSIENT, PERMANENT, CONFLICT, TIMEOUT, CONTRACT_VIOLATION, VALIDATION_FAILED)
- `classify_error()` Funktion mit pattern-basiertem Matching
- HTTP Status Code Mapping
- Custom Exceptions (ConflictError, ValidationError, ContractViolationError)

## Codebase-Kontext

### Relevante Artefakte

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/error_classification.py` (578 Zeilen)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/recovery.py` (736 Zeilen)

### CODEBASE-INSIGHTS

1. **Line 35-74**: `ErrorType` Enum definiert alle Fehlerkategorien
2. **Line 54-60**: `is_retryable` Property - nur TRANSIENT und TIMEOUT sind retryable
3. **Line 188-276**: `classify_error()` mit umfassender Pattern-Erkennung
4. **Line 528-552**: Custom Exception Types bereits definiert

### CODEBASE-ASSUMPTIONS

1. Die `classify_error()`-Funktion wird bereits in `RecoveryService.handle_error()` verwendet
2. Die ErrorType-Klassifizierung deckt alle REQ-018 Anforderungen ab

### CODEBASE-RISKS

1. **R-1**: Nicht alle REQ-018 Fehlerkategorien sind explizit abgebildet (z.B. "Network", "Rate-Limit")
2. **R-2**: Die Mapping von REQ-018 "Recoverable/Non-Recoverable" auf `ErrorType.is_retryable` muss validiert werden

## Voranalyse

### Anpassungsstellen

- **Keine neuen Module nötig** - bestehende Infrastruktur verwenden
- Eventuell Erweiterung der `ErrorType`-Enum um spezifischere Kategorien
- Eventuell Erweiterung der `classify_error()` um additional Patterns

### Patterns

- Pattern-basierte Fehlererkennung in `classify_error()`
- HTTP Status Code Mapping (4xx vs 5xx)
- Exception Message Pattern Matching

### Wiederverwendung

- `ErrorType` Enum direkt verwenden
- `classify_error()` direkt verwenden
- `RetryMatrix` für retry decisions verwenden

### Risiken

- **R-1**: Fehlende Fehlerkategorien müssen identifiziert werden
- **R-2**: Inkonsistente Mapping zwischen REQ-018 und Implementierung

## Technical Specification

### Änderungen (empfohlen)

**Keine Änderungen erforderlich** - bestehende Infrastruktur nutzen.

Falls Erweiterungen nötig:

1. **`execqueue/runner/error_classification.py`**:
   - Line 35-74: `ErrorType` um `RATE_LIMIT`, `NETWORK_ERROR` erweitern (optional)
   - Line 188-276: `classify_error()` um zusätzliche Patterns erweitern

### Flow-Integration

```
Task Execution → Exception Caught → classify_error() → ErrorType → is_retryable?
    ↓
RecoveryService.handle_error() → RetryDecision → Retry or Fail
```

### Seiteneffekte

- Keine

### Tests

- Bestehende Tests in `tests/test_error_classification.py` prüfen
- Fehlende Tests für neue Patterns hinzufügen

### Neue Module + Begründung

- **Keine** - bestehende Infrastruktur verwenden

## Umsetzungsspielraum

### Flexible Bereiche

- Entscheidung, ob zusätzliche `ErrorType`-Kategorien eingeführt werden
- Entscheidung, ob zusätzliche Patterns in `classify_error()` eingefügt werden
- Naming der zusätzlichen Kategorien

### Fixe Bereiche

- **Nicht verändern**: Bestehende `ErrorType`-Kategorien ohne zwingenden Grund
- **Nicht verändern**: Bestehende `classify_error()`-Logik ohne Tests
- **Muss erhalten bleiben**: `is_retryable` Property Logik

## Umsetzungsschritte

1. **Code Review** von `execqueue/runner/error_classification.py`
2. **Gap Analysis**: REQ-018 Fehlerkategorien vs. `ErrorType` Enum
3. **Entscheidung**: Erweiterungen nötig?
4. **Falls ja**:
   - `ErrorType` erweitern
   - `classify_error()` erweitern
   - Tests schreiben
5. **Validierung**: Bestehende Tests laufen lassen

## Abhängigkeiten

- Keine externen Abhängigkeiten
- Selbst-contained Modul

## Akzeptanzkriterien

- [ ] `ErrorType` Enum deckt alle REQ-018 Fehlerkategorien ab
- [ ] `classify_error()` klassifiziert alle definierten Fehler korrekt
- [ ] `is_retryable` Property stimmt mit REQ-018 "Recoverable" überein
- [ ] Bestehende Tests bestehen
- [ ] Neue Tests für zusätzliche Patterns (falls eingeführt)

## Entwickler-/Agent-Validierung

### Zu prüfende Dateien

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/runner/error_classification.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/tests/test_error_classification.py` (falls existent)

### Kritische Annahmen

1. `ErrorType.is_retryable == True` ≙ REQ-018 "Recoverable"
2. `ErrorType.is_retryable == False` ≙ REQ-018 "Non-Recoverable"

### Manuelle Checks

1. REQ-018 Abschnitt 4 "Fehlerkategorien" mit `ErrorType` Enum abgleichen
2. `classify_error()` Implementation mit REQ-018 Abschnitt 5 "Retry-Logik" abgleichen

## Risiken

| Risiko | Auswirkung | Gegenmaßnahme |
|--------|------------|---------------|
| Falsche Klassifizierung | Unnötige Retries oder vorzeitiger Abort | Tests schreiben, Logging aktivieren |
| Fehlende Patterns | Fehler werden nicht erkannt | Gap Analysis durchführen |

## Zielpfad

`/home/ubuntu/workspace/IdeaProjects/ExecQueue/docs/REQ-018/01_error_classification.md`
