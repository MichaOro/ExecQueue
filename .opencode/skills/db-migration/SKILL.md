---
name: db-migration
description: Handle database schema changes without Alembic migrations
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: database
---

## Was ich tue
- Analysiere Änderungen an SQLModel-Definitionen
- Erstelle manuelle Migration-Skripte für Schema-Änderungen
- Aktualisiere `execqueue/db/engine.py` bei Bedarf
- Dokumentiere Breaking Changes in Migrations
- Prüfe Data Integrity und Constraints
- Optimiere Indizes und Performance

## Wann du mich verwendest
- Bei neuen Models oder Feldern: "Add a new field to the Task model"
- Bei Schema-Änderungen: "Update the database schema for work packages"
- Vor Deployments: "Check what database changes are needed"
- Bei Performance-Problemen: "Optimize database queries for tasks"
- Für Indizes: "Add indexes to improve query performance"

## Wichtige Hinweise

### Keine Alembic Migrations
- Schema wird via `SQLModel.metadata.create_all()` erstellt
- Manuelles Sync erforderlich bei Model-Änderungen
- **Achtung**: Bestehende Daten können verloren gehen!
- Immer in Test-DB validieren vor Produktion

### Model-Konventionen
- `updated_at` hat `default_factory` aber KEIN `onupdate`
  → Manuell setzen: `task.updated_at = datetime.now(timezone.utc)`
- `is_test` Filter in ALLEN Queries
  → Verwende `is_test_mode()` Helper
- Relationships mit `joinedload()` laden
  → Vermeidet N+1 Queries

### Test-Mode Handling
```python
from execqueue.validation.test_mode import is_test_mode, apply_test_label

# In Models
class Task(SQLModel, table=True):
    id: Optional[int] = None
    is_test: bool = False  # Automatisch gesetzt via apply_test_label()
    
# In Queries
stmt = select(Task).where(Task.is_test == is_test_mode())

# Test data prefixing
task.id = apply_test_label("task_123")
```

## Migration-Workflow

### 1. Impact Assessment
```
- Welche Tabellen/Modelle betroffen?
- Datenverlust-Risiko?
- Backwards Compatibility?
- Welche Queries müssen angepasst werden?
```

### 2. Model-Änderungen
```python
# ❌ Schlecht: Feld einfach hinzufügen
class Task(SQLModel, table=True):
    id: Optional[int] = None
    title: str
    new_field: str  # Bestehende Daten haben keinen Wert!

# ✅ Gut: Default Value oder nullable
class Task(SQLModel, table=True):
    id: Optional[int] = None
    title: str
    new_field: Optional[str] = None  # Oder mit Default
```

### 3. Manuelles Migration-Skript
```python
# scripts/migrate_add_field.py
import asyncio
from sqlmodel import Session, select
from execqueue.db.engine import engine
from execqueue.models.task import Task

async def migrate():
    async with engine.connect() as conn:
        # Beispiel: Spalte hinzufügen (PostgreSQL)
        await conn.execute(
            text("ALTER TABLE task ADD COLUMN new_field VARCHAR(255)")
        )
        
        # Bestehende Daten migrieren
        result = await conn.execute(text("SELECT id FROM task"))
        for row in result:
            await conn.execute(
                text("UPDATE task SET new_field = 'default_value' WHERE id = :id"),
                {"id": row.id}
            )
        
        await conn.commit()

asyncio.run(migrate())
```

### 4. `create_db_and_tables()` Aktualisieren
```python
# execqueue/db/engine.py
async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    # Manuelle Migrationen hier aufrufen
    # await migrate_add_new_field()
```

### 5. Tests ausführen
```bash
# Test-DB neu erstellen
python -c "import execqueue.db.engine as e; e.create_db_and_tables()"

# Tests ausführen
pytest tests/test_models.py tests/test_db.py
```

### 6. Dokumentieren
```markdown
## Changelog Entry

### Database Migration [YYYY-MM-DD]
- Added: `new_field` to `Task` model
- Migration: `scripts/migrate_add_field.py`
- Breaking: No (backward compatible)
```

## Checkliste

- [ ] Model-Änderungen identifiziert
- [ ] Impact Assessment durchgeführt
- [ ] Datenverlust-Risiko bewertet
- [ ] Manuelles Migration-Skript erstellt
- [ ] Test-DB Migration getestet
- [ ] `create_db_and_tables()` aktualisiert
- [ ] Alle Tests erfolgreich
- [ ] Änderungen dokumentiert
- [ ] Production-Backup erstellt
- [ ] Rollback-Plan erstellt

## Bekannte Gotchas

1. **`updated_at` nicht auto-updated**
   → Manuell setzen in allen Update-Operationen

2. **`is_test` Filter wiederholt**
   → Zentralisierung in `execqueue/validation/test_mode.py` erwägen

3. **Relationships nicht geladen**
   → Immer `joinedload()` verwenden

4. **Bestehende Daten**
   → Immer Default Values oder nullable Felder bei neuen Spalten

5. **Test-DB Isolation**
   → Jede Test muss eigene DB-Session haben

## Troubleshooting

### "Table already exists" Fehler
→ Schema bereits erstellt, nur Model aktualisieren
→ Migration-Skript für Daten-Migration schreiben

### "Column does not exist" Fehler
→ Migration-Skript nicht ausgeführt
→ Datenbank nicht neu erstellt

### Foreign Key Constraints
→ Prüfe Dependencies zwischen Tables
→ Migration in richtiger Reihenfolge ausführen

### Performance-Probleme nach Migration
→ Indizes überprüfen
→ Query-Plan analysieren
→ `EXPLAIN ANALYZE` verwenden

## Best Practices

- **Immer zuerst in Test-DB**
- **Backup vor Production-Migration**
- **Migration-Skripte versionieren**
- **Rollback-Plan erstellen**
- **Dokumentation aktuell halten**
