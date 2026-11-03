"""Conexión, sesiones e inicialización de la base de datos.

Soporta MariaDB (producción) y opcionalmente SQLite (desarrollo local).
La selección se hace mediante la variable de entorno DB_TYPE:
  DB_TYPE=mariadb  (por defecto)
  DB_TYPE=sqlite   (solo para desarrollo/tests sin MariaDB)
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

logger = logging.getLogger("agenda.database")

_engine_lock = threading.Lock()
_engine: Engine | None = None
_SessionLocal: Any = None  # sessionmaker instance


# ---------------------------------------------------------------------------
# Configuración desde variables de entorno
# ---------------------------------------------------------------------------


def _db_type() -> str:
    return os.environ.get("DB_TYPE", "mariadb").lower().strip()


def _build_mariadb_url() -> str:
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = int(os.environ.get("DB_PORT", "3306"))
    name = os.environ.get("DB_NAME", "milo")
    user = os.environ.get("DB_USER", "milo_app")
    password = os.environ.get("DB_PASSWORD", "")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


def _build_sqlite_url() -> str:
    """URL SQLite para desarrollo/tests."""
    from app.config import database_path  # importación tardía, evita ciclos
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def _pool_settings() -> dict:
    return {
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": True,
    }


def _connect_timeout() -> int:
    return int(os.environ.get("DB_CONNECT_TIMEOUT", "10"))


# ---------------------------------------------------------------------------
# Engine singleton
# ---------------------------------------------------------------------------


def get_engine() -> Engine:
    """Devuelve el engine singleton. Crea uno si no existe."""
    global _engine, _SessionLocal
    with _engine_lock:
        if _engine is not None:
            return _engine

        db = _db_type()
        if db == "sqlite":
            url = _build_sqlite_url()
            logger.info("Usando SQLite: %s", url.split("///")[1] if "///" in url else url)
            _engine = create_engine(
                url,
                connect_args={"check_same_thread": False, "timeout": 30},
                pool_pre_ping=True,
            )
            from sqlalchemy import event

            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _record):
                cursor = dbapi_conn.cursor()
                try:
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.execute("PRAGMA busy_timeout=30000")
                    cursor.execute("PRAGMA journal_mode=WAL")
                finally:
                    cursor.close()

        else:
            url = _build_mariadb_url()
            timeout = _connect_timeout()
            connect_args = {"connect_timeout": timeout}
            try:
                _engine = create_engine(
                    url,
                    connect_args=connect_args,
                    **_pool_settings(),
                )
                # Ocultar contraseña en logs
                safe_url = url.split("@")[1] if "@" in url else url
                logger.info("Engine MariaDB creado: ...@%s", safe_url)
            except Exception as exc:
                logger.error("No se pudo crear el engine MariaDB: %s", exc)
                raise

        _SessionLocal = sessionmaker(
            bind=_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        return _engine


def _session_factory() -> Session:
    if _SessionLocal is None:
        get_engine()  # inicializa _SessionLocal
    return _SessionLocal()


# ---------------------------------------------------------------------------
# Inicialización del esquema
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Crea tablas que no existen. No borra ni altera datos existentes."""
    engine = get_engine()
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Esquema de tablas verificado/creado.")
    except Exception as exc:
        logger.error("Error al inicializar el esquema: %s", exc)
        raise

    db_type = _db_type()
    if db_type != "sqlite":
        _run_mariadb_migrations(engine)
    else:
        _run_sqlite_migrations(engine)


def _run_mariadb_migrations(engine: Engine) -> None:
    """Aplica migraciones idempotentes para MariaDB."""
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INT NOT NULL PRIMARY KEY, "
            "applied_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        ))
        conn.execute(text(
            "INSERT IGNORE INTO schema_version (version) VALUES (1)"
        ))


