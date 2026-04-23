# Arbeitspaket 1-04: Admin-Funktionen und Berechtigungsverwaltung

## 1. Titel
Admin-Funktionen und Berechtigungsverwaltung für Telegram-Bot

## 2. Ziel
Implementierung von Admin-spezifischen Commands für Benutzer-Management, System-Statistiken und Betriebs-Logs (`/admin users`, `/admin grant`, `/admin revoke`, `/admin logs`, `/admin db_stats`).

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: System-Administration und User-Management
- **Zielgruppe**: Administratoren
- **Business Value**: Ermöglicht Dezentrale Verwaltung von Bot-Berechtigungen ohne Datenbankzugriff

## 4. Betroffene Bestandteile

**Neu zu erstellen:**
- `execqueue/workers/telegram_bot.py` - Erweiterung um Admin-Commands (in bestehende Datei)

**Zu erweitern:**
- `execqueue/workers/telegram_bot.py` - Add Admin-Command-Handler
- `execqueue/services/telegram_admin_service.py` - Admin-spezifische Geschäftslogik

**Bereits vorhanden:**
- `execqueue/models/telegram_user.py` - für User-Management
- `execqueue/api/health.py` - für DB-Stats (kann wiederverwendet werden)

## 5. Konkrete Umsetzungsschritte

### Schritt 1: Admin-Service erstellen

**Datei: `execqueue/services/telegram_admin_service.py`**

**Struktur:**
```python
class TelegramAdminService:
    """Service fuer Admin-Funktionen im Telegram-Bot."""
    
    def __init__(self, session: Session):
        self.session = session
        
    def list_all_users(self) -> list[TelegramUser]:
        """Listet alle Telegram-Benutzer."""
        return session.exec(
            select(TelegramUser).order_by(TelegramUser.created_at)
        ).all()
    
    def grant_admin_role(self, telegram_id: str) -> TelegramUser:
        """Verleiht einem Benutzer Admin-Rolle."""
        user = session.exec(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        ).first()
        
        if not user:
            # Benutzer nicht gefunden - erstellen
            user = TelegramUser(
                telegram_id=telegram_id,
                role="admin",
                username=None
            )
        else:
            user.role = "admin"
        
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    
    def revoke_admin_role(self, telegram_id: str) -> bool:
        """Entzieht einem Benutzer Admin-Rolle."""
        user = session.exec(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        ).first()
        
        if not user:
            return False
        
        if user.role != "admin":
            return False  # War kein Admin
        
        user.role = "operator"  # Fall-back zu operator
        session.add(user)
        session.commit()
        return True
    
    def get_system_stats(self) -> dict:
        """Ermittelt System-Statistiken."""
        from execqueue.models.task import Task
        from execqueue.models.requirement import Requirement
        
        task_count = session.exec(select(func.count()).select_from(Task)).one()
        requirement_count = session.exec(
            select(func.count()).select_from(Requirement)
        ).one()
        user_count = session.exec(
            select(func.count()).select_from(TelegramUser)
        ).one()
        
        return {
            "tasks": task_count,
            "requirements": requirement_count,
            "telegram_users": user_count,
            "admin_users": session.exec(
                select(func.count()).select_from(TelegramUser)
                .where(TelegramUser.role == "admin")
            ).one(),
        }
    
    def get_recent_logs(self, limit: int = 50) -> list[str]:
        """Ermittelt letzte System-Logs (aus application log)."""
        # Hinweis: Logs kommen aus application log, nicht aus DB
        # Hier: Mock-Implementation oder Integration mit logging-System
        return []  # TODO: Implement logging retrieval
```

**Anforderungen:**
- Service verwendet Dependency Injection (Session wird injiziert)
- Alle Operationen sind idempotent (mehrfach ausführbar)
- Fehlerbehandlung bei nicht-existenten Benutzern
- Logging aller Admin-Operationen

### Schritt 2: Admin-Commands implementieren

