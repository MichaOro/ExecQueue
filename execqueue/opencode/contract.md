# OpenCode Serve API Contract (REQ-012 Paket 03)

## Verifizierte API Endpunkte

Dieses Dokument dokumentiert die tatsächlich verfügbaren Endpunkte von `opencode serve` (Version 1.14.29) als Grundlage für die REQ-012 Runner-Implementierung.

**Server:** `http://127.0.0.1:4096`
**Version:** 1.14.29

---

## 1. Global Endpoints

### GET /global/health

**Response:**
```json
{
  "healthy": true,
  "version": "1.14.29"
}
```

**Status:** ✅ Verifiziert

---

## 2. Session Endpoints

### GET /session

**Beschreibung:** Liste alle Sessions auf

**Response:** Array von Session-Objekten
```json
[
  {
    "id": "ses_22a1c0e74ffeSru7r1WZ5tB65T",
    "slug": "eager-mountain",
    "projectID": "aaa18d56a422085adbe61b28da11fb52780897f2",
    "directory": "/home/ubuntu/workspace/IdeaProjects/ExecQueue",
    "path": "",
    "title": "New session - 2026-04-28T20:59:38.763Z",
    "version": "1.14.29",
    "summary": {
      "additions": 358,
      "deletions": 146,
      "files": 7
    },
    "time": {
      "created": 1777409978763,
      "updated": 1777410615182
    }
  }
]
```

**Status:** ✅ Verifiziert

### GET /session/:id

**Beschreibung:** Hole Session-Details

**Response:** Session-Objekt (siehe oben)

**Status:** ⚠️ Nicht getestet (benötigt Session-ID)

### POST /session

**Beschreibung:** Erstelle neue Session

**Body:**
```json
{
  "parentID": "<optional>",
  "title": "<optional>"
}
```

**Status:** ⚠️ Nicht getestet (theoretisch basierend auf Dokumentation)

---

## 3. Agent Endpoints

### GET /agent

**Beschreibung:** Liste alle verfügbaren Agents auf

**Response:** Array von Agent-Objekten
```json
[
  {
    "name": "build",
    "description": "Primary delivery agent for ExecQueue...",
    "mode": "primary",
    "model": {
      "providerID": "adesso",
      "modelID": "qwen-3.5-122b-sovereign"
    },
    "temperature": 0.2,
    "native": true,
    "permission": [...]
  },
  {
    "name": "explore",
    "description": "Fast agent specialized for exploring codebases...",
    "mode": "subagent",
    "native": true,
    "temperature": 0
  },
  ...
]
```

**Verfügbare Agents:**
- `build` - Primary delivery agent (mode: primary)
- `plan` - Planning agent (mode: primary)
- `review` - Review subagent (mode: subagent)
- `explore` - Codebase exploration (mode: subagent)
- `general` - General-purpose agent (mode: subagent)
- `db-inspector` - Database inspection (mode: subagent)
- `db-writer` - Database writes (mode: subagent)
- `compaction` - Context summarization (mode: primary, hidden)
- `summary` - Conversation summary (mode: primary, hidden)
- `title` - Title generation (mode: primary, hidden)

**Status:** ✅ Verifiziert

---

## 4. Project Endpoints

### GET /project/current

**Beschreibung:** Hole aktuelles Projekt

**Response:**
```json
{
  "id": "aaa18d56a422085adbe61b28da11fb52780897f2",
  "worktree": "/home/ubuntu/workspace/IdeaProjects/ExecQueue",
  "vcs": "git",
  "icon": {
    "color": "purple"
  },
  "time": {
    "created": 1777203612572,
    "updated": 1777410090922
  },
  "sandboxes": [
    "/home/ubuntu/worktrees/opencode-test"
  ]
}
```

**Status:** ✅ Verifiziert

---

## 5. SSE Event Stream

### GET /event

**Beschreibung:** Server-Sent Events Stream

**Status:** ⚠️ Nicht getestet (benötigt SSE-Client-Implementierung)

**Erwartetes Verhalten** (basierend auf Dokumentation):
- First event: `server.connected`
- Subsequent events: Bus events (message updates, session updates, etc.)
- Heartbeat events möglich

---

