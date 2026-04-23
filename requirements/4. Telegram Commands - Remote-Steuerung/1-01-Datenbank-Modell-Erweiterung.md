# Arbeitspaket 1-01: Datenbank-Modell für Telegram-Integration erweitern

## 1. Titel
Datenbank-Modell für Telegram-Integration erweitern

## 2. Ziel
Erstellung der Datenbank-Tabellen `telegram_user` und `telegram_notification` zur Persistierung von Benutzern, Berechtigungen und Benachrichtigungen.

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: Benutzer- und Notification-Management für Telegram-Bot
- **Zielgruppe**: Bot-Operatoren, Administratoren
- **Business Value**: Ermöglicht rollenbasierte Zugriffssteuerung und persistente Benachrichtigungen

## 4. Betroffene Bestandteile
**Neu zu erstellen:**
- `execqueue/models/telegram_user.py` - User-Entität
- `execqueue/models/telegram_notification.py` - Notification-Entität

**Zu erweitern:**
- `execqueue/db/migration_YYYY_MM_DD_telegram_integration.py` - Migrationsskript
- `execqueue/db/engine.py` - Optional: Referenz zu neuen Models

## 5. Konkrete Umsetzungsschritte

### Schritt 1: TelegramUser Model erstellen
Datei: `execqueue/models/telegram_user.py`

**Felder:**
```python
class TelegramUser(SQLModel, table=True):
    __tablename__ = "telegram_user"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: str = Field(unique=True, index=True)  # Telegram Benutzer-ID
    username: Optional[str] = None  # Telegram Username (ohne @)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = Field(default="observer")  # observer | operator | admin
    subscribed_events: str = Field(default="{}")  # JSON-String: {"task_completed": true, ...}
    is_active: bool = Field(default=True)
    last_active: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    is_test: bool = Field(default=False)  # Für Test-Daten
```

**Anforderungen:**
- `telegram_id` muss UNIQUE sein (ein Telegram-Benutzer nur einmal)
- `role` hat Default-Wert "observer" (Least Privilege)
- `subscribed_events` als JSONB-ähnlicher String (PostgreSQL JSON support)
- `is_test` Flag für Test-Daten (konsistent mit anderen Models)

### Schritt 2: TelegramNotification Model erstellen
Datei: `execqueue/models/telegram_notification.py`

**Felder:**
```python
class TelegramNotification(SQLModel, table=True):
    __tablename__ = "telegram_notification"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_telegram_id: str = Field(index=True)  # Referenz zu TelegramUser
    event_type: str = Field(index=True)  # task_completed | validation_failed | retry_exhausted | scheduler_started | scheduler_stopped
    task_id: Optional[int] = None  # Optional: Referenz zu Task
    message: str  # Benachrichtigungstext
    is_read: bool = Field(default=False)
    sent_at: Optional[datetime] = None  # Wann gesendet (NULL = noch nicht gesendet)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    is_test: bool = Field(default=False)
```

**Anforderungen:**
- `user_telegram_id` indiziert für schnelle Abfragen
- `event_type` indiziert für Filterung
- `task_id` optional (nicht alle Events haben Tasks)
- `sent_at` NULL-bedingt für Queue-ähnliches Verhalten

### Schritt 3: Migrationsskript erstellen
Datei: `execqueue/db/migration_2026_04_23_telegram_integration.py`

**SQL-Statements:**
```sql
-- Tabelle telegram_user erstellen
CREATE TABLE IF NOT EXISTS telegram_user (
    id SERIAL PRIMARY KEY,
    telegram_id VARCHAR(50) UNIQUE NOT NULL,
    username VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'observer' CHECK (role IN ('observer', 'operator', 'admin')),
    subscribed_events TEXT DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_test BOOLEAN DEFAULT FALSE
);

-- Indexe für Performance
CREATE INDEX IF NOT EXISTS idx_telegram_user_telegram_id ON telegram_user(telegram_id);
CREATE INDEX IF NOT EXISTS idx_telegram_user_role ON telegram_user(role);
CREATE INDEX IF NOT EXISTS idx_telegram_user_is_active ON telegram_user(is_active);

-- Tabelle telegram_notification erstellen
CREATE TABLE IF NOT EXISTS telegram_notification (
    id SERIAL PRIMARY KEY,
    user_telegram_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    task_id INTEGER,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_test BOOLEAN DEFAULT FALSE
);

-- Indexe für Performance
CREATE INDEX IF NOT EXISTS idx_telegram_notification_user ON telegram_notification(user_telegram_id);
CREATE INDEX IF NOT EXISTS idx_telegram_notification_event_type ON telegram_notification(event_type);
CREATE INDEX IF NOT EXISTS idx_telegram_notification_is_read ON telegram_notification(is_read);
CREATE INDEX IF NOT EXISTS idx_telegram_notification_sent_at ON telegram_notification(sent_at);
```

