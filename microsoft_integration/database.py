"""Database layer for microsoft_integration.

Uses the same MariaDB instance as Milo (same DB_* env vars).
All Microsoft tables use the ms_ prefix.
This module manages ONLY the Microsoft schema — never touches Milo tables.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from microsoft_integration.config import get_settings

logger = logging.getLogger("microsoft.database")

_engine_lock = threading.Lock()
_engine: Engine | None = None
_SessionLocal: Any = None


def get_engine() -> Engine:
    """Singleton engine for the Microsoft integration database."""
    global _engine, _SessionLocal
    with _engine_lock:
        if _engine is not None:
            return _engine

        settings = get_settings()
        url = settings.database_url
        try:
            _engine = create_engine(
                url,
                connect_args={"connect_timeout": 10},
                pool_size=5,
                max_overflow=10,
                pool_recycle=1800,
                pool_pre_ping=True,
            )
            safe = url.split("@")[1] if "@" in url else url
            logger.info("Microsoft integration DB engine created: ...@%s", safe)
        except Exception as exc:
            logger.error("Cannot create Microsoft integration DB engine: %s", exc)
            raise

        _SessionLocal = sessionmaker(
            bind=_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        return _engine


def reset_engine() -> None:
    """Dispose engine (useful for tests)."""
    global _engine, _SessionLocal
    with _engine_lock:
        if _engine:
            _engine.dispose()
        _engine = None
        _SessionLocal = None


def _session_factory() -> Session:
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal()


@contextmanager
def get_db_session() -> Iterator[Session]:
    """Context manager for non-FastAPI operations."""
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request."""
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db_health() -> dict:
    """Check database connectivity. Never exposes credentials."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"database": "connected"}
    except Exception as exc:
        logger.error("Microsoft integration DB health check failed: %s", exc)
        return {"database": "disconnected", "detail": "Cannot connect to MariaDB"}
