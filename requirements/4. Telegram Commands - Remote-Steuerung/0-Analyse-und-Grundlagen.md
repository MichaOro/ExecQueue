# Analyse und Grundlagen - Telegram Commands

## Analyse der bestehenden Codebasis

### Bestehende Strukturen

**API Layer (`execqueue/api/`):**
- `tasks.py` - Task-Endpoints (GET, POST, PATCH)
- `requirements.py` - Requirement-Endpoints
- `work_packages.py` - WorkPackage-Endpoints
- `queue.py` - Queue-Management
- `health.py` - Health-Check Endpoint
- `metrics.py` - Metriken-Endpoints
- `dead_letter.py` - Dead-Letter-Queue

**Services Layer (`execqueue/services/`):**
- `queue_service.py` - Queue-Verarbeitungslogik
- `status_sync_service.py` - Status-Synchronisation
- `opencode_session_service.py` - OpenCode-Session-Management

**Models Layer (`execqueue/models/`):**
- `task.py` - Task-Entität
- `requirement.py` - Requirement-Entität (mit Queue-Steuerung)
- `work_package.py` - WorkPackage-Entität
- `dead_letter.py` - Dead-Letter-Queue-Entität

**Workers Layer (`execqueue/workers/`):**
- `opencode_adapter.py` - OpenCode-Integration

**Scheduler (`execqueue/scheduler/`):**
- `runner.py` - Task-Ausführungsloop

### Wiederverwendungspotenziale

1. **Bestehende API-Endpoints**: Der Telegram-Bot kann alle benötigten Daten über existierende Endpoints beziehen:
   - `GET /api/tasks` - Task-Liste
   - `GET /api/tasks/{id}` - Task-Detail
   - `GET /api/requirements` - Requirements
   - `GET /api/health` - System-Health
   - `POST /api/queue/start` - Scheduler starten
   - `POST /api/queue/stop` - Scheduler stoppen

2. **Session-Management**: `execqueue.db.session.get_session()` kann für Datenbankzugriffe im Bot wiederverwendet werden

3. **Validierungslogik**: `execqueue/validation/` enthält bereits Validierungsfunktionen

4. **Environment-Konfiguration**: `.env`-Struktur ist etabliert, nur `TELEGRAM_BOT_TOKEN` etc. hinzufügen

### Fachliche Domänen

**Telegram-Bot gehört zu:**
- **Primär**: `execqueue/workers/` (als externer Adapter, analog zu `opencode_adapter.py`)
- **Sekundär**: `execqueue/services/` (für bot-spezifische Geschäftslogik)

**Datenmodell-Erweiterungen:**
- Neue Tabelle `telegram_user` für Benutzerverwaltung
- Neue Tabelle `telegram_notification` für Benachrichtigungen
- Beide gehören in `execqueue/models/`

### Bestehende Patterns

**Bot-Implementierung folgt Pattern:**
```
execqueue/workers/telegram_bot.py       # Haupt-Bot-Logik (Polling/Webhook)
execqueue/workers/telegram_commands.py  # Command-Handler (erweitert)
execqueue/services/telegram_service.py  # Geschäftslogik (Benutzerverwaltung, Notifications)
execqueue/api/telegram.py               # Telegram Webhook Endpoint (optional)
execqueue/models/telegram_user.py       # User-Entität
execqueue/models/telegram_notification.py # Notification-Entität
```

### Bewusste Entscheidungen zur Struktur

**NICHT aufgeteilt werden:**
- **Keine separaten Helper-Dateien** für Message-Formattierung - bleibt im Bot-Code lokal
- **Keine View/Renderer-Klassen** - einfache String-Formatierung genügt
- **Keine separate Command-Routing-Bibliothek** - einfaches Dict-basiertes Routing

**Warum diese Aufteilung:**
1. Telegram-Bot ist ein **einheitlicher Worker** (wie opencode_adapter)
2. Command-Logik ist **nicht komplex genug** für eigene Module
3. Message-Formattierung ist **bot-spezifisch** und wird nicht wiederverwendet
4. Einfache Struktur = **bessere Wartbarkeit**

---

## Technische Voraussetzungen

### Zu installierende Dependencies
```
python-telegram-bot>=20.0  # Async Bot-Framework
```

### Zu konfigurierende Environment Variables
```
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_WEBHOOK_URL=<url>  # Optional für Production
TELEGRAM_POLLING_ENABLED=true  # Default für Development
TELEGRAM_ADMIN_USER_IDS=<comma-separated-ids>
TELEGRAM_RATE_LIMIT_PER_MINUTE=30
API_BASE_URL=http://127.0.0.1:8000/api
```

### Datenbank-Migration erforderlich
- Neue Tabellen: `telegram_user`, `telegram_notification`
- Siehe Arbeitspaket "Datenbank-Modell erweitern"

---

## Risikoanalyse

| Risiko | Auswirkung | Minderung |
|--------|------------|-----------|
| Telegram API Rate Limits | Bot-Commands können blockiert werden | Implementiere Rate-Limiting pro Benutzer |
| Bot-Token Kompromittierung | Unbefugter Zugriff | Token in `.env`, nie im Code |
| Datenbank-Verbindungsfehler | Bot kann nicht auf Daten zugreifen | Graceful Degradation mit Error-Nachrichten |
| Lange Nachrichten | Telegram API Limit (4096 Zeichen) | Nachrichten truncieren oder als Dokument senden |

---

## Offene Fragen (vor Implementierung klären)

1. **Webhook vs. Polling**: 
   - Polling: Einfach für Development, kein externes Hosting nötig
   - Webhook: Production-relevant, erfordert öffentlich zugängliche URL
   
   **Empfehlung**: Mit Polling starten, Webhook als Option vorbereiten

2. **Benachrichtigungs-Strategie**:
   - Sollen alle Benutzer automatisch benachrichtigt werden?
   - Oder nur auf Opt-in (`/subscribe`)?
   
   **Empfehlung**: Opt-in Modell (`/subscribe`) für Privacy

3. **Admin-Berechtigung**:
   - Statisch über `ADMIN_USER_IDS` in `.env`?
   - Oder dynamisch über Datenbank?
   
   **Empfehlung**: Hybrid - Start-Admins in `.env`, erweiterbar via `/admin grant`

---

## Akzeptanzkriterien (Gesamt)

- [ ] Bot startet und antwortet auf `/start` und `/help`
- [ ] Alle Must-Priority Commands funktionieren (`/queue`, `/status`, `/create`, `/cancel`, `/health`)
- [ ] Autorisierung funktioniert (observer, operator, admin Rollen)
- [ ] Rate-Limiting verhindert Missbrauch
- [ ] Graceful Degradation bei API-Ausfall
- [ ] Benachrichtigungen werden korrekt gesendet
- [ ] Alle Tests bestehen (Unit + Integration)

---

**Dieses Dokument dient als Referenz für alle folgenden Arbeitspakete.**
