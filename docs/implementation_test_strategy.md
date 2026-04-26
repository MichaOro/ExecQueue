# Implementierungs-Teststrategie

## TL;DR
Tests werden entlang von zwei Dimensionen klassifiziert:

1. **Systemkritikalität** – Einfluss auf die Systemstabilität
2. **Business-Logik-Abdeckung** – Bedeutung für korrektes Verhalten

Ein kombinierter Score bestimmt die Priorität: **Kritisch, Hoch, Mittel, Niedrig**

Für jede Implementierung muss in der Validierungsphase entschieden werden, ob **Unit-Tests und/oder Integrationstests erstellt oder aktualisiert werden müssen**.

Ziel: **Sinnvolle, breite Testabdeckung ohne unnötige Aufblähung der Test-Suite**

---

## 1. Ziele

- Sicherstellung der **funktionalen Korrektheit**
- Sicherstellung der **Systemstabilität**
- Minimierung von **Testlücken (Delta)**
- Balance zwischen **Geschwindigkeit und Qualität**
- Unterstützung von **LLM + Mensch Zusammenarbeit**
- **Sinnvolle und breite Abdeckung** ohne redundante Tests
- Möglichst kleine, aber ausreichende Testoberfläche

---

## 2. Testarten

### Unit-Tests

- Testen isolierte Logik
- Verwenden Mocks/Stubs, wo sinnvoll
- Schnell, deterministisch, eng abgegrenzt
- Geeignet für:
    - Business-Regeln
    - Parsing
    - Mapping
    - Validierung
    - Scoring
    - Formatierung
    - Entscheidungslogik

**Beispiel:**
- Validierung einer DB-Konfiguration mit gemockten Umgebungswerten

---

### Integrationstests

- Testen das Zusammenspiel echter Komponenten
- Möglichst **keine Mocks auf kritischen Pfaden**
- Validieren:
    - Infrastruktur
    - Wiring
    - Konfiguration
    - Laufzeitverhalten
    - externe Schnittstellen
    - Persistenz

**Beispiele:**
- Echte DB-Verbindung gegen Testdatenbank
- FastAPI-Endpoint mit Test-Client
- Telegram-Command über internen Dispatcher (ohne echte API, sofern nicht nötig)

---

## 3. Regeln für Test-Erstellung / -Update

Für jede Implementierung prüfen:

- Neue Tests erstellen, wenn Verhalten noch nicht abgedeckt ist
- Bestehende Tests anpassen, wenn sich Verhalten geändert hat
- **Keine neuen Tests**, wenn bereits ausreichend abgedeckt
- Bestehende Tests **erweitern statt duplizieren**
- Testoberfläche klein halten, aber ohne relevante Lücken

Wenn kein Test nötig ist → **Begründung dokumentieren**

---

## Zielzustand

- Gute Unit-Test-Abdeckung für isolierte Logik
- Gute Integrationstest-Abdeckung für kritische Flows
- Keine künstliche Testaufblähung
- Keine redundanten Tests
- Klare Nachvollziehbarkeit zwischen Requirement, Code und Tests

---

## 4. Bewertungsmodell (Scoring)

### 4.1 Systemkritikalität

| Score | Bedeutung |
|------:|----------|
| 1     | Kernsystem (DB, API) |
| 2     | Wichtiges Feature |
| 3     | Nice-to-have / Edge Case |

---

### 4.2 Business-Logik-Abdeckung

| Score | Bedeutung |
|------:|----------|
| 1     | Muss explizit getestet werden |
| 2     | Sollte getestet werden |
| 3     | Implizit abgedeckt / redundant |

---

## 5. Prioritätsberechnung

```text
Priorität = Kritikalität + Abdeckung
```

### Mapping

| Score | Priorität |
|------:|-----------|
| 2     | Kritisch |
| 3     | Hoch |
| 4     | Mittel |
| 5–6   | Niedrig |

---

## 6. Struktur der Test-Planungstabelle

