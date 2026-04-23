# Arbeitspaket 1-02: Telegram Bot Core Implementierung

## 1. Titel
Telegram Bot Core Implementierung - Grundgerüst und Basis-Commands

## 2. Ziel
Implementierung des grundlegenden Telegram Bots mit Polling-Modus, Command-Routing, Autorisierung und den Must-Priority Commands (`/start`, `/help`, `/queue`, `/status`, `/health`).

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: Remote-Steuerung von ExecQueue via Telegram
- **Zielgruppe**: Operatoren und Administratoren
- **Business Value**: Ermöglicht schnelle Statusabfragen und Steuerung ohne API-Kenntnisse

## 4. Betroffene Bestandteile

**Neu zu erstellen:**
- `execqueue/workers/telegram_bot.py` - Haupt-Bot-Logik mit Command-Handler

**Zu erweitern:**
- `execqueue/workers/__init__.py` - Export des Bots
- `.env` - Telegram-Konfiguration hinzufügen
- `execqueue/main.py` - Optional: Bot-Start als Background-Task

**Bereits vorhanden (wird konsumiert):**
- `execqueue/api/tasks.py` - GET /api/tasks
- `execqueue/api/requirements.py` - GET /api/requirements
- `execqueue/api/health.py` - GET /api/health

## 5. Konkrete Umsetzungsschritte

### Schritt 1: Environment-Konfiguration erweitern

**Datei: `.env` (oder `.env.example`)**

Folgende Variablen hinzufügen:
```env
# TELEGRAM BOT CONFIGURATION
TELEGRAM_BOT_TOKEN=<token_from_botfather>
TELEGRAM_POLLING_ENABLED=true  # true für Development, false für Production mit Webhook
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook/telegram  # Optional
TELEGRAM_ADMIN_USER_IDS=123456789,987654321  # Comma-separated
TELEGRAM_RATE_LIMIT_PER_MINUTE=30
API_BASE_URL=http://127.0.0.1:8000/api
```

**Anforderungen:**
- `TELEGRAM_BOT_TOKEN` ist REQUIRED (Bot startet nicht ohne)
- `TELEGRAM_POLLING_ENABLED` Default: true (Development-first)
- `TELEGRAM_ADMIN_USER_IDS` kann leer sein (dann nur Datenbank-Admins)

### Schritt 2: Bot-Hauptklasse erstellen

**Datei: `execqueue/workers/telegram_bot.py`**

**Struktur:**
```python
class TelegramBotWorker:
    """Telegram Bot Worker für ExecQueue Remote-Steuerung."""
    
    def __init__(self):
        self.bot = None  # telegram.ext.Application
        self.admin_user_ids: set[int] = set()
        self.rate_limits: dict[str, list[datetime]] = {}
        
    async def start(self):
        """Startet den Bot (Polling oder Webhook)."""
        # Initialisiere Bot mit Token
        # Lade Admin-User-IDs aus Environment
        # Registriere Command-Handler
        # Starte Polling oder Webhook
        
    async def stop(self):
        """Stoppt den Bot graceful."""
        # Beende alle laufenden Tasks
        # Schließe Bot-Verbindung
        
    def check_rate_limit(self, user_id: str) -> bool:
        """Prüft Rate-Limit für Benutzer."""
        # Implementiere滑动窗口-Rate-Limiting
        
    def get_user_role(self, user_id: str, session: Session) -> str:
        """Ermittelt Rolle des Benutzers."""
        # Prüfe zuerst Datenbank (TelegramUser)
        # Fall-back: Admin-Liste aus Environment
        # Default: "observer"
```

**Anforderungen:**
- Async-first Design (python-telegram-bot ist async)
- Graceful Shutdown (stop() muss alle Tasks beenden)
- Rate-Limiting pro Benutzer (verhindert Missbrauch)
- Rollen-basierte Zugriffskontrolle (RBAC)

### Schritt 3: Command-Handler implementieren

**Datei: `execqueue/workers/telegram_bot.py` (im gleichen File)**

**Register-Struktur:**
```python
# Command-Definitionen mit Metadaten
COMMANDS = {
    "start": {
        "handler": handle_start,
        "role": "observer",
        "description": "Bot-Start mit Begrüßung und Hilfe",
    },
    "help": {
        "handler": handle_help,
        "role": "observer",
        "description": "Zeige alle verfügbaren Commands",
    },
    "queue": {
        "handler": handle_queue,
        "role": "observer",
        "description": "Zeige aktuelle Task-Queue (max 10)",
    },
    "status": {
        "handler": handle_status,
        "role": "observer",
        "description": "Detail-Status eines Tasks",
        "requires_arg": True,  # task_id erforderlich
    },
    "health": {
        "handler": handle_health,
        "role": "observer",
        "description": "System-Status anzeigen",
    },
    "create": {
        "handler": handle_create,
        "role": "operator",
        "description": "Neuen Task anlegen",
        "requires_arg": True,
    },
    "cancel": {
        "handler": handle_cancel,
        "role": "operator",
        "description": "Task abbrechen",
        "requires_arg": True,
    },
    "start_scheduler": {
        "handler": handle_start_scheduler,
        "role": "admin",
        "description": "Scheduler aktivieren",
    },
    "stop_scheduler": {
        "handler": handle_stop_scheduler,
        "role": "admin",
        "description": "Scheduler deaktivieren",
    },
}
```

