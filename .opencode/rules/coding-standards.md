# Implementierungskredo & Coding Standards

## Philosophie

Wir entwickeln mit dem Ziel einer **schlanken, verständlichen und wartbaren Codebasis**. Bestehende Strukturen, Module und etablierte Patterns werden bevorzugt erweitert, statt vorschnell neue Ebenen, Dateien oder Abstraktionen einzuführen. Jede Änderung soll sich natürlich in die vorhandene Architektur einfügen und den Bestand verbessern, nicht fragmentieren.

### Grundprinzipien

- **Clean Code mit minimaler Invasivität**: Änderungen nur dort, wo fachlich notwendig, mit möglichst wenig Seiteneffekten
- **Keine präventiven Abstraktionen**: Nicht für hypothetische zukünftige Anforderungen generalisieren, sondern für den realen, aktuellen Bedarf
- **Keine redundanten Logik**: Bestehende Logik nicht duplizieren, sondern bei sinnvoller Wiederverwendung sauber gebündelt
- **Keine künstliche Zentralisierung**: Wiederverwendung nur wenn sie die Wartbarkeit tatsächlich erhöht
- **Technische Komplexität ist kein Selbstzweck**: Bewusst niedrig halten
- **Balanciertes Design**: Weder Monolithisierung noch übertriebene Zerlegung, sondern Robustheit und Pragmatismus

### Qualitätsziele

Jede Implementierung muss sich an folgenden Kriterien messen lassen:

1. **Einfach verständlich** - Ohne unnötige mentale Last erfassbar
2. **Fachlich sauber eingeordnet** - Klare Zuordnung zu Domänen
3. **Ohne redundante Logik** - DRY-Prinzip strikt anwenden
4. **Ohne unnötige technische Tiefe** - Keine überflüssigen Schichten
5. **Leicht testbar und wartbar** - Isolierte, klare Strukturen
6. **Konsistent mit bestehenden Mustern** - Projekt-Patterns erweitern statt brechen

### Die Schnittregel: Schlanker Code vor Atomisierung

**Im Zweifel gilt: Die einfachere, klarere und besser in den Bestand passende Lösung ist der besseren technischen Idee vorzuziehen.**

Neue Dateien oder Module werden **nur** dann eingeführt, wenn mindestens einer der folgenden Punkte erfüllt ist:

1. **Wiederverwendung**: Die Logik wird an mehreren Stellen sinnvoll wiederverwendet
2. **Übersichtlichkeit**: Eine bestehende Datei würde fachlich unsauber oder deutlich unübersichtlicher werden
3. **Fachliche Grenze**: Es existiert eine echte fachliche Grenze innerhalb der bestehenden Architektur

**Kapselung** wird dort eingesetzt, wo sie Verständlichkeit, Änderbarkeit und Wiederverwendung verbessert. Bündelung von Logik soll nicht maximal, sondern **sinnvoll** erfolgen: **so viel wie nötig, so wenig wie möglich.**

### Beispiele

**❌ Schlecht (über-atomisiert):**
```
services/task/creation.py
services/task/validation.py
services/task/persistence.py
services/task/notification.py
```

**✅ Gut (zusammengefasst):**
```
services/task_service.py  # Alle Task-bezogenen Operationen in einer Datei
```

**❌ Schlecht (unnötig neue Datei):**
```python
# Neue Datei utils/date_helpers.py nur für eine Funktion
def format_timestamp(ts): ...
```

**✅ Gut (im bestehenden Kontext):**
```python
# In der bestehenden Datei, wo es verwendet wird
def format_timestamp(ts): ...
```

---

## FastAPI/SQLModel spezifische Regeln

### API Layer
- Routes in `api/` nach Domain gruppieren (tasks, requirements, work-packages)
- Dependency Injection für gemeinsame Logik verwenden
- Error Handling konsistent mit HTTPException
- Keine direkten DB-Queries in API-Endpoints

### Services Layer
- Geschäftslogik in `services/` zentralisieren
- Service-Funktionen sollten testbar und isoliert sein
- Bestehende Services erweitern statt neue zu erstellen
- Keine redundanten Service-Schichten

### Models Layer
- SQLModel Patterns konsistent verwenden
- Relationships klar definieren
- `is_test` Filter in allen Queries beachten
- Model-Erweiterungen bevorzugen vor neuen Models

### Datenbank
- **Keine Alembic-Migrations** (manuelle Schema-Verwaltung via `SQLModel.metadata.create_all()`)
- Test-Daten erhalten `test_` Prefix
- Schema-Änderungen nur nach Impact Assessment

---

## Code Quality Anforderungen

