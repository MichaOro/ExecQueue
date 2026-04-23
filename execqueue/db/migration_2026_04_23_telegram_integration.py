"""
Datenbank-Migration für Telegram-Integration

Erstellt Tabellen telegram_user und telegram_notification.
Verwendet ALTER TABLE um existierende Daten zu erhalten.

Ausführungsanleitung:
    python -m execqueue.db.migration_2026_04_23_telegram_integration

WICHTIG: Vor Production-Ausführung ein Backup erstellen!
"""

from sqlmodel import Session, text
from execqueue.db.engine import DATABASE_URL, TEST_DATABASE_URL, engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(session: Session, is_test: bool = False):
    """Führt Migration auf der gegebenen Datenbank aus."""
    db_type = "TEST" if is_test else "PRODUCTION"
    logger.info(f"Beginne Migration auf {db_type}-Datenbank")
    
    migrations = [
        # Tabelle telegram_user erstellen
        """
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
        """,
        
        # Indexe für telegram_user
        """
        CREATE INDEX IF NOT EXISTS idx_telegram_user_telegram_id ON telegram_user(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_telegram_user_role ON telegram_user(role);
        CREATE INDEX IF NOT EXISTS idx_telegram_user_is_active ON telegram_user(is_active);
        """,
        
        # Tabelle telegram_notification erstellen
        """
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
        """,
        
        # Indexe für telegram_notification
        """
        CREATE INDEX IF NOT EXISTS idx_telegram_notification_user ON telegram_notification(user_telegram_id);
        CREATE INDEX IF NOT EXISTS idx_telegram_notification_event_type ON telegram_notification(event_type);
        CREATE INDEX IF NOT EXISTS idx_telegram_notification_is_read ON telegram_notification(is_read);
        CREATE INDEX IF NOT EXISTS idx_telegram_notification_sent_at ON telegram_notification(sent_at);
        """,
    ]
    
    for i, migration_sql in enumerate(migrations, 1):
        logger.info(f"Migration Schritt {i}/{len(migrations)}")
        try:
            session.exec(text(migration_sql))
            session.commit()
            logger.info(f"✓ Migration Schritt {i} erfolgreich")
        except Exception as e:
            logger.error(f"✗ Migration Schritt {i} fehlgeschlagen: {e}")
            raise
    
    logger.info(f"✓ Migration auf {db_type}-Datenbank erfolgreich abgeschlossen")


def ensure_tables_exist(session: Session):
    """Stellt sicher, dass Tabellen existieren (nur für Test-Datenbank)."""
    from sqlmodel import SQLModel
    try:
        # Prüfen ob Tabellen existieren
        session.exec(text("SELECT 1 FROM telegram_user LIMIT 1"))
        logger.info("Telegram-Tabellen existieren bereits")
    except Exception:
        logger.info("Telegram-Tabellen existieren nicht - erstelle sie...")
        SQLModel.metadata.create_all(engine)
        logger.info("Telegram-Tabellen erfolgreich erstellt")


def main():
    """Hauptfunktion - führt Migration auf Test und Production aus."""
    import sys
    
    # Prüfen ob nur Test-Datenbank migriert werden soll
    test_only = "--test-only" in sys.argv
    
    # Test-Datenbank migrieren
    logger.info("=" * 60)
    from sqlmodel import Session
    from execqueue.db.engine import engine as test_engine
    
    # Sicherstellen, dass Tabellen existieren
    with Session(test_engine) as session:
        ensure_tables_exist(session)
    
    with Session(test_engine) as session:
        run_migration(session, is_test=True)
    
    if test_only:
        logger.info("Test-only Modus - Production-Migration übersprungen")
        return
    
    # Production-Datenbank migrieren (mit Bestätigung)
    print("\n" + "=" * 60)
    print("WARNUNG: Dies wird die Production-Datenbank ändern!")
    print("Stelle sicher, dass ein Backup erstellt wurde.")
    print("=" * 60)
    
    confirmation = input("\nMöchten Sie fortfahren? (type 'YES' to confirm): ")
    if confirmation != "YES":
        logger.info("Migration abgebrochen durch Benutzer")
        return
    
    with Session(engine) as session:
        run_migration(session, is_test=False)
    
    logger.info("=" * 60)
    logger.info("✓ Migration erfolgreich abgeschlossen!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