## 6. Message Endpoints (Nicht Getestet)

### POST /session/:id/message

**Beschreibung:** Sende Nachricht an Session und warte auf Antwort

**Body (erwartet):**
```json
{
  "parts": [{"type": "text", "text": "<message>"}],
  "agent": "<agent-name>",
  "model": "<optional>"
}
```

**Response (erwartet):**
```json
{
  "info": {
    "id": "<message-id>",
    "role": "user",
    "sessionID": "<session-id>",
    ...
  },
  "parts": [...]
}
```

**Status:** ❌ Nicht getestet

### GET /session/:id/message

**Beschreibung:** Liste Nachrichten in Session

**Status:** ❌ Nicht getestet

---

## 7. File Endpoints (Nicht Getestet)

### GET /file/content?path=<path>

**Beschreibung:** Lese Datei-Inhalt

**Status:** ❌ Nicht getestet

### GET /find/file?query=<query>

**Beschreibung:** Finde Dateien nach Name

**Status:** ❌ Nicht getestet

---

## Implementierungsentscheidungen für REQ-012

### 1. Session Management

**Entscheidung:** Sessions werden reaktiv erstellt - der Runner erstellt eine neue Session pro Task-Execution.

**Begründung:**
- Jede Execution hat eigene Traceability
- `correlation_id` wird in TaskExecution gespeichert
- Keine Wiederverwendung von Sessions zwischen Executions

### 2. Agent Auswahl

**Entscheidung:** Verwende `build` Agent für alle Task-Executions.

**Begründung:**
- `build` ist der Primary delivery agent
- Hat vollständige Schreibrechte
- Konfiguriert mit `qwen-3.5-122b-sovereign` Modell

### 3. SSE Event Stream

**Entscheidung:** SSE-Stream wird nach Session-Erstellung abonniert und bis zum Abschluss der Execution gehört.

**Begründung:**
- Ermöglicht Echtzeit-Tracking von Execution-Fortschritt
- Heartbeats können für Liveness-Checks verwendet werden
- Events werden chronologisch in TaskExecutionEvent gespeichert

### 4. Prompt Dispatch

**Entscheidung:** Prompt wird via `POST /session/:id/message` gesendet.

**Begründung:**
- Blocking Response ermöglicht sofortiges Erfassen von message_id/run_id
- Alternative `prompt_async` wäre asynchron und komplexer zu handhaben

---

## Implementierungsrisko

### Hoch

1. **SSE Endpunkt unklar:**
   - `/event` ist global, nicht session-spezifisch
   - Event-Filterung muss über Session-ID im Payload erfolgen
   - Event-Taxonomie muss noch vollständig dokumentiert werden

2. **Message Dispatch Antwortformat:**
   - Antwortstruktur muss noch mit Live-System verifiziert werden
   - Timeout-Verhalten unklar

3. **Session Lifecycle:**
   - Wann wird eine Session automatisch geschlossen?
   - Muss Session explizit geschlossen werden (`DELETE /session/:id`)?

### Mittel

1. **Error Handling:**
   - HTTP Error Codes müssen noch kategorisiert werden
   - Timeout-Verhalten bei langen Executions

2. **Authentication:**
   - Aktuell kein Auth erforderlich (localhost)
   - Für Production müsste `OPENCODE_SERVER_PASSWORD` beachtet werden

---

## Nächste Schritte (Paket 04)

1. Implementiere `OpenCodeClient` Klasse mit:
   - `create_session()` → session_id
   - `send_message(session_id, prompt, agent="build")` → message_id
   - `get_session(session_id)` → session status
   - `connect_sse(session_id)` → SSE stream

2. Füge Timeout-Konfiguration hinzu:
   - Request timeout: 30s
   - Stream timeout: 3600s (1 hour)

3. Mape HTTP Errors zu technischen Kategorien:
   - Connection errors
   - HTTP errors (4xx, 5xx)
   - Timeouts
   - Invalid responses

---

## Dokumentation Quellen

- OpenCode Server Docs: https://opencode.ai/docs/server/
- Verifiziert mit: `opencode serve --port 4096 --hostname 127.0.0.1`
- Version: 1.14.29
- Test Datum: 2026-04-28
