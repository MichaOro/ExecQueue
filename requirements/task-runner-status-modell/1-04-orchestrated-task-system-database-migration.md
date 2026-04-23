# Arbeitspaket 4: Datenbank-Migration und Schema-Management

## 1. Titel
Datenbank-Migration: Sichere Schema-Erweiterung ohne Datenverlust

## 2. Ziel
Durchführung einer sicheren Datenbank-Migration, die neue Felder zu bestehenden Tabellen hinzufügt OHNE existierende Daten zu verlieren. Die Migration muss in Test-Umgebung validiert und für Production vorbereitet sein.

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: Datenbank-Schema-Management
- **Zweck**: Erweiterung bestehender Tabellen ohne Datenverlust
- **Bezug**: Anforderungsartefakt Section 16 (Datenbank-Migration und Schema-Management)

## 4. Betroffene Bestandteile

### Zu ändernde Dateien:
- `execqueue/db/engine.py` - Migration-Logik anpassen
- **Neue Datei**: `migrations/schema_migration.sql` - SQL-Migrationsskript
- **Neue Datei**: `migrations/rollback.sql` - Rollback-Skript

### Datenbank-Tabellen:
- `requirement` - 6 neue Felder
- `work_packages` - 4 neue Felder + Foreign Key
- `tasks` - 4 neue Felder

### Bestehende Komponenten:
- `create_db_and_tables()` - Muss für Production deaktiviert/angepasst werden
- `check_and_migrate_db()` - Muss erweitert werden

## 5. Konkrete Umsetzungsschritte

### Schritt 1: Migrations-Verzeichnis erstellen
**Ziel**: Strukturierte Ablage für Migrationsskripte

**Umsetzung**:
```bash
mkdir -p migrations
```

**Dateien erstellen**:
- `migrations/schema_migration.sql` - Haupt-Migration
- `migrations/rollback.sql` - Rollback-Skript
- `migrations/README.md` - Migrations-Anleitung

### Schritt 2: SQL-Migrationsskript erstellen
**Ziel**: Alle Schema-Änderungen als idempotentes SQL-Skript

**Inhalt `migrations/schema_migration.sql`**:
```sql
-- Requirement Tabelle erweitern
ALTER TABLE requirement 
    ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog',
    ADD COLUMN IF NOT EXISTS "type" VARCHAR(50) DEFAULT 'artifact',
    ADD COLUMN IF NOT EXISTS has_work_packages BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS order_number INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS scheduler_enabled BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS parallelization_delay INTEGER DEFAULT 0;

-- WorkPackage Tabelle erweitern
ALTER TABLE work_packages
    ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog',
    ADD COLUMN IF NOT EXISTS order_number INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dependency_id INTEGER,
    ADD COLUMN IF NOT EXISTS parallelization_enabled BOOLEAN DEFAULT FALSE;

-- Task Tabelle erweitern
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS block_queue BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS parallelization_allowed BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS schedulable BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog';

-- Fremdschlüssel für dependency_id hinzufügen
ALTER TABLE work_packages
    ADD CONSTRAINT IF NOT EXISTS fk_work_packages_dependency
    FOREIGN KEY (dependency_id) REFERENCES work_packages(id);

-- Indizes erstellen
CREATE INDEX IF NOT EXISTS idx_requirement_queue_status ON requirement(queue_status);
CREATE INDEX IF NOT EXISTS idx_work_packages_queue_status ON work_packages(queue_status);
CREATE INDEX IF NOT EXISTS idx_tasks_queue_status ON tasks(queue_status);
CREATE INDEX IF NOT EXISTS idx_tasks_block_queue_status ON tasks(block_queue, status);

-- Bestehende Daten aktualisieren (falls nötig)
UPDATE requirement SET queue_status = 'backlog' WHERE queue_status IS NULL;
UPDATE work_packages SET queue_status = 'backlog' WHERE queue_status IS NULL;
UPDATE tasks SET queue_status = 'queued' WHERE queue_status IS NULL;
```

**Wichtig**: 
- `IF NOT EXISTS` für idempotente Ausführung
- `DEFAULT` Werte für existierende Daten
- Keine `DROP` oder `TRUNCATE` Befehle

### Schritt 3: Rollback-Skript erstellen
**Ziel**: Migration kann bei Problemen rückgängig gemacht werden

