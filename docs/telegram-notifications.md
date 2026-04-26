# Telegram Notifications im Testcluster

Diese Dokumentation beschreibt alle automatischen Benachrichtigungen, die der ExecQueue Telegram Bot sendet.

## Notification-Übersicht

| Notification | Was macht er? | Erfolgskriterium |
|--------------|---------------|------------------|
| **Bot Online** | Sendet eine Benachrichtigung beim erfolgreichen Start des Bots | Bot sendet eine Nachricht mit grünem Indikator (🟢) und dem Text "Bot Online" inkl. Startzeitpunkt an die konfigurierte User ID |
| **Bot Shutdown** | Sendet eine Benachrichtigung beim Herunterfahren des Bots | Bot schreibt Status "not_ok" in die Health-Datei mit Detail "Telegram bot is shutting down" (keine direkte Telegram-Nachricht, aber Status-Update) |
| **Bot Stopped** | Sendet eine Benachrichtigung wenn der Bot gestoppt wird | Bot schreibt Status "not_ok" in die Health-Datei mit Detail "Telegram bot stopped." (keine direkte Telegram-Nachricht, aber Status-Update) |
| **Bot Error** | Sendet eine Benachrichtigung bei Fehlern | Bot schreibt Status "not_ok" in die Health-Datei mit Fehlerdetails (keine direkte Telegram-Nachricht, aber Status-Update) |
| **Health Status Update** | Periodische Health-Updates durch den Health Reporter | Bot schreibt alle `telegram_polling_timeout` Sekunden (Standard: 30s) Status "ok" mit Detail "Telegram bot is running and polling for updates" in die Health-Datei |

## Technische Details

### Bot Online Notification

Die "Bot Online" Notification wird automatisch beim erfolgreichen Start gesendet, sofern `telegram_notification_user_id` konfiguriert ist.

**Nachrichtenformat:**
```markdown
🟢 *Bot Online*

Der ExecQueue Bot ist jetzt online und steht zur Verfügung.
Startzeit: YYYY-MM-DD HH:MM:SS UTC
```

**Bedingungen:**
- Bot muss erfolgreich initialisiert und gestartet sein
- `TELEGRAM_NOTIFICATION_USER_ID` muss in der `.env` konfiguriert sein
- Die Benachrichtigung ist optional - wenn sie fehlschlägt, startet der Bot trotzdem weiter

### Health Status Reporter

Der Bot führt einen Health Reporter aus, der regelmäßig den Status in eine Datei schreibt:

**Dateipfad:** `ops/health/telegram_bot.json`

**Beispielinhalt:**
```json
{
  "component": "telegram_bot",
  "status": "ok",
  "detail": "Telegram bot is running and polling for updates.",
  "last_check": "2026-04-26T14:41:36.123456+00:00",
  "pid": 589656
}
```

**Update-Intervall:** Alle `telegram_polling_timeout` Sekunden (Standard: 30 Sekunden)

**Status-Werte:**
- `"ok"` - Bot läuft normal
- `"starting"` - Bot initialisiert
- `"not_ok"` - Bot gestoppt oder Fehler

### Fehlerbehandlung bei Notifications

- Wenn die Benachrichtigung beim Start fehlschlägt (z.B. Chat nicht gefunden), wird ein Warning im Log protokolliert
- Der Bot-Start wird **nicht** durch eine fehlgeschlagene Benachrichtigung blockiert
- Fehler werden im Log sichtbar: `Failed to send notification to user {user_id}: {error}`

## Konfiguration

### Benötigte Umgebungsvariablen

In der `.env` Datei konfigurieren:

```bash
# Telegram Bot aktivieren
TELEGRAM_BOT_ENABLED=true

# Bot Token (vom BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# User ID für Benachrichtigungen (deine eigene Telegram User ID)
TELEGRAM_NOTIFICATION_USER_ID=123456789

# Polling Intervall in Sekunden (optional, Standard: 30)
TELEGRAM_POLLING_TIMEOUT=30
```

### User ID ermitteln

Um deine Telegram User ID herauszufinden:
1. Schreibe eine Nachricht an den Bot
2. Verwende den `/health` Command
3. Oder rufe die Telegram API auf: `https://api.telegram.org/bot<TOKEN>/getUpdates`

Die User ID findest du im `from.id` Feld der Antwort.

## Notification-API

### `send_notification_to_user(user_id, message)`

Sendet eine Notification an einen spezifischen User.

**Parameter:**
- `user_id` (str): Telegram User ID
- `message` (str): Nachricht im Markdown-Format

**Rückgabe:** `bool` - `True` bei Erfolg, `False` bei Fehler

**Beispiel:**
```python
await send_notification_to_user("123456789", "🟢 *Bot Online*\n\nBot ist gestartet.")
```

### `send_notification_to_channel(message)`

Wrapper-Funktion, die eine Notification an den konfigurierten Notification-User sendet.

**Parameter:**
- `message` (str): Nachricht im Markdown-Format

**Rückgabe:** `bool` - `True` bei Erfolg, `False` wenn kein User konfiguriert