**Datei: `execqueue/workers/telegram_bot.py` (erweitern)**

**Command-Handler:**

1. **handle_admin_users** - Liste aller Benutzer
```python
async def handle_admin_users(update: Update, context: ContextTypes.DEFAULTType):
    """Zeigt alle Telegram-Benutzer mit Rollen."""
    # Lade alle Benutzer aus DB
    # Format: "👥 *Alle Benutzer:*\n\n123456789 - @username (admin)\n987654321 - John Doe (operator)"
    # Paginierung bei > 20 Benutzern
```

2. **handle_admin_grant** - Admin-Rolle vergeben
```python
async def handle_admin_grant(update: Update, context: ContextTypes.DEFAULTType):
    """Verleiht einem Benutzer Admin-Rolle."""
    # Parse telegram_id aus Command
    # Validiere Format (muss Integer sein)
    # Prüfe ob Absender selbst Admin ist
    # Rufe service.grant_admin_role() auf
    # Bestätige mit Benutzer-Details
```

3. **handle_admin_revoke** - Admin-Rolle entziehen
```python
async def handle_admin_revoke(update: Update, context: ContextTypes.DEFAULTType):
    """Entzieht einem Benutzer Admin-Rolle."""
    # Parse telegram_id aus Command
    # Validiere Format
    # Prüfe ob Absender selbst Admin ist
    # Schutz: Kann sich nicht selbst entziehen
    # Rufe service.revoke_admin_role() auf
    # Bestätige mit Ergebnis
```

4. **handle_admin_logs** - System-Logs anzeigen
```python
async def handle_admin_logs(update: Update, context: ContextTypes.DEFAULTType):
    """Zeigt letzte System-Logs."""
    # Parse limit aus Command (Default: 50)
    # Rufe service.get_recent_logs() auf
    # Format: "📋 *Letzte 50 Logs:*\n\n[2026-04-23 12:00:00] INFO: Task #123 completed"
    # Truncation bei > 4000 Zeichen
```

5. **handle_admin_db_stats** - Datenbank-Statistiken
```python
async def handle_admin_db_stats(update: Update, context: ContextTypes.DEFAULTType):
    """Zeigt Datenbank-Statistiken."""
    # Rufe service.get_system_stats() auf
    # Format: "📊 *Datenbank-Statistiken:*\n\nTasks: 123\nRequirements: 45\nTelegram Users: 12 (4 Admins)"
```

**Command-Definitionen:**
```python
"admin users": {
    "handler": handle_admin_users,
    "role": "admin",
    "description": "Liste aller Telegram-Benutzer",
},
"admin grant": {
    "handler": handle_admin_grant,
    "role": "admin",
    "description": "Admin-Rolle vergeben: /admin grant <telegram_id>",
    "requires_arg": True,
},
"admin revoke": {
    "handler": handle_admin_revoke,
    "role": "admin",
    "description": "Admin-Rolle entziehen: /admin revoke <telegram_id>",
    "requires_arg": True,
},
"admin logs": {
    "handler": handle_admin_logs,
    "role": "admin",
    "description": "Zeige System-Logs: /admin logs [limit]",
},
"admin db_stats": {
    "handler": handle_admin_db_stats,
    "role": "admin",
    "description": "Zeige Datenbank-Statistiken",
},
```

**Anforderungen:**
- Admin-Commands erfordern explizite Admin-Rolle (Role-Check)
- Schutz vor sich selbst entziehen (`/admin revoke <eigenes_id>`)
- Input-Validierung (telegram_id muss Integer sein)
- Fehlermeldungen bei nicht-existenten Benutzern

### Schritt 3: Admin-Role-Check verstärken

**Datei: `execqueue/workers/telegram_bot.py` (erweitern)**