**Inhalt `migrations/rollback.sql`**:
```sql
-- Indizes entfernen
DROP INDEX IF EXISTS idx_tasks_block_queue_status;
DROP INDEX IF EXISTS idx_tasks_queue_status;
DROP INDEX IF EXISTS idx_work_packages_queue_status;
DROP INDEX IF EXISTS idx_requirement_queue_status;

-- Fremdschlüssel entfernen
ALTER TABLE work_packages DROP CONSTRAINT IF EXISTS fk_work_packages_dependency;

-- Felder entfernen (VORSICHT: Daten gehen verloren!)
ALTER TABLE tasks DROP COLUMN IF EXISTS queue_status;
ALTER TABLE tasks DROP COLUMN IF EXISTS schedulable;
ALTER TABLE tasks DROP COLUMN IF EXISTS parallelization_allowed;
ALTER TABLE tasks DROP COLUMN IF EXISTS block_queue;

ALTER TABLE work_packages DROP COLUMN IF EXISTS parallelization_enabled;
ALTER TABLE work_packages DROP COLUMN IF EXISTS dependency_id;
ALTER TABLE work_packages DROP COLUMN IF EXISTS order_number;
ALTER TABLE work_packages DROP COLUMN IF EXISTS queue_status;

ALTER TABLE requirement DROP COLUMN IF EXISTS parallelization_delay;
ALTER TABLE requirement DROP COLUMN IF EXISTS scheduler_enabled;
ALTER TABLE requirement DROP COLUMN IF EXISTS order_number;
ALTER TABLE requirement DROP COLUMN IF EXISTS has_work_packages;
ALTER TABLE requirement DROP COLUMN IF EXISTS "type";
ALTER TABLE requirement DROP COLUMN IF EXISTS queue_status;
```

**Warnung**: Rollback löscht alle neuen Felder und deren Daten!

### Schritt 4: Migration-Helper in engine.py erweitern
**Ziel**: Einfache Ausführung der Migration

**Änderungen in `execqueue/db/engine.py`**:

```python
def run_migration(migration_file: str = "migrations/schema_migration.sql"):
    """Run database migration from SQL file.
    
    Args:
        migration_file: Path to migration SQL file
        
    Raises:
        FileNotFoundError: If migration file not found
        RuntimeError: If migration fails
    """
    migration_path = Path(migration_file)
    if not migration_path.exists():
        raise FileNotFoundError(f"Migration file not found: {migration_file}")
    
    with migration_path.open() as f:
        migration_sql = f.read()
    
    try:
        with engine.connect() as conn:
            # Execute each statement separately
            for statement in migration_sql.split(';'):
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    conn.execute(text(statement))
            conn.commit()
        
        logger.info("Migration %s completed successfully", migration_file)
    except Exception as e:
        logger.error("Migration failed: %s", e)
        raise RuntimeError(f"Migration failed: {e}")


def backup_database(backup_file: str = "db_backup.sql"):
    """Create a database backup.
    
    WARNING: This is a simple backup. For production, use pg_dump.
    
    Args:
        backup_file: Path to backup file
    """
    # Simple backup using SQLModel metadata
    # For production, use: pg_dump DATABASE_URL > backup_file
    logger.warning("Simple backup created. For production, use pg_dump")
    # Implementation depends on specific needs
```

### Schritt 5: `create_db_and_tables()` für Production schützen
**Ziel**: Verhindern dass `drop_all()` in Production ausgeführt wird

**Änderungen in `execqueue/db/engine.py`**:

```python
def create_db_and_tables(allow_drop: bool = False):
    """Create all database tables.
    
    WARNING: This drops and recreates ALL tables if allow_drop=True.
    Use only for development or test databases.
    
    Args:
        allow_drop: If True, drops existing tables. Default False for safety.
    """
    if allow_drop:
        logger.warning("DROPPING all tables - this will delete all data!")
        SQLModel.metadata.drop_all(engine)
    
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables created successfully")


def check_and_migrate_db():
    """Check if database needs migration and run migrations.
    
    This should be called on application startup.
    Prioritizes SQL migrations over create_all.
    """
    migration_file = Path("migrations/schema_migration.sql")
    
    if migration_file.exists():
        logger.info("Running SQL migration...")
        run_migration(str(migration_file))
    else:
        logger.warning("No migration file found, using create_all")
        # Only create tables, don't drop
        SQLModel.metadata.create_all(engine)
    
    logger.info("Database migration completed successfully")
```

### Schritt 6: Migrations-README erstellen
**Ziel**: Klare Anleitung für Migration in verschiedenen Umgebungen

**Inhalt `migrations/README.md`**:

```markdown
# Datenbank-Migration

## Voraussetzungen

- PostgreSQL Datenbank läuft
- DATABASE_URL in .env gesetzt
- Backup der Production-Datenbank (für Production-Migration)

## Migration in Test-Umgebung

```bash
# 1. Test-Datenbank prüfen
export DATABASE_URL=postgresql://user:pass@test-db/queue_test

# 2. Migration ausführen
python -c "from execqueue.db.engine import run_migration; run_migration()"

# 3. Schema prüfen
psql $DATABASE_URL -c "\d requirement"
psql $DATABASE_URL -c "\d work_packages"
psql $DATABASE_URL -c "\d tasks"

