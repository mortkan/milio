import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base

# Use the same Base as app.models to ensure all models are registered
from app.models import Base

get_database_path_cache = {}


def get_database_path() -> str:
    """Get the database path from AGENDA_DB env var or default."""
    return os.environ.get("AGENDA_DB", "data/agenda.db")


def get_engine() -> create_engine:
    """Create and return the SQLAlchemy engine."""
    db_path = get_database_path()
    return create_engine(f"sqlite:///{db_path}")


def init_db() -> None:
    """Initialize the database, creating all tables if they don't exist."""
    db_path = get_database_path()
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Create all tables from models (idempotent)
    Base.metadata.create_all(bind=engine)
    
    # Create schema_version table if it doesn't exist
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """))
        conn.commit()


def get_db() -> Session:
    """Get a database session - used as FastAPI dependency."""
    db_path = get_database_path()
    engine = create_engine(f"sqlite:///{db_path}")
    session = Session(bind=engine)
    return session