**Erweiterter Role-Check:**
```python
async def check_admin_permission(self, user_id: str, session: Session) -> bool:
    """Prüft ob Benutzer Admin-Rechte hat."""
    # Prüfe Datenbank
    user = session.exec(
        select(TelegramUser).where(TelegramUser.telegram_id == str(user_id))
    ).first()
    
    if user and user.role == "admin":
        return True
    
    # Prüfe Environment-Liste (Fallback)
    admin_ids = os.getenv("TELEGRAM_ADMIN_USER_IDS", "").split(",")
    if str(user_id) in admin_ids:
        return True
    
    return False
```

**Anforderungen:**
- Database-Roll hat Vorrang vor Environment-Liste
- Logging bei Admin-Zugriff (Audit-Trail)
- Fehler bei fehlgeschlagener Prüfung

### Schritt 4: Audit-Logging für Admin-Operationen

**Datei: `execqueue/workers/telegram_bot.py` (erweitern)**

**Audit-Log-Helper:**
```python
def log_admin_action(
    user_id: str,
    action: str,
    target_user_id: Optional[str] = None,
    success: bool = True
):
    """Loggt Admin-Aktion für Audit-Trail."""
    message = f"AUDIT: User {user_id} performed {action}"
    if target_user_id:
        message += f" on target {target_user_id}"
    if not success:
        message += " [FAILED]"
    
    logger.warning(message)  # WARNING-Level für Audit-Logs
```

**Verwendung in Handlers:**
```python
async def handle_admin_grant(update: Update, context: ContextTypes.DEFAULTType):
    user_id = update.effective_user.id
    target_id = context.args[0]
    
    try:
        user = service.grant_admin_role(target_id)
        log_admin_action(str(user_id), "grant_admin", target_id, True)
        await update.message.reply_text(f"✅ {target_id} ist jetzt Admin")
    except Exception as e:
        log_admin_action(str(user_id), "grant_admin", target_id, False)
        await update.message.reply_text(f"❌ Fehler: {e}")
```

**Anforderungen:**
- Alle Admin-Operationen werden geloggt
- SUCCESS/FAILURE wird unterschieden
- Logging auf WARNING-Level (separat von INFO)

### Schritt 5: Schutzmechanismen implementieren

**Datei: `execqueue/workers/telegram_bot.py` (erweitern)**

**Schutz vor Missbrauch:**
```python
# 1. Kann sich nicht selbst entziehen
if target_id == str(user_id):
    await update.message.reply_text("❌ Du kannst dir deine eigenen Admin-Rechte nicht entziehen.")
    return

# 2. Mindestens ein Admin muss immer vorhanden sein
admin_count = service.get_admin_count()
if admin_count == 1 and action == "revoke":
    await update.message.reply_text("❌ Es muss mindestens ein Admin vorhanden sein.")
    return

# 3. Rate-Limiting fuer Admin-Commands (10 pro Minute)
if not check_rate_limit(user_id, admin_only=True):
    await update.message.reply_text("❌ Rate-Limit erreicht. Warte 60 Sekunden.")
    return
```

**Anforderungen:**
- Schutz vor unbeabsichtigtem Self-Lockout
- Mindestens ein Admin immer vorhanden
- Strengeres Rate-Limiting fuer Admin-Commands

## 6. Architektur- und Codequalitaetsvorgaben

**Clean Code:**
- Admin-Service ist isoliert testbar
- Type Hints fuer alle Funktionen
- Docstrings fuer öffentliche Methoden

**Minimal Invasivitaet:**
- Admin-Service in EINER Datei
- Admin-Commands in bestehendem `telegram_bot.py` (nicht neu)
- Keine separaten Permission-Helper-Dateien

**Sicherheit:**
- Role-Check VOR jeder Admin-Operation
- Audit-Logging fuer alle Admin-Aktionen
- Schutz vor Self-Lockout
- Input-Validierung (telegram_id Format)

**Fehlerbehandlung:**
- Graceful Error-Messages fuer Benutzer
- Detaillierte Logs fuer Debugging
- Keine Stacktraces in Bot-Nachrichten

