from sqlmodel import create_engine, SQLModel, Session
from contextlib import contextmanager
from execqueue.runtime import get_opencode_base_url
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = (
    "postgresql+psycopg://neondb_owner:npg_EoJ1iySBWNX6@ep-wispy-sea-alz3z46t-pooler.c-3.eu-central-1.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
)

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
        import os
        
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