### Before You Code
1. Bestehende Patterns im Projekt analysieren
2. AGENTS.md, requirements/*.md und diese Datei lesen
3. Prüfen ob bestehender Code erweitert werden kann
4. Minimale Invasivität sicherstellen

### During Development
1. Clean Code Prinzipien anwenden
2. Type Hints für alle Funktionen verwenden
3. Docstrings für öffentliche APIs schreiben (Google/Numpy Style)
4. Keine premature Optimization
5. Redundante Logik vermeiden
6. Bestehende Strukturen erweitern

### Before Commit
1. Alle Tests müssen bestehen (`pytest`)
2. Code-Review durch code-reviewer Subagent
3. Git diff prüfen auf unbeabsichtigte Änderungen
4. German Comments wo angemessen
5. Sicherstellen, dass Änderungen minimal invasiv sind

---

## Testing Conventions

### Framework Setup
- `asyncio_mode = auto` in pytest.ini
- Test-Daten mit `test_` Prefix
- Isolierte Tests (jede Test eigene DB-Session)
- Mocking für externe Services (httpx.MockTransport)

### Coverage Targets
- **Models**: 95%
- **Services**: 90%
- **API**: 85%
- **Scheduler**: 80%

### Test-Qualität
- Klare AAA-Struktur (Arrange-Act-Assert)
- Test-Namen beschreiben das Verhalten
- Keine redundanten Tests
- Flaky Tests sofort reparieren

---

## Projekt-spezifische Gotchas

1. **`updated_at` nicht auto-updated**: Manuell setzen in Scheduler/API (kein `onupdate`)
2. **`is_test` Filter wiederholt**: Every query filters `is_test == is_test_mode()` - Zentralisierung erwägen
3. **SQL Logging disabled**: `echo=False` in engine.py - Für Debugging temporär aktivieren
4. **OpenCode Adapter Tests**: 4 Tests benötigen `httpx.MockTransport` Setup

---

## Workflows

### Neue Feature Implementierung
```
1. PLAN (optional für große Features):
   → @plan Implementierungsplan erstellen
   → Bestehende Patterns analysieren
   → Minimale Invasivität sicherstellen

2. BUILD:
   → @build Feature nach Plan implementieren
   → Bestehende Code-Strukturen erweitern
   → Keine präventiven Abstraktionen

3. TEST:
   → @test-engineer Tests erstellen und validieren
   → Coverage prüfen
   → Alle Tests müssen grün sein

4. REVIEW:
   → @code-reviewer Code-Review durchführen
   → Clean Code prüfen
   → Redundanz-Check

5. COMMIT:
   → Nur wenn alle Tests grün
   → Git diff prüfen
   → aussagekräftige Commit-Message
```

### Datenbank-Änderungen
```
1. @db-specialist Impact Assessment erstellen
2. Migration Plan dokumentieren
3. In Test-DB validieren
4. Backup vor Produktion-Änderungen
5. Schema-Änderung manuell durchführen
6. Tests erneut ausführen
```

### Security-Critical Changes
```
1. @security-auditor Security Review anfordern
2. OWASP Top 10 prüfen
3. Remediation umsetzen
4. Erneute Prüfung nach Fixes
5. Security-Documentation aktualisieren
```

### Code-Refactoring
```
1. Bestehende Code-Struktur analysieren
2. Redundanz-Potential identifizieren
3. Minimal-invasive Refactoring-Strategie entwickeln
4. @code-reviewer Review einholen
5. Schrittweise Umstellung mit Tests
6. Keine funktionale Änderung ohne Grund
```

---

## Agent-Interaktion

### Wichtige Schnittstellen

- **@build** - Full implementation with all tools
- **@plan** - Analysis without code changes
- **@code-reviewer** - Quality and security review
- **@test-engineer** - Test creation and validation
- **@db-specialist** - Database schema changes
- **@documentation-writer** - Documentation updates
- **@security-auditor** - Security analysis

### Prompting Best Practices

**Good:**
```
"Implementiere Task-Filterung nach Priority.
Folge dem bestehenden Pattern in execqueue/api/tasks.py.
Erweitere bestehenden Code minimal invasiv.
Keine neuen Module wenn bestehende erweitert werden können."
```

**Bad:**
```
"Mach Task-Filterung."
```

---

## Referenzen

- FastAPI Documentation: https://fastapi.tiangolo.com/
- SQLModel Documentation: https://sqlmodel.tiangolo.com/
- pytest Documentation: https://docs.pytest.org/
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- AGENTS.md - Agent usage guidelines
- requirements/*.md - Projekt-Anforderungen
