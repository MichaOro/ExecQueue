# Arbeitspaket 1-03: Benachrichtigungen und Subscription-Management

## 1. Titel
Benachrichtigungen und Subscription-Management für Telegram-Bot

## 2. Ziel
Implementierung von automatischen Benachrichtigungen bei Task-Events und Subscription-Management (`/subscribe`, `/unsubscribe`) für Benutzer.

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: Event-basierte Benachrichtigungen
- **Zielgruppe**: Alle Bot-Benutzer (mit Subscription)
- **Business Value**: Proaktive Information über Task-Abschlüsse und Fehler ohne manuelle Abfrage

## 4. Betroffene Bestandteile

**Neu zu erstellen:**
- `execqueue/workers/telegram_notification_service.py` - Notification-Sendelogik
- `execqueue/workers/telegram_bot.py` - Erweiterung um Subscription-Commands

**Zu erweitern:**
- `execqueue/workers/telegram_bot.py` - Add `/subscribe`, `/unsubscribe` Commands
- `execqueue/scheduler/runner.py` - Notification-Trigger nach Task-Abschluss
- `execqueue/api/queue.py` - Optional: Notification-Trigger bei Queue-Events

**Bereits vorhanden:**
- `execqueue/models/telegram_user.py` (aus AP 1-01)
- `execqueue/models/telegram_notification.py` (aus AP 1-01)

## 5. Konkrete Umsetzungsschritte

### Schritt 1: Subscription-Commands implementieren

**Datei: `execqueue/workers/telegram_bot.py` (erweitern)**

**Handler: handle_subscribe**
```python
async def handle_subscribe(update: Update, context: ContextTypes.DEFAULTType):
    """Benutzer abonniert Event-Typen."""
    # Parse Event-Typ aus Command
    # Validiere Event-Typ (task_completed, validation_failed, retry_exhausted)
    # Aktualisiere subscribed_events in TelegramUser
    # Bestätige Subscription
```

**Handler: handle_unsubscribe**
```python
async def handle_unsubscribe(update: Update, context: ContextTypes.DEFAULTType):
    """Benutzer entfernt Subscription."""
    # Parse Event-Typ aus Command
    # Entferne aus subscribed_events
    # Bestätige Unsubscription
```

**Command-Definitionen:**
```python
"subscribe": {
    "handler": handle_subscribe,
    "role": "observer",
    "description": "Event abonnieren: /subscribe task_completed",
    "requires_arg": True,
},
"unsubscribe": {
    "handler": handle_unsubscribe,
    "role": "observer",
    "description": "Event abbestellen: /unsubscribe task_completed",
    "requires_arg": True,
},
```

**Verfügbare Event-Typen:**
- `task_completed` - Task wurde erfolgreich abgeschlossen
- `validation_failed` - Validierung fehlgeschlagen
- `retry_exhausted` - Retry-Limit erreicht
- `scheduler_started` - Scheduler wurde gestartet
- `scheduler_stopped` - Scheduler wurde gestoppt

**Anforderungen:**
- Multiple Subscriptions pro Benutzer möglich (JSON-Array)
- Fehler bei unbekanntem Event-Typ mit Hilfenachricht
- Bestätigung nach Subscribe/Unsubscribe

### Schritt 2: Notification-Sendelogik implementieren

**Datei: `execqueue/workers/telegram_notification_service.py`**

**Struktur:**
```python
class TelegramNotificationService:
    """Service für Versendung von Telegram-Benachrichtigungen."""
    
    def __init__(self, bot: telegram.Bot):
        self.bot = bot
        
    async def send_notification(
        self,
        user_telegram_id: str,
        event_type: str,
        message: str,
        task_id: Optional[int] = None
    ):
        """Sendet Benachrichtigung an Benutzer."""
        # Prüfe ob Benutzer Event abonniert hat
        # Wenn ja: Telegram API aufrufen
        # Wenn nein: Notification in DB speichern für manuelle Prüfung
        
    async def notify_task_completed(self, task: Task):
        """Benachrichtigt alle Abonnenten über Task-Abschluss."""
        # Format: "Task #{task.id} abgeschlossen"
        # summary: task.validation_summary
        # evidence: task.validation_evidence
        
    async def notify_validation_failed(self, task: Task):
        """Benachrichtigt über Validierungsfehler."""
        # Format: "Task #{task.id} - Validierung fehlgeschlagen"
        # reason: validation_error_message
        
    async def notify_retry_exhausted(self, task: Task):
        """Benachrichtigt über erschöpftes Retry-Limit."""
        # Format: "Task #{task.id} - Retry-Limit erreicht"
        # action: "Manuelle Intervention erforderlich"
        
    async def notify_scheduler_started(self):
        """Benachrichtigt Admins über Scheduler-Start."""
        # Format: "Scheduler gestartet"
        
    async def notify_scheduler_stopped(self):
        """Benachrichtigt Admins über Scheduler-Stop."""
        # Format: "Scheduler gestoppt"
```

