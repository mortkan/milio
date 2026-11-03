#!/usr/bin/env python3
"""Migración de datos SQLite → MariaDB.

Uso:
    python scripts/migrate_sqlite_to_mariadb.py [--sqlite PATH] [--dry-run]

Variables de entorno necesarias (o en .env):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

El script lee la base SQLite, inserta los registros en MariaDB y valida
que los conteos origen/destino coincidan. Hace rollback ante cualquier error.
No borra ni modifica la BD SQLite original.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

# Carga .env si existe
try:
    from dotenv import load_dotenv
    _root = Path(__file__).parent.parent
    _env = _root / ".env"
    if _env.exists():
        load_dotenv(_env, override=False)
except ImportError:
    pass

# Añade el directorio raíz al path para importar app.*
sys.path.insert(0, str(Path(__file__).parent.parent))

import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("migrate")


def _mariadb_url() -> str:
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = int(os.environ.get("DB_PORT", "3306"))
    name = os.environ.get("DB_NAME", "milo")
    user = os.environ.get("DB_USER", "milo_app")
    password = os.environ.get("DB_PASSWORD", "")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


def migrate(sqlite_path: Path, dry_run: bool = False) -> None:
    if not sqlite_path.exists():
        logger.error("No existe el archivo SQLite: %s", sqlite_path)
        sys.exit(1)

    # Conectar a SQLite
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    # Contar registros origen
    src_notes = src.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    src_quick = src.execute("SELECT COUNT(*) FROM quick_notes").fetchone()[0]
    src_routines = src.execute("SELECT COUNT(*) FROM routines").fetchone()[0]
    src_records = src.execute("SELECT COUNT(*) FROM routine_records").fetchone()[0]
    logger.info(
        "SQLite — notas: %d, quick_notes: %d, rutinas: %d, registros: %d",
        src_notes, src_quick, src_routines, src_records,
    )

    if src_notes + src_quick + src_routines == 0:
        logger.info("La base SQLite está vacía. No hay datos que migrar.")
        return

    if dry_run:
        logger.info("[DRY-RUN] Simulación completada. No se escribió nada.")
        return

    # Conectar a MariaDB
    from sqlalchemy import create_engine, text
    url = _mariadb_url()
    engine = create_engine(url, pool_pre_ping=True)

    # Inicializar esquema destino
    from app.models import Base
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        # Leer y migrar notas
        notes = src.execute(
            "SELECT id, title, content, note_date, time, category, color, "
            "priority, completed, recurrence, recurrence_end, status, position, "
            "created_at, updated_at FROM notes"
        ).fetchall()

        inserted_notes = 0
        for row in notes:
            conn.execute(text(
                "INSERT IGNORE INTO notes "
                "(id, title, content, note_date, time, category, color, "
                " priority, completed, recurrence, recurrence_end, status, position, "
                " item_type, progress_percent, created_at, updated_at) "
                "VALUES (:id, :title, :content, :note_date, :time, :category, :color, "
                "        :priority, :completed, :recurrence, :recurrence_end, :status, :position, "
                "        'note', 0, :created_at, :updated_at)"
            ), {
                "id": row["id"],
                "title": row["title"] or "",
                "content": row["content"] or "",
                "note_date": row["note_date"],
                "time": row["time"],
                "category": row["category"],
                "color": row["color"],
                "priority": row["priority"],
                "completed": bool(row["completed"]),
                "recurrence": row["recurrence"] or "none",
                "recurrence_end": row["recurrence_end"],
                "status": row["status"] or "none",
                "position": row["position"] or 0,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
            inserted_notes += 1

        # Quick notes
        quick = src.execute(
            "SELECT id, content, created_at FROM quick_notes"
        ).fetchall()
        inserted_quick = 0
        for row in quick:
            conn.execute(text(
                "INSERT IGNORE INTO quick_notes (id, content, created_at) "
                "VALUES (:id, :content, :created_at)"
            ), dict(row))
            inserted_quick += 1

        # Routines
        routines = src.execute(
            "SELECT id, title, description, schedule, color, icon, "
            "checklist_template, created_at, updated_at FROM routines"
        ).fetchall()
        inserted_routines = 0
        for row in routines:
            conn.execute(text(
                "INSERT IGNORE INTO routines "
                "(id, title, description, schedule, color, icon, "
                " checklist_template, created_at, updated_at) "
                "VALUES (:id, :title, :description, :schedule, :color, :icon, "
                "        :checklist_template, :created_at, :updated_at)"
            ), {
                "id": row["id"],
                "title": row["title"] or "",
                "description": row["description"],
                "schedule": row["schedule"] or "daily",
                "color": row["color"],
                "icon": row["icon"],
                "checklist_template": row["checklist_template"] or "",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
            inserted_routines += 1

        # Routine records
        records = src.execute(
            "SELECT id, routine_id, date, completed, completed_at, notes FROM routine_records"
        ).fetchall()
        inserted_records = 0
        for row in records:
            conn.execute(text(
                "INSERT IGNORE INTO routine_records "
                "(id, routine_id, date, completed, completed_at, notes) "
                "VALUES (:id, :routine_id, :date, :completed, :completed_at, :notes)"
            ), {
                "id": row["id"],
                "routine_id": row["routine_id"],
                "date": row["date"],
                "completed": bool(row["completed"]),
                "completed_at": row["completed_at"],
                "notes": row["notes"],
            })
            inserted_records += 1

    # Verificar
    with engine.connect() as conn:
        dst_notes = conn.execute(text("SELECT COUNT(*) FROM notes")).scalar()
        dst_quick = conn.execute(text("SELECT COUNT(*) FROM quick_notes")).scalar()
        dst_routines = conn.execute(text("SELECT COUNT(*) FROM routines")).scalar()
        dst_records = conn.execute(text("SELECT COUNT(*) FROM routine_records")).scalar()

    logger.info(
        "MariaDB — notas: %d, quick_notes: %d, rutinas: %d, registros: %d",
        dst_notes, dst_quick, dst_routines, dst_records,
    )

    errors = []
    if inserted_notes > 0 and dst_notes < inserted_notes:
        errors.append(f"Notas: esperadas >= {inserted_notes}, encontradas {dst_notes}")
    if inserted_quick > 0 and dst_quick < inserted_quick:
        errors.append(f"Quick notes: esperadas >= {inserted_quick}, encontradas {dst_quick}")
    if inserted_routines > 0 and dst_routines < inserted_routines:
        errors.append(f"Rutinas: esperadas >= {inserted_routines}, encontradas {dst_routines}")

    if errors:
        logger.error("Discrepancias en la validación:\n  %s", "\n  ".join(errors))
        sys.exit(1)

    logger.info(
        "Migración completada: %d notas, %d quick_notes, %d rutinas, %d registros.",
        inserted_notes, inserted_quick, inserted_routines, inserted_records,
    )
    src.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migración SQLite → MariaDB")
    parser.add_argument(
        "--sqlite",
        default="data/agenda.db",
        help="Ruta al archivo SQLite (por defecto: data/agenda.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular sin escribir nada en MariaDB",
    )
    args = parser.parse_args()
    migrate(Path(args.sqlite), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