**Anforderungen:**
- Command-Handler sind modular (einfach erweiterbar)
- Role-Check vor Handler-Ausführung
- Argument-Validierung (z.B. task_id Format)
- Fehlerbehandlung mit benutzerfreundlichen Nachrichten

### Schritt 4: Command-Handler Implementierung

**Datei: `execqueue/workers/telegram_bot.py`**

**Implementiere folgende Handler:**

1. **handle_start** - Begrüßung mit `/help` Link
2. **handle_help** - Liste aller Commands mit Beschreibung
3. **handle_queue** - Holt Tasks von API, formatiert als Liste
4. **handle_status** - Holt Task-Detail von API, zeigt Status, retry_count, etc.
5. **handle_health** - Holt Health-Check von API, zeigt DB-Status, Scheduler-Status
6. **handle_create** - Validiert Prompt, erstellt Task via API
7. **handle_cancel** - Cancelt Task via API
8. **handle_start_scheduler** - Startet Scheduler via API
9. **handle_stop_scheduler** - Stoppt Scheduler via API

**Formatierungs-Beispiel:**
```python
def format_task_list(tasks: list[dict]) -> str:
    """Formatiert Task-Liste für Telegram."""
    if not tasks:
        return "❌ Keine Tasks in der Queue."
    
    lines = ["📋 *Aktuelle Task-Queue:*", ""]
    for task in tasks[:10]:  # Max 10
        status_emoji = {"queued": "⏳", "in_progress": "🔄", "done": "✅", "failed": "❌"}.get(task.status, "❓")
        lines.append(f"{status_emoji} `#{task.id}` - {task.title[:30]}")
        lines.append(f"   Status: {task.status}, Priority: {task.execution_order}")
    
    return "\n".join(lines)