## 7. Abgrenzung: Was NICHT Teil des Pakets ist

- **Keine Web-Oberfläche** fuer User-Management
- **Keine Bulk-Operationen** (z.B. "grant admin to all")
- **Keine Role-Hierarchie** (nur admin/operator/observer)
- **Keine temporären Admin-Rechte** (z.B. "admin for 1 hour")
- **Keine detaillierten Audit-Reports** (nur Logs)

## 8. Abhängigkeiten

**Vorausgesetzt:**
- Arbeitspaket 1-01 (Datenbank-Modelle) - `TelegramUser`
- Arbeitspaket 1-02 (Bot Core) - Basis-Infrastruktur
- `python-telegram-bot` ist installiert

**Wird benötigt für:**
- Arbeitspaket 1-05 (Tests) - testet Admin-Funktionen

## 9. Akzeptanzkriterien

- [ ] `/admin users` zeigt alle Benutzer mit Rollen
- [ ] `/admin grant <id>` verleiht Admin-Rolle und bestaetigt
- [ ] `/admin revoke <id>` entzieht Admin-Rolle und bestaetigt
- [ ] Benutzer kann sich nicht selbst Admin-Rechte entziehen
- [ ] Mindestens ein Admin bleibt immer erhalten
- [ ] `/admin logs [limit]` zeigt System-Logs
- [ ] `/admin db_stats` zeigt Datenbank-Statistiken
- [ ] Alle Admin-Operationen werden audit-geloggt
- [ ] Rate-Limiting fuer Admin-Commands (10/Minute)
- [ ] Non-Admins erhalten "Access denied" bei Admin-Commands
- [ ] Input-Validierung fuer telegram_id (muss Integer sein)

## 10. Risiken / Prüfpunkte

| Risiko | Auswirkung | Minderung |
|--------|------------|-----------|
| Alle Admins deaktivieren | System ist unzugänglich | Mindestens 1 Admin-Check vor revoke |
| Self-Lockout | Admin kann sich nicht mehr helfen | Schutz vor self-revoke |
| Telegram-ID Spoofing | Falscher Benutzer wird admin-isiert | Validierung der Absender-ID |
| Rate-Limit Bypass | Admin-Commands werden missbraucht | Strenges Rate-Limiting (10/min) |

**Prüfpunkte vor Merge:**
- [ ] Admin-Commands nur mit Admin-Rolle ausführbar
- [ ] Schutzmechanismen getestet (self-revoke, min 1 admin)
- [ ] Audit-Logs werden korrekt geschrieben
- [ ] Rate-Limiting funktioniert fuer Admin-Commands

## 11. Begründung für Struktur

**Warum `telegram_admin_service.py`?**
- **Trennung von Concerns**: Admin-Logik ist separiert von Bot-Commands
- **Wiederverwendung**: Service kann von anderen Admin-Tools verwendet werden
- **Testbarkeit**: Service ist isoliert testbar (ohne Bot-Mock)

**Warum Admin-Commands in `telegram_bot.py`?**
- **Konsistenz**: Alle Commands an einem Ort
- **Verstaendlichkeit**: Command-Routing ist zentral
- **Keine Aufblaehung**: Admin-Commands sind nur ~200 Zeilen extra

**Bewusste Entscheidung: Keine separate Permission-Manager-Datei**
- Role-Check ist einfach genug fuer lokalen Helper
- Keine komplexe Permission-Infrastruktur noetig
- Audit-Logging ist lokal im Bot verstaendlich

## 12. Empfohlene Dateinamen

- `execqueue/services/telegram_admin_service.py`
- `execqueue/workers/telegram_bot.py` (erweitern um Admin-Commands)

## 13. Zielpfade

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/services/telegram_admin_service.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/workers/telegram_bot.py`

---

**Ende Arbeitspaket 1-04**