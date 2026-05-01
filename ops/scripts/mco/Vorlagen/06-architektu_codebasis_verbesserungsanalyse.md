## Kontext

@INPUT_PATH

## Ziel

Identifiziere konkrete Verbesserungen für:

- Wartbarkeit
- Stabilität
- Erweiterbarkeit
- Codequalität
- Architektur-Kohärenz
- berücksichtige die Dokumente unter @INPUT_PATH, betrachte jedoch immer die gesamtanwendung

Fokus:

> Bestehende Struktur stärken, nicht neu erfinden.

---

## Bewertungsdimensionen

- Wartbarkeit
- Lesbarkeit
- Testbarkeit
- Stabilität / Robustheit
- Architektur-Kohärenz
- fachlicher Schnitt
- Komplexität / Over-Engineering
- Performance (falls relevant)

---

## Leitprinzipien

- Clean Code
- DRY
- minimale Invasivität
- Erweiterung > Neuentwicklung
- keine unnötigen Abstraktionen
- keine künstliche Modularisierung
- Kontext schlägt Theorie

---

## Analyseauftrag

Identifiziere gezielt:

- unnötige Abstraktionen
- doppelte Logik
- falsche Verantwortlichkeiten
- übergroße oder überfragmentierte Module
- fehlende fachliche Trennung (falls sinnvoll)
- Performance- oder IO-Probleme
- Schwächen in Fehlerbehandlung, Validierung, Testbarkeit
- Risiken für zukünftige Erweiterungen

Bewerte zusätzlich:

- Architekturentscheidungen
- Wiederverwendbarkeit
- Kohärenz der Struktur
- Robustheit bei Fehlerfällen

---

## Entscheidungslogik

- Keine Refactorings ohne klaren Mehrwert
- Bestehende Struktur bevorzugt erweitern
- Neue Module nur wenn:
    - klare fachliche Grenze
    - echte Wiederverwendung
    - sonst Überladung bestehender Komponenten

---

## Output

Erzeuge eine **strukturierte, priorisierte Verbesserungsanalyse**.

### Struktur

1. Kurzfazit
2. Positiv beibehaltene Strukturen
3. Zentrale Schwachstellen
4. Risiken bei Nichtbehebung

5. Verbesserungen (priorisiert)
    - Hoch
    - Mittel
    - Niedrig

6. Bewusst **nicht empfohlene** Refactorings
7. Empfohlene Umsetzungsreihenfolge
8. Optional: 3–6 Arbeitspakete
9. Test- und Validierungshinweise

---

## Anforderungen je Verbesserung

- Titel
- Problem
- Auswirkung
- Empfehlung
- Betroffene Bestandteile
- Eingriffstiefe (niedrig/mittel/hoch)
- Risiko
- Erwarteter Nutzen
- Erweiterung vs. neues Modul (klar entscheiden)

---

## Output-Regeln

- kein Code
- keine Implementierung
- präzise und konkret
- keine generischen Aussagen
- keine theoretischen Best Practices ohne Kontext
- priorisieren statt aufzählen

---

## Abschluss

Die letzte Zeile MUSS exakt sein:

EXECQUEUE.STATUS.FINISHED