```

**Anforderungen:**
- Markdown-Formatierung für bessere Lesbarkeit (Telegram unterstützt MarkdownV2)
- Emojis für Status-Visualisierung
- Truncation bei langen Texten (Telegram Limit: 4096 Zeichen)
- Error-Handling mit klaren Fehlermeldungen

### Schritt 5: API-Kommunikation

**Datei: `execqueue/workers/telegram_bot.py`**

**Helper-Funktion:**
```python
async def call_api(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """Ruft ExecQueue API auf."""
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api")
    url = f"{base_url}/{endpoint}"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if method == "GET":
                response = await client.get(url, params=data)
            elif method == "POST":
                response = await client.post(url, json=data)
            
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            raise BotError("API nicht erreichbar (Timeout)")
        except httpx.HTTPStatusError as e:
            raise BotError(f"API-Fehler: {e.response.status_code}")
```

**Anforderungen:**
- Timeout von 10 Sekunden
- Graceful Degradation bei API-Ausfall (Error-Nachricht an Benutzer)
- HTTP-Exceptions in BotError umwandeln

### Schritt 6: Bot-Start in ExecQueue integrieren

**Datei: `execqueue/main.py`**

**Optionaler Start als Background-Task:**
```python
@app.on_event("startup")
async def on_startup():
    """Create all database tables and start Telegram Bot."""
    SQLModel.metadata.create_all(engine)
    
    # Telegram Bot starten (wenn konfiguriert)
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        from execqueue.workers.telegram_bot import TelegramBotWorker
        bot = TelegramBotWorker()
        asyncio.create_task(bot.start(), name="telegram_bot")
```

**Alternative: Separate CLI für Bot-Start**
```python
# execqueue/__main__.py erweitern
if sys.argv[1] == "telegram":
    from execqueue.workers.telegram_bot import TelegramBotWorker
    asyncio.run(TelegramBotWorker().start())
```

**Anforderungen:**
- Bot startet nur wenn `TELEGRAM_BOT_TOKEN` gesetzt ist
- Graceful Shutdown bei App-Stop
- Fehler-Logging bei Bot-Start-Fehlern

### Schritt 7: Logging konfigurieren

**Datei: `execqueue/workers/telegram_bot.py`**

```python
logger = logging.getLogger(__name__)

# In Handler:
logger.info(f"User {user_id} executed command: {command}")
logger.error(f"Error in {command}: {error}")
```

**Anforderungen:**
- Strukturierte Logs (JSON-Format für Production)
- User-ID loggen (nicht Telegram-Username für Privacy)
- Fehler mit Stacktrace loggen

## 6. Architektur- und Codequalitätsvorgaben

**Clean Code:**
- Async/Await für alle I/O-Operationen
- Type Hints für alle Funktionen
- Docstrings für öffentliche Methoden
- Single Responsibility pro Handler-Funktion

**Minimal Invasivität:**
- Bot-Logik in EINER Datei (nicht aufgeteilt in commands.py, handlers.py, etc.)
- Message-Formattierung lokal in Handler-Funktionen
- Keine präventiven Abstraktionen (z.B. kein Command-Interface)

**Fehlerbehandlung:**
- Try-Catch um API-Calls
- Benutzerfreundliche Fehlermeldungen
- Logging von Errors für Debugging

**Sicherheit:**
- Role-Check VOR Handler-Ausführung
- Input-Validierung (z.B. task_id ist Integer)
- Keine sensiblen Daten in Logs

## 7. Abgrenzung: Was NICHT Teil des Pakets ist

- **Keine Benachrichtigungen** - kommen in Arbeitspaket 1-03
- **Keine Subscription-Commands** (`/subscribe`, `/unsubscribe`) - später
- **Keine Admin-Commands** (`/admin users`, `/admin grant`) - später
- **Keine Inline-Keyboards** - erst in Phase 2
- **Keine Webhook-Unterstützung** - nur Polling (Webhook als TODO)

## 8. Abhängigkeiten

**Vorausgesetzt:**
- Arbeitspaket 1-01 (Datenbank-Modelle) - für User-Validierung
- `httpx` ist installiert (für API-Calls)
- `python-telegram-bot` ist installiert

**Wird benötigt für:**
- Arbeitspaket 1-03 (Benachrichtigungen) - baut auf Bot-Infrastruktur auf
- Arbeitspaket 1-04 (Tests) - testet diese Implementierung

## 9. Akzeptanzkriterien

- [ ] Bot startet mit `TELEGRAM_BOT_TOKEN` in `.env`
- [ ] `/start` zeigt Begrüßung mit `/help` Link
- [ ] `/help` listet alle Commands mit Beschreibung
- [ ] `/queue` zeigt max 10 Tasks mit Status und Emojis
- [ ] `/status <task_id>` zeigt Detail-Status
- [ ] `/health` zeigt System-Status (DB, Scheduler, Queue)
- [ ] `/create <prompt>` erstellt neuen Task
- [ ] `/cancel <task_id>` bricht Task ab
- [ ] `/start_scheduler` und `/stop_scheduler` funktionieren (nur Admin)
- [ ] Rate-Limiting funktioniert (30 Commands/Minute)
- [ ] Role-Check verhindert nicht-autorisierten Zugriff
- [ ] Graceful Degradation bei API-Ausfall (Error-Nachricht)
- [ ] Logs enthalten User-ID und Command

## 10. Risiken / Prüfpunkte

| Risiko | Auswirkung | Minderung |
|--------|------------|-----------|
| python-telegram-bot Version | API-Brüche zwischen v13.x und v20.x | Explizite Version in requirements.txt (>=20.0) |
| API-Base-URL falsch konfiguriert | Bot kann nicht kommunizieren | Default auf localhost, klare Fehlermeldung |
| Telegram API Rate Limit (30/min) | Bot wird blockiert | Eigenes Rate-Limiting unter 30 halten |
| Lange Nachrichten (>4096 Zeichen) | Telegram verwirft Nachricht | Truncation oder Dokument senden |

**Prüfpunkte vor Merge:**
- [ ] Bot lokal getestet (Polling-Modus)
- [ ] Alle Must-Commands funktionieren
- [ ] Role-Check validiert (observer kann nicht admin-Commands ausführen)
- [ ] Rate-Limiting testbar (z.B. via Mock)
- [ ] Logs werden korrekt geschrieben

## 11. Begründung für Struktur

**Warum alles in einer Datei?**
- **Lesbarkeit**: Ein File mit ~400 Zeilen ist übersichtlicher als 5 Files mit je 80 Zeilen
- **Wiederverwendung**: Command-Handler sind bot-spezifisch, werden nirgendwo anders genutzt
- **Wartbarkeit**: Änderungen am Bot betreffen nur eine Datei
- **Pattern-Konsistenz**: `opencode_adapter.py` ist auch eine große, zusammengefasste Datei

**Warum keine separaten Formatter/Helper?**
- **Einmalig**: Message-Formattierung wird nur im Bot verwendet
- **Komplexität**: Extra-Datei für 2-3 Funktionen ist Overengineering
- **Local Context**: Formatierungslogik ist besser verständlich im Handler-Kontext

**Bewusste Entscheidung: Keine Aufteilung in:**
- `telegram_commands.py` (Command-Handler)
- `telegram_formatter.py` (Message-Formattierung)
- `telegram_api_client.py` (API-Kommunikation)

Stattdessen: **Eine Datei** mit klar strukturierten Abschnitten (siehe Umsetzungsschritte).

## 12. Empfohlene Dateinamen

- `execqueue/workers/telegram_bot.py` (alleinige Datei für Bot-Logik)

## 13. Zielpfade

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/workers/telegram_bot.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/.env` (Erweiterung)
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/main.py` (optional: Bot-Start integrieren)

---

**Ende Arbeitspaket 1-02**
