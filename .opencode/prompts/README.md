# OpenCode Agent Prompts - ExecQueue

Diese Verzeichnis enthält die System-Prompts für alle konfigurierten Agenten und Subagenten.

## Struktur

```
.opencode/prompts/
├── build.md              # Haupt-Entwicklungs-Agent
├── plan.md               # Planungs- und Architektur-Agent
├── code-reviewer.md      # Code Review Subagent
├── test-engineer.md      # Test Engineering Subagent
├── db-specialist.md      # Database Specialist Subagent
├── documentation-writer.md # Technical Writer Subagent
└── security-auditor.md   # Security Auditor Subagent
```

## Verwendung

Die Prompts werden in `opencode.json` via `{file:path}` Referenzierung geladen:

```json
{
  "agent": {
    "build": {
      "prompt": "{file:.opencode/prompts/build.md}"
    }
  }
}
```

## Agent-Übersicht

### Primary Agents

| Agent | Prompt File | Temperature | Color | Purpose |
|-------|-------------|-------------|-------|---------|
| build | build.md | 0.3 | primary | Code-Entwicklung |
| plan | plan.md | 0.1 | secondary | Architektur/Planung |

### Subagents

| Subagent | Prompt File | Temperature | Color | Purpose |
|----------|-------------|-------------|-------|---------|
| code-reviewer | code-reviewer.md | 0.1 | accent | Code Reviews |
| test-engineer | test-engineer.md | 0.2 | success | Test-Erstellung |
| db-specialist | db-specialist.md | 0.1 | info | Datenbank-Design |
| documentation-writer | documentation-writer.md | 0.3 | info | Dokumentation |
| security-auditor | security-auditor.md | 0.1 | error | Security Reviews |

## Temperature-Einstellungen

- **0.1**: Sehr fokussiert, deterministisch (Plan, Review, Security, DB)
- **0.2**: Ausgewogen (Test)
- **0.3**: Etwas kreativer (Build, Documentation)

## Permissions

Jeder Agent hat spezifische Permission-Konfigurationen:

- **build**: Alle Tools erlaubt
- **plan**: Read-only (edit/write/bash: deny)
- **subagents**: Je nach Rolle eingeschränkt

## Wartung

Bei Änderungen an Agent-Rollen oder -Verantwortlichkeiten:
1. Prompt-Datei aktualisieren
2. `opencode.json` Permissions prüfen
3. AGENTS.md bei Bedarf aktualisieren
4. Tests ausführen

## Best Practices

1. **Klare Verantwortung**: Jeder Agent hat eindeutige Aufgaben
2. **Granulare Permissions**: Minimal notwendige Rechte
3. **Temperatur-Optimierung**: Je nach Aufgabe anpassen
4. **Dokumentation**: Alle Änderungen im Changelog erfassen