**Anforderungen:**
- Service ist unabhängig vom Bot (Dependency Injection)
- Error-Handling bei Telegram-API-Fehlern
- Logging aller Versende-Versuche
- Graceful Degradation (wenn Telegram nicht erreichbar, in DB speichern)

### Schritt 3: Notification-Trigger im Scheduler integrieren

**Datei: `execqueue/scheduler/runner.py` (erweitern)**

**Änderung nach Task-Abschluss:**
```python
async def run_next_task(session: Session) -> Optional[Task]:
    """Läuft nächsten Task und sendet Notification bei Abschluss."""
    task = await _get_next_task(session)
    if not task:
        return None
    
    # Task ausfuehren
    result = await _execute_task(task)
    
    # Ergebnis speichern
    task.status = result.status
    task.validation_summary = result.summary
    task.validation_evidence = result.evidence
    session.add(task)
    await session.commit()
    
    # Notification senden (wenn konfiguriert)
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        from execqueue.workers.telegram_notification_service import TelegramNotificationService
        from telegram import Bot
        
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        bot = Bot(token=bot_token)
        service = TelegramNotificationService(bot)
        
        if result.status == "done":
            await service.notify_task_completed(task)
        elif result.status == "failed":
            await service.notify_validation_failed(task)
        elif task.retry_count >= task.max_retries:
            await service.notify_retry_exhausted(task)
    
    return task
```

**Anforderungen:**
- Notification ist OPTIONAL (nur wenn `TELEGRAM_BOT_TOKEN` gesetzt)
- Notification soll Task-Ausfuehrung NICHT blockieren (async fire-and-forget)
- Fehler in Notification sollen Task-Ergebnis NICHT beeinflussen

### Schritt 4: Admin-Notification-Logik

**Datei: `execqueue/workers/telegram_notification_service.py` (erweitern)**

**Helper: get_admin_user_ids()**
```python
def get_admin_user_ids() -> set[str]:
    """Ermittelt alle Admin-User-IDs (DB + Environment)."""
    # Lade Admin-IDs aus TELEGRAM_ADMIN_USER_IDS
    # Lade Admins aus Datenbank (role="admin")
    # Return union beider Sets
```

**Notification fuer Admins-only:**
```python
async def _notify_admins(self, event_type: str, message: str):
    """Sendet Notification nur an Admin-Benutzer."""
    admin_ids = get_admin_user_ids()
    for admin_id in admin_ids:
        await self.send_notification(admin_id, event_type, message)
```

**Anforderungen:**
- Admin-Notificationen umgehen Subscription-Check
- Admins erhalten immer kritische Events (scheduler_start/stop, retry_exhausted)

### Schritt 5: Notification-Queue (Fallback bei API-Ausfall)

**Datei: `execqueue/workers/telegram_notification_service.py` (erweitern)**

**Persistente Queue:**
```python
async def _save_notification(
    self,
    user_telegram_id: str,
    event_type: str,
    message: str,
    task_id: Optional[int] = None
):
    """Speichert Notification in DB fuer spaeteren Versende-Versuch."""
    notification = TelegramNotification(
        user_telegram_id=user_telegram_id,
        event_type=event_type,
        message=message,
        task_id=task_id,
        is_read=False,
        sent_at=None  # NULL = noch nicht gesendet
    )
    session.add(notification)
    await session.commit()
```

**Background-Worker fuer verpasste Notifications:**
```python
async def retry_pending_notifications():
    """Versendet gespeicherte Notifications bei verfuegbarer API."""
    while True:
        pending = await _get_pending_notifications()
        for notification in pending:
            try:
                await send_to_telegram(notification)
                notification.sent_at = utcnow()
                notification.is_read = True
            except Exception as e:
                logger.error(f"Notification send failed: {e}")
                # Naechster Versuch in 5 Minuten
        await asyncio.sleep(300)  # 5 Minuten Interval
```

**Anforderungen:**
- Notifications werden in DB gespeichert wenn Telegram nicht erreichbar
- Background-Worker versucht alle 5 Minuten verpasste Notifications zu senden
- Maximal 24 Stunden alte Notifications (danach verwerfen)

### Schritt 6: Commands fuer Notification-Status

**Datei: `execqueue/workers/telegram_bot.py` (erweitern)**

**Handler: handle_notifications**
```python
async def handle_notifications(update: Update, context: ContextTypes.DEFAULTType):
    """Zeigt aktuelle Subscriptions des Benutzers."""
    # Lade subscribed_events aus TelegramUser
    # Format: "Deine Subscriptions:\ntask_completed - aktiv\nvalidation_failed - inaktiv"
    # Zeige auch ungelesene Notifications
```

**Command-Definition:**
```python
"notifications": {
    "handler": handle_notifications,
    "role": "observer",
    "description": "Zeige deine Subscriptions",
},
```

**Anforderungen:**
- Zeigt alle Event-Typen mit Status (abonniert/nicht abonniert)
- Zeigt Anzahl ungelesener Notifications

## 6. Architektur- und Codequalitaetsvorgaben

