from sqlmodel import create_engine, SQLModel, Session
from contextlib import contextmanager
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import text
from execqueue.runtime import get_opencode_base_url
import logging
import os

logger = logging.getLogger(__name__)

# Pfad zur .env Datei (Projekt-Root)
DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"

def _load_database_url() -> str:
    """Lädt die DATABASE_URL aus .env Datei.
    
    Returns:
        DATABASE_URL aus .env
        
    Raises:
        FileNotFoundError: Wenn .env Datei nicht existiert
        ValueError: Wenn DATABASE_URL nicht gesetzt oder invalid ist
    """
    # .env Datei laden
    if not DOTENV_PATH.exists():
        raise FileNotFoundError(
            f".env Datei nicht gefunden bei {DOTENV_PATH}. "
            "Bitte .env Datei im Projekt-Root erstellen (siehe .env.example)."
        )
    
    dotenv_vars = dotenv_values(DOTENV_PATH)
    
    # DATABASE_URL prüfen
    database_url = dotenv_vars.get("DATABASE_URL", "").strip()
    
    if not database_url:
        raise ValueError(
            "DATABASE_URL ist in der .env Datei nicht gesetzt. "
            "Bitte einen gültigen PostgreSQL-Verbindungsstring hinzufügen."
        )
    
    # Grundlegende Validierung der URL-Struktur
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
        raise ValueError(
            f"DATABASE_URL muss mit 'postgresql://', 'postgresql+psycopg://' oder 'postgresql+psycopg2://' beginnen. "
            f"Erhaltener Wert: {database_url[:50]}..."
        )
    
    return database_url


def _load_test_database_url() -> str | None:
    """Lädt die TEST_DATABASE_URL aus .env Datei oder Environment.
    
    Returns:
        TEST_DATABASE_URL oder None wenn nicht gesetzt
        
    Note:
        TEST_DATABASE_URL ist optional. Wenn nicht gesetzt, wird DATABASE_URL verwendet.
    """
    # Zuerst aus Environment variablen prüfen (hat Priorität)
    test_db_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if test_db_url:
        return test_db_url
    
    # Dann aus .env Datei
    if DOTENV_PATH.exists():
        dotenv_vars = dotenv_values(DOTENV_PATH)
        test_db_url = dotenv_vars.get("TEST_DATABASE_URL", "").strip()
        if test_db_url:
            return test_db_url
    
    return None


def _validate_connection(database_url: str, db_name: str = "database") -> bool:
    """Prüft ob eine Datenbankverbindung hergestellt werden kann.
    
    Args:
        database_url: PostgreSQL Verbindungsstring
        db_name: Name der Datenbank für Logging
        
    Returns:
        True wenn Verbindung erfolgreich, False sonst
    """
    try:
        test_engine = create_engine(database_url, echo=False)
        with test_engine.connect() as conn:
            # Führe einen einfachen SELECT 1 aus um die Verbindung zu testen
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        logger.debug("%s Verbindung erfolgreich", db_name)
        return True
    except Exception as e:
        logger.warning("%s Verbindung fehlgeschlagen: %s", db_name, str(e))
        return False


# URLs laden und validieren
try:
    DATABASE_URL = _load_database_url()
    logger.info("DATABASE_URL erfolgreich geladen")
except (FileNotFoundError, ValueError) as e:
    logger.error(str(e))
    raise


# Test-Datenbank URL (optional)
TEST_DATABASE_URL = _load_test_database_url()
if TEST_DATABASE_URL:
    logger.info("TEST_DATABASE_URL erfolgreich geladen")
else:
    logger.info("TEST_DATABASE_URL nicht gesetzt, verwende DATABASE_URL")
    TEST_DATABASE_URL = DATABASE_URL


# Engine erstellen
engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables():
    """Create all database tables.
    
    WARNING: This drops and recreates ALL tables. Use only for development
    or when you know the consequences. Alembic migrations should be used
    for production databases.
    """
    try:
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise


def check_and_migrate_db():
    """Check if database needs migration and run Alembic migrations.
    
    This should be called on application startup in production.
    """
    try:
        from alembic import command
        from alembic.config import Config
        
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
    except ImportError:
        # Alembic not installed - fall back to create_all
        logger.warning("Alembic not installed, using create_all")
        SQLModel.metadata.create_all(engine)
    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        raise


@contextmanager
def get_session():
    """Get a database session (sync context manager for API dependencies)."""
    with Session(engine) as session:
        yield session