**Anforderungen:**
- Migration muss idempotent sein (mehrfach ausführbar ohne Fehler)
- CHECK-Constraints für role und event_type
- Alle必要的 Indexe für häufige Queries

### Schritt 4: Models in __init__.py exportieren
- `execqueue/models/__init__.py`: TelegramUser und TelegramNotification exportieren

### Schritt 5: Migration testen
- Migration auf Test-Datenbank ausführen
- Tabellenstruktur validieren
- Test-Daten einfügen und abfragen

## 6. Architektur- und Codequalitätsvorgaben

**Clean Code:**
- Docstrings für Models (Google Style)
- Type Hints für alle Felder
- Konsistente Benennung mit bestehendem Code (`utcnow()`, `is_test` Flag)

**Minimal Invasivität:**
- Keine Änderungen an existierenden Models
- Neue Models folgen bestehendem Pattern (siehe `requirement.py`)
- Migration folgt Pattern aus `migration_2026_04_23_orchestrated_system.py`

**Testbarkeit:**
- Models müssen in Tests nutzbar sein (mit `is_test=True`)
- Migration muss auf Test- und Production-Datenbank laufen

## 7. Abgrenzung: Was NICHT Teil des Pakets ist

- **Keine Bot-Logik** - nur Datenbank-Struktur
- **Keine API-Endpoints** - kommen in späteren Paketen
- **Keine Business-Logik** - Service-Schicht kommt später
- **Keine Seed-Daten** - manuelles Anlegen von Admin-Benutzern

## 8. Abhängigkeiten

**Vorausgesetzt:**
- Bestehendes `execqueue.db.engine` (DATABASE_URL, TEST_DATABASE_URL)
- Bestehendes `execqueue.db.session` (Session-Management)
- SQLModel ist installiert

**Wird benötigt für:**
- Arbeitspaket 1-02 (Telegram Bot Core) - für User-Validierung
- Arbeitspaket 1-03 (Benachrichtigungen) - für Notification-Speicherung

## 9. Akzeptanzkriterien

- [ ] `TelegramUser` Model ist erstellt und folgt Projekt-Patterns
- [ ] `TelegramNotification` Model ist erstellt und folgt Projekt-Patterns
- [ ] Migrationsskript ist erstellt und idempotent
- [ ] Migration läuft erfolgreich auf Test-Datenbank
- [ ] Migration läuft erfolgreich auf Production-Datenbank (mit Bestätigung)
- [ ] Alle Indexe sind erstellt
- [ ] CHECK-Constraints funktionieren (role, event_type)
- [ ] Tests können neue Models verwenden

## 10. Risiken / Prüfpunkte

| Risiko | Minderung |
|--------|-----------|
| Migration bricht Production-Datenbank | Backup vor Ausführung, Test auf Staging zuerst |
| Telegram-ID-Konflikte (z.B. wenn Benutzer-ID sich ändert) | `telegram_id` als UNIQUE, nicht als PK |
| JSON-Handling in `subscribed_events` | Als String speichern, JSON-Parsing im Service-Layer |

**Prüfpunkte vor Merge:**
- [ ] SQL-Linting (Syntax-Check)
- [ ] Review durch DB-Specialist
- [ ] Migration auf frischer Test-Datenbank validiert

## 11. Begründung für neue Dateien

**Warum neue Model-Dateien?**
- **Fachliche Grenze**: Telegram-spezifische Entitäten gehören nicht in `requirement.py` oder `task.py`
- **Wiederverwendung**: Models werden an mehreren Stellen benötigt (Bot, API, Services)
- **Konsistenz**: Folgt Pattern von `dead_letter.py` (eigene Datei für Entität)

**Warum eigene Migration?**
- **Nachvollziehbarkeit**: Separate Migration für klar abgegrenzte Feature
- **Rollback**: Einfacher rückgängig machen bei Problemen
- **Team-Kollaboration**: Andere Entwickler können Migration reviewen

## 12. Empfohlene Dateinamen

- `execqueue/models/telegram_user.py`
- `execqueue/models/telegram_notification.py`
- `execqueue/db/migration_2026_04_23_telegram_integration.py`

## 13. Zielpfad

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/telegram_user.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/models/telegram_notification.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/db/migration_2026_04_23_telegram_integration.py`

---

**Ende Arbeitspaket 1-01**
