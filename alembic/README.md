# Alembic Migrations für ExecQueue

## Überblick

ExecQueue verwendet Alembic für Datenbank-Migrations. Die Migrationen werden automatisch bei jedem Start in Production ausgeführt.

## Quick Start

### Erste Migration erstellen (nach Model-Änderungen)

```bash
# 1. Models ändern
# 2. Migration generieren
alembic revision --autogenerate -m "description of changes"

# 3. Migration prüfen (WICHTIG!)
# Prüfe alembic/versions/<revision>_*.py auf korrekte up/downgrade Logik

# 4. Migration anwenden
alembic upgrade head
```

### Migrationen verwalten

```bash
# Aktuelle Migration anzeigen
alembic current

# Migration History zeigen
alembic history

# Zu vorheriger Migration zurückkehren (Rollback)
alembic downgrade -1

# Zu spezifischer Revision
alembic downgrade <revision_id>
alembic upgrade <revision_id>
```

## Wichtige Hinweise

### ⚠️ Vor Production-Migrationen

1. **Full Backup** der Production-Database erstellen
2. **Auf Staging testen** mit production-ähnlichen Daten
3. **Rollback testen**: `alembic downgrade -1` muss funktionieren
4. **Downtime planen**: Migration kann App-Start blockieren

### ⚠️ Autogenerate prüfen

Alembic's `--autogenerate` ist nicht perfekt:
- **Immer** generierte Migration manuell prüfen
- **Drop-Statements** explizit reviewen (Datenverlust!)
- Bei komplexen Änderungen: **Manuelle Migration** schreiben

### Test-Database

Tests verwenden weiterhin `create_db_and_tables()` für saubere Isolation:
```python
# In conftest.py oder Test-Setup
SQLModel.metadata.drop_all(engine)
SQLModel.metadata.create_all(engine)
```

## Architektur

- `alembic.ini` - Alembic Konfiguration (Root-Verzeichnis)
- `alembic/` - Migrations Verzeichnis
  - `env.py` - Alembic Environment (nutzt SQLModel.metadata)
  - `versions/` - Versionierte Migration-Scripts
- `execqueue/db/engine.py` - Database Engine mit Migration-Hook

## Workflow bei Model-Änderungen

1. **Model ändern** in `execqueue/models/`
2. **Migration generieren**: `alembic revision --autogenerate -m "..."`
3. **Migration prüfen**: 
   - Sind alle Änderungen korrekt?
   - Sind DROP-Statements beabsichtigt?
   - Sind DEFAULT Values korrekt?
4. **Lokal anwenden**: `alembic upgrade head`
5. **Tests laufen**: `pytest`
6. **Commit**: Migration-File mit committen
7. **Deploy**: `alembic upgrade head` im Deploy-Script

## Troubleshooting

### "Table already exists"
- Migration war bereits gestamped: `alembic stamp head`
- Oder: Tabellen manuell löschen (nur Dev!)

### "No changes detected"
- Model-Änderung wurde nicht erkannt
- Prüfe ob Model in `SQLModel.metadata` ist
- Manchmal manuelle Migration nötig

### Destructive Changes
- Alembic erkennt gelöschte Spalten/Tabellen
- **Nicht automatisch** commiten!
- Explizit reviewen und bestätigen

## Production Deployment

```bash
# In Deploy-Script (vor App-Start)
alembic upgrade head
uvicorn execqueue.main:app --host 0.0.0.0 --port 8000
```

**Backup vor Migration!**

---

**Erstellt:** 2026-04-23 (Arbeitspaket 1-03)
**Status:** ✅ Funktionierend