# 4. Tests ausführen
pytest
```

## Migration in Production

### Vor der Migration

```bash
# 1. Backup erstellen (EMPFOHLEN: pg_dump)
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# 2. Backup verifizieren
pg_restore --list backup_*.sql

# 3. Downtime-Fenster planen
```

### Migration ausführen

```bash
# 1. Application stoppen
sudo systemctl stop execqueue

# 2. Migration ausführen
export DATABASE_URL=postgresql://user:pass@prod-db/queue
python -c "from execqueue.db.engine import run_migration; run_migration()"

# 3. Schema verifizieren
psql $DATABASE_URL -c "SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name IN ('requirement', 'work_packages', 'tasks');"

# 4. Application starten
sudo systemctl start execqueue

# 5. Logs prüfen
sudo journalctl -u execqueue -f
```

### Bei Problemen (Rollback)

```bash
# 1. Application stoppen
sudo systemctl stop execqueue

# 2. Rollback ausführen (VORSICHT: Datenverlust!)
python -c "from execqueue.db.engine import run_migration; run_migration('migrations/rollback.sql')"

# 3. Oder Backup wiederherstellen
pg_restore -d $DATABASE_URL backup_*.sql

# 4. Application starten
sudo systemctl start execqueue
```

## Migration verifizieren

```sql
-- Neue Felder prüfen
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'requirement' AND column_name IN (
    'queue_status', 'type', 'has_work_packages', 
    'order_number', 'scheduler_enabled', 'parallelization_delay'
);

-- Indizes prüfen
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'tasks';

-- Datenintegrität prüfen
SELECT COUNT(*) FROM requirement WHERE queue_status IS NULL;
SELECT COUNT(*) FROM work_packages WHERE queue_status IS NULL;
SELECT COUNT(*) FROM tasks WHERE queue_status IS NULL;
```

## Häufige Probleme

### Constraint violation bei Fremdschlüssel
- Prüfen ob `dependency_id` auf existierende WorkPackages zeigt
- Oder temporär Fremdschlüssel entfernen

### Index bereits vorhanden
- Skript ist idempotent mit `IF NOT EXISTS`
- Manuelles Löschen falls nötig: `DROP INDEX IF EXISTS`

### Downtime zu lang
- Migration während Wartungsfenster
- Online-Migration mit minimalen Locks
- Blue-Green Deployment betrachten
```

### Schritt 7: Migration in Test-Umgebung validieren
**Ziel**: Sicherstellen dass Migration funktioniert

**Umsetzung**:
```bash
# 1. Test-Datenbank mit existierenden Daten füllen
# (Bestehende Tests verwenden oder manuelle Daten)

# 2. Migration ausführen
python -c "from execqueue.db.engine import run_migration; run_migration()"

# 3. Schema prüfen
psql $TEST_DATABASE_URL -c "\d requirement"

# 4. Daten prüfen
psql $TEST_DATABASE_URL -c "SELECT * FROM requirement LIMIT 5;"

# 5. Tests ausführen
pytest
```

### Schritt 8: Environment-Konfiguration
**Ziel**: Migration nur in bestimmten Umgebungen erlauben

**Änderungen in `execqueue/runtime.py`**:
```python
def is_production() -> bool:
    """Check if running in production environment."""
    return os.getenv("EXECQUEUE_ENV", "development") == "production"


def allow_schema_changes() -> bool:
    """Check if schema changes are allowed."""
    # Block in production unless explicitly allowed
    if is_production():
        return os.getenv("ALLOW_SCHEMA_CHANGES", "false").lower() == "true"
    return True
```

**Anpassung in `engine.py`**:
```python
def run_migration(migration_file: str = "migrations/schema_migration.sql"):
    """Run database migration with production safety checks."""
    if is_production() and not allow_schema_changes():
        raise RuntimeError(
            "Schema changes blocked in production. "
            "Set ALLOW_SCHEMA_CHANGES=true to override (use with caution)."
        )
    # ... rest of migration logic
```

## 6. Architektur- und Codequalitätsvorgaben

### Sicherheit
- **Kein Datenverlust**: Migration darf keine Daten löschen
- **Idempotenz**: Migration kann mehrfach ausgeführt werden
- **Rollback-Fähigkeit**: Rollback-Skript muss funktionieren
- **Production-Schutz**: Migration in Production nur mit expliziter Erlaubnis

### Code-Qualität
- **SQL-Injection-Schutz**: Keine dynamischen SQL-Strings
- **Fehlerbehandlung**: Klare Fehlermeldungen bei Problemen
- **Logging**: Alle Migrationsschritte protokollieren
- **Documentation**: Klare README mit Beispielen

### Datenbank-Praxis
- **IF NOT EXISTS**: Alle ALTER TABLE mit IF NOT EXISTS
- **DEFAULT Werte**: Neue Felder haben sinnvolle Defaults
- **Indizes**: Nur wirklich benötigte Indizes erstellen
- **Foreign Keys**: Mit CONSTRAINT IF NOT EXISTS