| Test-Datei | Testname | Priorität | Typ | Erfolgskriterien | Fehlerkriterien | Begründung |
|---|---|---:|---|---|---|---|
| `tests/integration/test_health.py` | `test_health_returns_system_status` | Hoch | Integration | Endpoint liefert korrekte Health-Daten | Endpoint fehlt / falsche Daten / Fehler | Validiert Betriebsbereitschaft |

---

### Spaltenbeschreibung

| Spalte | Zweck |
|---|---|
| `Test-Datei` | Pfad zur Testdatei |
| `Testname` | Konkreter Testname |
| `Priorität` | Kritisch / Hoch / Mittel / Niedrig |
| `Typ` | Unit oder Integration |
| `Erfolgskriterien` | Wann der Test besteht |
| `Fehlerkriterien` | Welche Fehler erkannt werden |
| `Begründung` | Warum dieser Test existiert |

---

## 7. Beispiele

### DB-Verbindung

- Kritikalität: 1
- Abdeckung: 1  
  → Score = 2 → **Kritisch**

Begründung:  
Core-Komponente → echter Integrationstest erforderlich

---

### /health Command Existenz

- Kritikalität: 2
- Abdeckung: 3  
  → Score = 5 → **Niedrig**

Begründung:  
Implizit durch Ergebnis-Test abgedeckt

---

### /health Ergebnisvalidierung

- Kritikalität: 2
- Abdeckung: 1  
  → Score = 3 → **Hoch**

Begründung:  
Validiert Funktionsfähigkeit + Systemstatus

---

## 8. Ordnerstruktur

```text
/tests
  /unit
  /integration
  /clusters
```

---

## 9. Test-Clustering

Cluster:

- critical (kritisch)
- high (hoch)
- medium (mittel)
- low (niedrig)

Beispiel:

```yaml
priority: critical
type: integration
requirement: telegram_start
```

---

## 10. Requirement-basierte Dokumentation

Pfad:

```text
/docs/tests/<requirement>.md
```

### Inhalt:

- Implementierungsbereich
- Zugehörige Tests
- Klassifikation (Unit/Integration)
- Priorität
- Erfolgskriterien
- Fehlerkriterien
- Coverage-Erklärung
- Entscheidung:
    - neuer Test
    - Update
    - kein Test
- Begründung gegen Redundanz

---

## 11. LLM-Workflow Integration

### Implementierungsphase

- Minimaler Prompt
- Fokus auf Feature
- Keine spekulativen Tests

### Validierungsphase

- Unit-Tests für neue/geänderte Logik
- Integrationstests für:
    - Komponenteninteraktion
    - Infrastruktur
    - APIs / DB / Runtime
- Bestehende Tests anpassen statt duplizieren
- Dokumentation aktualisieren
- Testübersicht pflegen

---

## 12. Guardrails

- Kein Integrationstest bei kritischen Pfaden → FAIL
- Nur Mock-DB-Tests → nicht ausreichend
- Redundante Tests → nur mit Begründung
- Jedes Requirement → Test oder dokumentierte Abdeckung
- Neue Logik ohne Testentscheidung → FAIL
- Testabdeckung breit genug, aber nicht künstlich aufgebläht

---

## 13. Best Practices

- Klarheit vor Quantität
- Kontrollierte Redundanz nur bei Mehrwert
- Mindestens ein echter Integrationstest für kritische Komponenten
- Deterministische Tests
- Kein Over-Mocking bei Infrastruktur
- Bestehende Tests bevorzugt erweitern
- Kleine, fokussierte Testoberfläche
- Keine Tests auf instabile Implementierungsdetails
- Unit = Logik, Integration = Verhalten

---

## 14. Zusammenfassung

Diese Strategie ermöglicht:

- Skalierbare Testarchitektur
- Konsistente Qualität bei Mensch + LLM
- Kontrolliertes Wachstum der Test-Suite
- Klare Priorisierung nach Risiko
- Sinnvolle und breite Testabdeckung
- Minimale Redundanz und Wartungskosten
