"""
Datenbank-Migration für Orchestriertes Task-System

Fügt neue Felder für Queue-Steuerung und Statusmodell hinzu.
Verwendet ALTER TABLE um existierende Daten zu erhalten.

Ausführungsanleitung:
    python -m execqueue.db.migration_2026_04_23_orchestrated_system

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
        # Requirement Tabelle erweitern
        """
        ALTER TABLE requirement 
        ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog',
        ADD COLUMN IF NOT EXISTS type VARCHAR(50) DEFAULT 'artifact',
        ADD COLUMN IF NOT EXISTS has_work_packages BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS order_number INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS scheduler_enabled BOOLEAN DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS parallelization_delay INTEGER DEFAULT 0;
        """,
        
        # WorkPackage Tabelle erweitern
        """
        ALTER TABLE work_packages
        ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog',
        ADD COLUMN IF NOT EXISTS order_number INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS dependency_id INTEGER,
        ADD COLUMN IF NOT EXISTS parallelization_enabled BOOLEAN DEFAULT FALSE;
        """,
        
        # Task Tabelle erweitern
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS block_queue BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS parallelization_allowed BOOLEAN DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS schedulable BOOLEAN DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog';
        """,
        
        # Fremdschlüssel für dependency_id hinzufügen
        """
        ALTER TABLE work_packages
        ADD CONSTRAINT IF NOT EXISTS fk_work_packages_dependency
        FOREIGN KEY (dependency_id) REFERENCES work_packages(id);
        """,
        
        # Indizes erstellen für bessere Performance
        """
        CREATE INDEX IF NOT EXISTS idx_requirement_queue_status ON requirement(queue_status);
        CREATE INDEX IF NOT EXISTS idx_requirement_order_number ON requirement(order_number);
        CREATE INDEX IF NOT EXISTS idx_requirement_scheduler_enabled ON requirement(scheduler_enabled);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_work_packages_queue_status ON work_packages(queue_status);
        CREATE INDEX IF NOT EXISTS idx_work_packages_order_number ON work_packages(order_number);
        CREATE INDEX IF NOT EXISTS idx_work_packages_dependency ON work_packages(dependency_id);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_tasks_queue_status ON tasks(queue_status);
        CREATE INDEX IF NOT EXISTS idx_tasks_block_queue_status ON tasks(block_queue, status);
        CREATE INDEX IF NOT EXISTS idx_tasks_schedulable ON tasks(schedulable, status);
        CREATE INDEX IF NOT EXISTS idx_tasks_parallelization ON tasks(parallelization_allowed, status);
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
        session.exec(text("SELECT 1 FROM requirement LIMIT 1"))
        logger.info("Tabellen existieren bereits")
    except Exception:
        logger.info("Tabellen existieren nicht - erstelle sie...")
        SQLModel.metadata.create_all(engine)
        logger.info("Tabellen erfolgreich erstellt")


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