def _run_sqlite_migrations(engine: Engine) -> None:
    """Migraciones para SQLite (desarrollo/tests)."""
    with engine.begin() as conn:
        # check_existing columns and add missing ones idempotently
        def cols(table: str) -> set[str]:
            rows = conn.exec_driver_sql(f'PRAGMA table_info("{table}")').fetchall()
            return {str(r[1]) for r in rows}

        migrations: dict[str, dict[str, str]] = {
            "notes": {
                "time": "VARCHAR(5)",
                "category": "VARCHAR(50)",
                "color": "VARCHAR(7)",
                "priority": "VARCHAR(30)",
                "completed": "BOOLEAN NOT NULL DEFAULT 0",
                "recurrence": "VARCHAR(10) NOT NULL DEFAULT 'none'",
                "recurrence_end": "DATE",
                "status": "VARCHAR(20) DEFAULT 'none'",
                "position": "INTEGER DEFAULT 0",
                "item_type": "VARCHAR(20) NOT NULL DEFAULT 'note'",
                "estimated_minutes": "INTEGER",
                "actual_minutes": "INTEGER",
                "duration_minutes": "INTEGER",
                "progress_percent": "INTEGER DEFAULT 0",
            },
        }
        for table, columns in migrations.items():
            existing = cols(table)
            if not existing:
                continue
            for name, definition in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(
                        f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'
                    )

        # Migrar tablas legacy (name→title, record_date→date)
        routine_cols = cols("routines")
        if "name" in routine_cols:
            has_title = "title" in routine_cols
            has_schedule = "schedule" in routine_cols
            has_icon = "icon" in routine_cols
            has_color = "color" in routine_cols
            has_checklist = "checklist_template" in routine_cols
            conn.exec_driver_sql("DROP TABLE IF EXISTS routines__migrated")
            conn.exec_driver_sql(
                "CREATE TABLE routines__migrated ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "title VARCHAR(200) NOT NULL, "
                "description TEXT, "
                "schedule VARCHAR(20) NOT NULL, "
                "color VARCHAR(7), icon VARCHAR(10), "
                "checklist_template TEXT NOT NULL, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
            title_expr = "COALESCE(NULLIF(title,''),name,'')" if has_title else "COALESCE(name,'')"
            schedule_expr = "COALESCE(NULLIF(schedule,''),'daily')" if has_schedule else "'daily'"
            icon_expr = "icon" if has_icon else "NULL"
            color_expr = "color" if has_color else "NULL"
            checklist_expr = "COALESCE(checklist_template,'')" if has_checklist else "''"
            has_updated = "updated_at" in routine_cols
            updated_expr = "COALESCE(updated_at,created_at,CURRENT_TIMESTAMP)" if has_updated else "COALESCE(created_at,CURRENT_TIMESTAMP)"
            conn.exec_driver_sql(
                f"INSERT INTO routines__migrated "
                f"SELECT id, {title_expr}, description, "
                f"{schedule_expr}, {color_expr}, {icon_expr}, "
                f"{checklist_expr}, "
                f"COALESCE(created_at,CURRENT_TIMESTAMP), "
                f"{updated_expr} FROM routines"
            )
            conn.exec_driver_sql("DROP TABLE routines")
            conn.exec_driver_sql("ALTER TABLE routines__migrated RENAME TO routines")

        record_cols = cols("routine_records")
        if "record_date" in record_cols:
            has_date = "date" in record_cols
            has_completed_at = "completed_at" in record_cols
            has_notes = "notes" in record_cols
            date_expr = "COALESCE(date, record_date, DATE('now'))" if has_date else "COALESCE(record_date, DATE('now'))"
            completed_at_expr = "completed_at" if has_completed_at else "NULL"
            notes_expr = "notes" if has_notes else "NULL"
            conn.exec_driver_sql("DROP TABLE IF EXISTS routine_records__migrated")
            conn.exec_driver_sql(
                "CREATE TABLE routine_records__migrated ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "routine_id INTEGER NOT NULL, "
                "date DATE NOT NULL, completed BOOLEAN NOT NULL, "
                "completed_at DATETIME, notes TEXT)"
            )
            conn.exec_driver_sql(
                f"INSERT INTO routine_records__migrated "
                f"SELECT id, routine_id, "
                f"{date_expr}, "
                f"COALESCE(completed,0), {completed_at_expr}, {notes_expr} FROM routine_records"
            )
            conn.exec_driver_sql("DROP TABLE routine_records")
            conn.exec_driver_sql(
                "ALTER TABLE routine_records__migrated RENAME TO routine_records"
            )

        # Normalizar valores nulos en notas legacy
        note_existing = cols("notes")
        if note_existing:
            conn.exec_driver_sql(
                "UPDATE notes SET "
                "title = COALESCE(title, ''), "
                "content = COALESCE(content, ''), "
                "note_date = COALESCE(note_date, DATE(created_at), DATE('now')), "
                "completed = COALESCE(completed, 0), "
                "recurrence = COALESCE(NULLIF(recurrence,''), 'none'), "
                "status = COALESCE(NULLIF(status,''), 'none'), "
                "position = COALESCE(position, 0), "
                "created_at = COALESCE(created_at, CURRENT_TIMESTAMP), "
                "updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
            )

        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, "
            "applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.exec_driver_sql(
            "INSERT OR IGNORE INTO schema_version(version) VALUES (1)"
        )


# ---------------------------------------------------------------------------
# Comprobación de salud
# ---------------------------------------------------------------------------


def check_db_health() -> dict:
    """Comprueba la conectividad con la base de datos. No expone credenciales."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"database": "connected"}
    except Exception as exc:
        logger.error("Fallo de conexión con la BD: %s", exc)
        return {"database": "disconnected", "detail": "No se puede conectar con MariaDB"}


# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------


@contextmanager
def get_db_session() -> Iterator[Session]:
    """Context manager para operaciones fuera de FastAPI (backups, seeds…)."""
    session = _session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI: una sesión por petición, siempre liberada."""
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
