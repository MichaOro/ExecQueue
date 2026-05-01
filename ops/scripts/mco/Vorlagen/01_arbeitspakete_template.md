## Aufgabe

Erstelle umsetzbare Arbeitspakete basierend auf einem Anforderungsartefakt.

@INPUT_PATH

---

## Kontext

- Ordner → rekursiv analysieren (Requirements, Code, Tests)
- Datei → Datei + relevanten Codekontext analysieren

---

## Ziel

Erzeuge Arbeitspakete, die:

- direkt umsetzbar sind
- technisch fundiert sind
- im Kontext der bestehenden Codebase stehen
- validierbar sind

Die Pakete dienen als **direkte Grundlage für eine Implementierung**.

---

## Output

Erzeuge:

`WORK_PACKAGES.md`

- im Zielordner oder neben der Datei

---

## Leitprinzipien

- minimale Invasivität
- Erweiterung > Neuentwicklung
- Wartbarkeit > kurzfristige Lösung
- Kontext schlägt Theorie
- keine unnötige Komplexität

---

## Vorgehen

1. Anforderungen analysieren
2. Codebase-Kontext einbeziehen
3. betroffene Bereiche identifizieren
4. Umsetzungsschritte ableiten
5. in umsetzbare Pakete schneiden

---

## Anforderungen an Arbeitspakete

Jedes Arbeitspaket muss:

- ein klares Ziel haben
- konkret umsetzbar sein
- relevante Bereiche benennen
- überprüfbar sein

Typische Inhalte:

- Ziel
- betroffene Module/Dateien
- Umsetzungsschritte
- Abhängigkeiten
- Validierung

---

## Wichtige Regeln

- keine starre Spezifikation
- keine unnötigen Abstraktionen
- Fokus auf reale Umsetzung
- Anpassungen während Umsetzung erlaubt

---

## Iteration

Wenn der Umfang groß ist:

- iterativ arbeiten
- fortsetzen bis vollständig

---

## Ergebnis

WORK_PACKAGES.md mit:

- klaren, umsetzbaren Arbeitspaketen
- nachvollziehbarer Struktur