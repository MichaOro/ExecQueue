---
name: code-review
description: Review code for FastAPI best practices, SQLModel patterns, and project conventions
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: review
---

## Was ich tue
- Prüfe Code auf FastAPI Best Practices
- Validiere SQLModel-Definitionen und Relationships
- Stelle sicher, dass Testing Conventions eingehalten werden
- Identifiziere wiederholte `is_test` Filter (Sollte zentralisiert werden)
- Prüfe auf korrekte Async/Await Verwendung
- Security-Review gemäß OWASP Top 10
- Performance-Optimierungen vorschlagen (N+1 Queries, Indizes)

## Wann du mich verwendest
- Vor PRs: "Review this code for best practices"
- Bei Refactorings: "Check if my refactoring follows project conventions"
- Für neue APIs: "Review this FastAPI endpoint implementation"
- Vor Commits: "Review this code before I commit"
- Für Security: "Security review of this authentication code"

## Review-Fokuspunkte

### FastAPI
- Korrekte Dependency Injection
- Status Codes und Exception Handling
- Pydantic/SQLModel Validation
- Async Endpoint Implementation
- Error Response Format konsistent

### SQLModel
- Relationship Definitions korrekt
- Index und Constraint Usage
- Query Optimization mit `joinedload()`
- `is_test` Filter Konsistenz
- `updated_at` manuell setzen

### Testing
- Alle Tests müssen bestehen
- Test-Daten mit `test_` Prefix
- Korrekte Fixture Verwendung
- Mock-Strategie für External Services
- AAA-Struktur (Arrange-Act-Assert)

### Security (OWASP Top 10)
- Authentication/Authorization Checks
- Input Validation und Sanitization
- SQL Injection Prevention
- Sensitive Data Protection
- Security Headers

### Performance
- N+1 Query Prevention
- Database Index Usage
- Async Operations korrekt
- Caching-Strategien

## Bekannte Gotchas

1. **`updated_at` nicht auto-updated**
   → Models haben `default_factory` aber kein `onupdate`
   → Manuell setzen: `task.updated_at = datetime.now(timezone.utc)`

2. **`is_test` filter wiederholt**
   → Jede Query filtert `is_test == is_test_mode()`
   → **Empfehlung**: Zentralisierung in `execqueue/validation/test_mode.py`

3. **No Alembic migrations**
   → Schema via `SQLModel.metadata.create_all()`
   → Manuelle Synchronisation bei Model-Änderungen

4. **SQL logging disabled**
   → `echo=False` in `engine.py`
   → Temporär via `ECHO_SQL=true` für Debugging

5. **OpenCode Adapter Tests brauchen MockTransport**
   → 4 Tests benötigen korrektes Mocking

6. **DLQ tests brauchen `client` fixture**
   → In `tests/conftest.py` hinzufügen

7. **N+1 Queries bei Relationships**
   → Immer `joinedload()` verwenden:
   ```python
   stmt = select(Task).options(joinedload(Task.requirements))
   ```

## Review-Output-Format

```
## Summary
[Approve / Changes Requested / Major Issues]

## Critical Issues
- [Issue] - [Location] - [Fix]

## Major Issues
- [Issue] - [Location] - [Fix]

## Minor Issues
- [Issue] - [Location] - [Suggestion]

## Positive Feedback
- [Good practices observed]

## Recommendations
1. [Specific actionable recommendation]
2. [Second recommendation]
```

## Best Practices für Reviews

- **Konstruktiv**: Gib hilfreiches, respektvolles Feedback
- **Begründet**: Erkläre WARUM etwas problematisch ist
- **Priorisiert**: Unterteile nach Schweregrad
- **Pragmatisch**: Fokus auf tatsächliche Risiken, nicht Perfektion
