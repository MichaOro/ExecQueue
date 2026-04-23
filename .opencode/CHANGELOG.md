# Changelog - Agent Updates

Alle wesentlichen Änderungen an Agent-Konfigurationen, Prompts und Skills werden hier dokumentiert.

## [2.0.0] - 2026-04-23

### Added
- **Prompt-Dateien**: Alle Agent-Prompts in `.opencode/prompts/` zentralisiert
  - `build.md` - Haupt-Entwicklungs-Agent
  - `plan.md` - Planungs- und Architektur-Agent
  - `code-reviewer.md` - Code Review Subagent
  - `test-engineer.md` - Test Engineering Subagent
  - `db-specialist.md` - Database Specialist Subagent
  - `documentation-writer.md` - Technical Writer Subagent
  - `security-auditor.md` - Security Auditor Subagent

- **Temperature-Konfiguration**: Unterschiedliche Temperaturen pro Agent
  - `0.1`: Plan, code-reviewer, db-specialist, security-auditor (fokussiert)
  - `0.2`: test-engineer (ausgewogen)
  - `0.3`: build, documentation-writer (kreativer)

- **Color-Coding**: Visuelle Unterscheidung im TUI
  - `primary`: build
  - `secondary`: plan
  - `accent`: code-reviewer
  - `success`: test-engineer
  - `info`: db-specialist, documentation-writer
  - `error`: security-auditor

- **Skills-Erweiterungen**: Umfassende Dokumentation und Troubleshooting
  - `test-runner`: Coverage Targets, Test-Ausführung, Bekannte Issues & Fixes
  - `code-review`: Security-Review, Performance-Optimierung, Review-Output-Format
  - `api-generator`: Vollständige Endpoint-Templates, Security Best Practices
  - `db-migration`: Migration-Workflow, Checkliste, Troubleshooting

- **AGENTS.md Updates**:
  - OpenCode Best Practices Section (Tab-Switching, Undo/Redo, Session-Management)
  - Known Gotchas mit Lösungen strukturiert
  - Agent Usage Guidelines erweitert
  - Permission Levels dokumentiert

### Changed
- **opencode.json**: Migration von `tools` zu `permission` (modernes Format)
  ```json
  // Before (deprecated)
  "tools": { "write": false, "edit": false }
  
  // After (modern)
  "permission": { "edit": "deny", "write": "deny" }
  ```

- **Prompt-Referenzierung**: Von inline-Text zu `{file:path}`
  ```json
  // Before
  "prompt": "Folge AGENTS.md für Projekt-Konventionen..."
  
  // After
  "prompt": "{file:.opencode/prompts/build.md}"
  ```

- **Skills**: Alle Skills mit zusätzlichen Best Practices und Troubleshooting erweitert

### Improved
- **Wartbarkeit**: Prompts in separate Dateien extrahiert
- **Lesbarkeit**: AGENTS.md mit klaren Sektionen und Struktur
- **Developer Experience**: Umfassende Troubleshooting-Guides
- **Security**: OWASP Top 10 Checklisten integriert
- **Performance**: N+1 Query Prevention dokumentiert

### Security
- Security-Auditor Prompt mit OWASP Top 10 Checkliste erweitert
- FastAPI-spezifische Security Patterns dokumentiert
- Input Validation Best Practices hinzugefügt

### Documentation
- Prompt-README mit Agent-Übersicht erstellt
- Temperature-Einstellungen dokumentiert
- Workflow-Beispiele für alle Agent-Typen

---

## [1.0.0] - 2026-04-23

### Initial Release
- Basis-Agent-Konfiguration mit 6 Subagenten
- 4 Skills (test-runner, db-migration, code-review, api-generator)
- Versioning-System mit SemVer
- AGENTS.md mit Projekt-Konventionen