**Beispiel:**
```python
await send_notification_to_channel("🔄 System Neustart durchgeführt")
```

## Markdown-Formatierung

Alle Notifications verwenden das Markdown-Format von Telegram:

- `*Text*` für **Fett**
- `_Text_` für *Kursiv*
- `` `Text` `` für `Monospace`
- Emojis werden unterstützt

**Beispiel:**
```python
message = (
    "🟢 *Bot Online*\n\n"
    "Der ExecQueue Bot ist jetzt _online_ und steht zur **Verfügung**.\n"
    f"Startzeit: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
)
```

## Health File Monitoring

Das Health File wird vom API gelesen, um den Bot-Status an Clients anzuzeigen:

### Health Check Endpoint
Das API liest `ops/health/telegram_bot.json` und zeigt:
- Status (ok/degraded/error)
- Detail-Informationen
- Letzte Check-Zeit

### Stale Detection
Wenn das Health File älter als 60 Sekunden ist, wird der Bot als "ERROR" markiert mit der Meldung:
```
Bot health status is stale ({age}s old). Bot may have crashed.
```

## Beispiel-Szenarien

### Szenario 1: Bot startet erfolgreich
```
1. Bot wird gestartet
2. Health Status: "starting" → "ok"
3. "Bot Online" Notification wird gesendet
4. Health Reporter aktualisiert alle 30s den Status
```

### Szenario 2: Bot startet ohne Notification-User
```
1. Bot wird gestartet
2. Health Status: "starting" → "ok"
3. Keine Notification (User ID nicht konfiguriert)
4. Bot läuft trotzdem normal
```

### Szenario 3: Bot startet mit Fehler bei Notification
```
1. Bot wird gestartet
2. Health Status: "starting" → "ok"
3. Notification schlägt fehl (z.B. "Chat not found")
4. Warning im Log: "Failed to send notification to user"
5. Bot läuft trotzdem normal weiter
```

### Szenario 4: Bot wird gestoppt
```
1. SIGINT/SIGTERM Signal empfangen
2. Health Status: "ok" → "not_ok"
3. Detail: "Telegram bot is shutting down"
4. Bot wird sauber gestoppt
5. Health Status: "not_ok" mit Detail "Telegram bot stopped."
```

## Troubleshooting

### Notification wird nicht gesendet
- Prüfen: `TELEGRAM_NOTIFICATION_USER_ID` ist in `.env` gesetzt
- Prüfen: User ID ist korrekt (numerische ID, nicht Username)
- Prüfen: Bot hat Schreibrechte im Chat (bei Gruppen/Channels)
- Log prüfen: `ops/logs/telegram_bot.log`

### Health File wird nicht geschrieben
- Prüfen: Schreibrechte für `ops/health/` Verzeichnis
- Prüfen: Bot-Prozess läuft und hat PID in `ops/pids/telegram_bot.pid`
- Log prüfen: `ops/logs/telegram_bot.log`

### Bot Status ist "stale"
- Bot-Prozess könnte abgestürzt sein
- PID Datei prüfen: `cat ops/pids/telegram_bot.pid`
- Prozess prüfen: `ps aux | grep telegram`
- Bot neu starten: `./ops/scripts/telegram_restart.sh`

## Best Practices

1. **Notification-User konfigurieren**: Immer eine User ID setzen, um Bot-Status zu verfolgen
2. **Logs überwachen**: Regelmäßig `ops/logs/telegram_bot.log` prüfen
3. **Health File monitoren**: API nutzt diese Datei für Health Checks
4. **Fehler ignorieren**: Notification-Fehler blockieren den Bot nicht - das ist beabsichtigt
5. **Stale Detection**: 60s Threshold ist angemessen für 30s Polling-Intervall

## Testing

### Manuelles Testen
```bash
# 1. Bot neu starten
./ops/scripts/telegram_restart.sh

# 2. Notification prüfen (in deinem Telegram)
# Du solltest "Bot Online" erhalten

# 3. Health Status prüfen
cat ops/health/telegram_bot.json

# 4. Logs prüfen
tail -f ops/logs/telegram_bot.log
```

### Automatisiertes Testen
Tests finden sich in:
- `tests/test_telegram_notification_channel.py`
- `tests/test_telegram_bot_startup.py`

Ausführung:
```bash
pytest tests/test_telegram_notification_channel.py -v
pytest tests/test_telegram_bot_startup.py -v
```

## Zusammenfassung

Telegram Notifications im ExecQueue Testcluster umfassen:
- **Automatische "Bot Online" Notification** beim Start
- **Periodische Health Updates** via Health File
- **Graceful Shutdown** mit Status-Updates
- **Fehlertoleranz** - Notification-Fehler blockieren nicht
- **Markdown-Formatierung** für ansprechende Nachrichten
- **Health File Monitoring** durch das API

Die Notification-Infrastruktur ist robust und fehlertolerant konzipiert, um zuverlässige Status-Updates zu gewährleisten, ohne den Bot-Betrieb zu gefährden.