**Clean Code:**
- Service ist testbar (Dependency Injection fuer Bot)
- Async/Await fuer alle I/O-Operationen
- Type Hints fuer alle Funktionen

**Minimal Invasivitaet:**
- Notification-Service in EINER Datei (nicht aufgeteilt)
- Trigger-Logik im bestehenden `runner.py` (keine neue Datei)
- Commands in bestehendem `telegram_bot.py` (nicht neu)

**Fehlerbehandlung:**
- Notification-Fehler beeinflussen Task-Ergebnis NICHT
- Fallback auf DB-Queue bei API-Ausfall
- Logging aller Fehler

**Sicherheit:**
- Nur abonnierte Benutzer erhalten Notifications
- Admin-Notifications nur an autorisierte User
- Keine sensiblen Daten in Nachrichten

## 7. Abgrenzung: Was NICHT Teil des Pakets ist

- **Keine Push-Benachrichtigungen** außerhalb von Telegram
- **Keine Read-Receipts** (is_read wird nicht an Telegram gesendet)
- **Keine Notification-History** in der UI (nur in DB)
- **Keine Batch-Notifications** (jede Event separat)
- **Keine Notification-Preflight-Checks** (z.B. "willst du wirklich subscriben?")

## 8. Abhängigkeiten

**Vorausgesetzt:**
- Arbeitspaket 1-01 (Datenbank-Modelle) - `TelegramNotification`
- Arbeitspaket 1-02 (Bot Core) - `TelegramBotWorker`
- `python-telegram-bot` ist installiert

**Wird benötigt für:**
- Arbeitspaket 1-04 (Tests) - testet Benachrichtigungen

## 9. Akzeptanzkriterien

- [ ] `/subscribe task_completed` funktioniert und bestaetigt Subscription
- [ ] `/unsubscribe task_completed` funktioniert und bestaetigt Unsubscription
- [ ] Benutzer erhalten nur Notifications fuer abonnierte Events
- [ ] `notify_task_completed` sendet bei erfolgreichem Task-Abschluss
- [ ] `notify_validation_failed` sendet bei Validierungsfehler
- [ ] `notify_retry_exhausted` sendet wenn Retry-Limit erreicht
- [ ] Admins erhalten `scheduler_started` und `scheduler_stopped`
- [ ] Notifications werden in DB gespeichert wenn Telegram nicht erreichbar
- [ ] Background-Worker versucht verpasste Notifications zu senden
- [ ] `/notifications` zeigt aktuelle Subscriptions an
- [ ] Notification-Versand blockiert Task-Ausfuehrung NICHT
- [ ] Error in Notification beeinflusst Task-Ergebnis NICHT

## 10. Risiken / Prüfpunkte

| Risiko | Auswirkung | Minderung |
|--------|------------|-----------|
| Telegram API Down | Notifications gehen verloren | DB-Queue als Fallback |
| Zu viele Notifications | Benutzer blockiert Bot | Rate-Limiting pro Benutzer |
| Spam durch Events | Benutzer unsubscriben | Opt-in Modell (standardmaessig nichts abonniert) |
| Performance bei vielen Benutzern | Langsame Task-Ausfuehrung | Async fire-and-forget, nicht warten |

**Prüfpunkte vor Merge:**
- [ ] Notification-Sendelogik getestet (mit Mock-Bot)
- [ ] DB-Queue funktioniert (Simulation API-Ausfall)
- [ ] Subscription-Check korrekt (nur abonnierte Benutzer erhalten Events)
- [ ] Admin-Notifications nur an Admins

## 11. Begründung für Struktur

**Warum `telegram_notification_service.py`?**
- **Trennung von Concerns**: Notification-Logik ist unabhagig von Command-Handling
- **Wiederverwendung**: Service kann von Scheduler UND Bot verwendet werden
- **Testbarkeit**: Service ist isoliert testbar (Dependency Injection)

**Warum Trigger in `runner.py`?**
- **Minimal Invasivitaet**: Notification-Trigger gehoert an Stelle wo Task-Abschluss passiert
- **Keine neue Abstraktion**: Kein Grund fuer separates `notification_trigger.py`
- **Konsistenz**: Scheduler ist verantwortlich fuer Task-Lebenszyklus (inkl. Notifications)

**Bewusste Entscheidung: Keine separate Notification-Queue-Datei**
- DB-Queue ist einfach genug fuer `telegram_notification_service.py`
- Keine komplexe Queue-Infrastruktur (RabbitMQ, Redis) noetig
- Fallback-Logik ist lokal verstaendlich im Service

## 12. Empfohlene Dateinamen

- `execqueue/workers/telegram_notification_service.py`
- `execqueue/workers/telegram_bot.py` (erweitern um Subscription-Commands)
- `execqueue/scheduler/runner.py` (erweitern um Notification-Trigger)

## 13. Zielpfade

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/workers/telegram_notification_service.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/workers/telegram_bot.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/scheduler/runner.py`

---

**Ende Arbeitspaket 1-03**