## 7. Abgrenzung: Was nicht Teil des Pakets ist

**Nicht enthalten**:
- Alembic-Migrationen (manuelle SQL-Migration bevorzugt)
- Data-Migration (Bestehende Daten werden nicht transformiert)
- Performance-Optimierung (Indizes nur für neue Felder)
- Backup-Strategie (nur einfacher Hinweis auf pg_dump)

**Explizite Entscheidungen**:
- **Keine Alembic** - Manuelle SQL-Migration einfacher und kontrollierbarer
- **Keine Data-Transformation** - Neue Felder erhalten Defaults
- **Kein automatisches Backup** - Manuelles Backup vor Production-Migration

## 8. Abhängigkeiten

### Vor diesem Paket:
- **AP-1 (Model-Erweiterungen)** - Kenntnis der neuen Felder

### Nach diesem Paket:
- **AP-2 (Queue-Service)** - Kann neue Felder verwenden
- **AP-3 (Scheduler-Erweiterung)** - Kann neue Felder verwenden
- **Production-Deploy** - Nur nach erfolgreicher Migration

## 9. Akzeptanzkriterien

### Funktionale Kriterien
- [ ] Migration fügt alle 14 neuen Felder hinzu
- [ ] Bestehende Daten bleiben erhalten
- [ ] Neue Felder haben korrekte Defaults
- [ ] Indizes werden erstellt
- [ ] Fremdschlüssel wird hinzugefügt

### Technische Kriterien
- [ ] Migration ist idempotent (mehrfach ausführbar)
- [ ] Rollback-Skript funktioniert
- [ ] Production-Schutz aktiv (ALLOW_SCHEMA_CHANGES)
- [ ] Logging aller Migrationsschritte
- [ ] README mit klaren Anweisungen

### Sicherheitskriterien
- [ ] Backup-Empfehlung in README
- [ ] Warning bei `drop_all()` in `create_db_and_tables()`
- [ ] Production-Migration nur mit expliziter Erlaubnis
- [ ] Rollback-Plan dokumentiert

## 10. Risiken / Prüfpunkte

### Kritische Risiken
- **Datenverlust**: Bei falscher Migration oder Rollback
  - **Minderung**: Vollständiges Backup vor Migration
  - **Minderung**: Migration zuerst in Test-Umgebung
  
- **Downtime**: Lange Migration blockiert Application
  - **Minderung**: Migration während Wartungsfenster
  - **Minderung**: Skript optimieren für schnelle Ausführung

- **Konflikt mit existierenden Daten**: Constraints verletzt
  - **Minderung**: Daten vor Migration prüfen
  - **Minderung**: Temporär Constraints entfernen

### Prüfpunkte vor Production
- [ ] Migration in Test-Umgebung erfolgreich getestet
- [ ] Backup verifiziert und getestet
- [ ] Rollback-Skript in Test-Umgebung getestet
- [ ] Wartungsfenster geplant
- [ ] Team informiert über Downtime
- [ ] Monitoring aktiviert nach Migration

## 11. Begründung für neue Dateien/Module

### Neue Dateien erforderlich:

**`migrations/schema_migration.sql`**:
- Zentrale Ablage für alle Schema-Änderungen
- Idempotentes SQL-Skript für wiederholbare Ausführung
- Versionierbar im Git-Repository
- **Begründung**: SQL-Migrationen müssen explizit dokumentiert und versioniert sein

**`migrations/rollback.sql`**:
- Notwendig für Fehlerfälle
- Klare Gegenmaßnahme zur Migration
- **Begründung**: Rollback muss ebenso getestet sein wie Migration

**`migrations/README.md`**:
- Klare Anleitung für verschiedene Umgebungen
- Troubleshooting und häufige Probleme
- **Begründung**: Migration ist kritisch und muss dokumentiert sein

**Keine Alembic-Konfiguration**:
- **Begründung**: Projekt verwendet manuelle Schema-Verwaltung (siehe AGENTS.md)
- **Begründung**: Einfacher SQL-Skripte geben mehr Kontrolle

## 12. Empfohlener Dateiname
`1-04-orchestrated-task-system-database-migration.md`

## 13. Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/requirements/task-runner-status-modell/1-04-orchestrated-task-system-database-migration.md`

---

**Arbeitspaket Version**: 1.0  
**Erstellt**: 2026-04-23  
**Priorität**: CRITICAL (Blocker für Production-Deploy)  
**Geschätzter Aufwand**: 4-6 Stunden (inkl. Testing und Documentation)  
**Verantwortlich**: Build Agent (ExecQueue)  
**Production-Warnung**: Vor Production-Migration unbedingt Backup erstellen!

EXECQUEUE.STATUS.FINISHED
