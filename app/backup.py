"""Copias de seguridad y tarea periódica en segundo plano.

Para MariaDB: genera un dump SQL comprimido (.sql.gz) usando PyMySQL.
Para SQLite: copia el archivo .db usando la API de backup nativa.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, backup_dir, get_settings

logger = logging.getLogger("agenda.backup")

STATE_FILE = DATA_DIR / "backup_state.json"
CHECK_INTERVAL_SECONDS = 60

# Tablas a incluir en el dump MariaDB (orden: primero las padres)
_MARIADB_TABLES = [
    "notes",
    "quick_notes",
    "tags",
    "note_tags",
    "subtasks",
    "routines",
    "routine_records",
    "schema_version",
]


# ---------------------------------------------------------------------------
# Estado persistente
# ---------------------------------------------------------------------------


def _read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp.replace(STATE_FILE)


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------


def list_backups() -> list[dict[str, Any]]:
    directory = backup_dir()
    if not directory.exists():
        return []
    valid_suffixes = {".db", ".sqlite3", ".sql", ".gz"}
    items: list[dict[str, Any]] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        # Aceptar .sql.gz y .db
        suffixes = "".join(path.suffixes)
        if not any(path.name.endswith(s) for s in (".db", ".sqlite3", ".sql.gz")):
            continue
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items


def _cleanup(directory: Path, keep: int) -> None:
    files = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and any(
                path.name.endswith(s) for s in (".db", ".sqlite3", ".sql.gz")
            )
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files[keep:]:
        try:
            path.unlink()
            logger.info("Copia antigua eliminada: %s", path.name)
        except OSError as exc:
            logger.warning("No se pudo eliminar %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Backup MariaDB (dump SQL comprimido, Python puro)
# ---------------------------------------------------------------------------


def _escape_sql_value(value: Any) -> str:
    """Escapa un valor para incluirlo en un INSERT SQL."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | float):
        return str(value)
    # Cadena: escapar comillas simples y barras
    text = str(value)
    text = text.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def _dump_mariadb(target: Path) -> None:
    """Genera un dump SQL completo de la BD MariaDB y lo comprime en .sql.gz."""
    import pymysql

    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = int(os.environ.get("DB_PORT", "3306"))
    db_name = os.environ.get("DB_NAME", "milo")
    user = os.environ.get("DB_USER", "milo_app")
    password = os.environ.get("DB_PASSWORD", "")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        charset="utf8mb4",
        connect_timeout=10,
    )

    lines: list[str] = [
        "-- Agenda backup",
        f"-- Created: {datetime.now(timezone.utc).isoformat()}",
        f"-- Database: {db_name}",
        "",
        "SET FOREIGN_KEY_CHECKS=0;",
        "SET NAMES utf8mb4;",
        "",
    ]

    try:
        with conn.cursor() as cur:
            for table in _MARIADB_TABLES:
                # Comprobar si la tabla existe
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = %s",
                    (db_name, table),
                )
                if cur.fetchone()[0] == 0:
                    continue

                # Schema de la tabla
                cur.execute(f"SHOW CREATE TABLE `{table}`")
                row = cur.fetchone()
                create_sql = row[1]
                lines.append(f"DROP TABLE IF EXISTS `{table}`;")
                lines.append(create_sql + ";")
                lines.append("")

                # Datos
                cur.execute(f"SELECT * FROM `{table}`")
                rows = cur.fetchall()
                if rows:
                    columns = [desc[0] for desc in cur.description]
                    col_list = ", ".join(f"`{c}`" for c in columns)
                    for data_row in rows:
                        values = ", ".join(_escape_sql_value(v) for v in data_row)
                        lines.append(
                            f"INSERT INTO `{table}` ({col_list}) VALUES ({values});"
                        )
                    lines.append("")
    finally:
        conn.close()

    lines.append("SET FOREIGN_KEY_CHECKS=1;")
    content = "\n".join(lines).encode("utf-8")

    with gzip.open(str(target), "wb") as gz:
        gz.write(content)


# ---------------------------------------------------------------------------
# Backup SQLite (API nativa)
# ---------------------------------------------------------------------------


def _dump_sqlite(target: Path) -> None:
    from app.config import database_path

    source_path = database_path()
    if not source_path.exists():
        raise FileNotFoundError("La base de datos SQLite todavía no existe")

    dest_path = target.with_suffix(".db")
    source = sqlite3.connect(str(source_path))
    destination = sqlite3.connect(str(dest_path))
    try:
        with destination:
            source.backup(destination)
    finally:
        destination.close()
        source.close()
    # Devolvemos la ruta real (con .db)
    if dest_path != target:
        target.unlink(missing_ok=True)
        return dest_path  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Punto de entrada único
# ---------------------------------------------------------------------------


def create_backup(reason: str = "manual") -> dict[str, Any]:
    """Crea una copia de seguridad según el tipo de BD configurada."""
    settings = get_settings()
    db_type = os.environ.get("DB_TYPE", "mariadb").lower().strip()
    target_dir = backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if db_type == "sqlite":
        # El nombre final tendrá .db (añadido por _dump_sqlite)
        base = target_dir / f"agenda-{stamp}"
        counter = 1
        while (base.with_suffix(".db")).exists():
            base = target_dir / f"agenda-{stamp}-{counter}"
            counter += 1
        result_path = _dump_sqlite_path(base)
    else:
        target = target_dir / f"agenda-{stamp}.sql.gz"
        counter = 1
        while target.exists():
            target = target_dir / f"agenda-{stamp}-{counter}.sql.gz"
            counter += 1
        _dump_mariadb(target)
        result_path = target

    _cleanup(target_dir, settings.backups.keep)
    now = datetime.now(timezone.utc).isoformat()
    _write_state({"last_backup": now, "last_reason": reason})
    logger.info("Copia de seguridad creada: %s", result_path.name)
    return {
        "name": result_path.name,
        "size": result_path.stat().st_size,
        "created_at": now,
        "reason": reason,
    }


def _dump_sqlite_path(base: Path) -> Path:
    """Wrapper que devuelve la ruta real del backup SQLite."""
    from app.config import database_path

    source_path = database_path()
    if not source_path.exists():
        raise FileNotFoundError("La base de datos SQLite todavía no existe")

    target = base.with_suffix(".db")
    source = sqlite3.connect(str(source_path))
    destination = sqlite3.connect(str(target))
    try:
        with destination:
            source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


# ---------------------------------------------------------------------------
# Programador
# ---------------------------------------------------------------------------


def _last_backup_datetime() -> datetime | None:
    state = _read_state()
    candidates: list[datetime] = []
    raw = state.get("last_backup")
    if isinstance(raw, str):
        try:
            value = datetime.fromisoformat(raw)
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            candidates.append(value)
        except ValueError:
            pass

    directory = backup_dir()
    if directory.exists():
        for path in directory.iterdir():
            if not path.is_file():
                continue
            if any(path.name.endswith(s) for s in (".db", ".sqlite3", ".sql.gz")):
                try:
                    candidates.append(
                        datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                    )
                except OSError:
                    continue
    return max(candidates) if candidates else None


def maybe_scheduled_backup() -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.backups.enabled:
        return None
    last = _last_backup_datetime()
    now = datetime.now(timezone.utc)
    interval = settings.backups.frequency_hours * 3600
    if last is not None and (now - last).total_seconds() < interval:
        return None
    try:
        return create_backup(reason="scheduled")
    except Exception as exc:
        logger.warning("No se pudo crear la copia automática: %s", exc)
        return None


async def backup_scheduler() -> None:
    await asyncio.sleep(2)
    while True:
        try:
            await asyncio.to_thread(maybe_scheduled_backup)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Error en el planificador de copias: %s", exc)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def safe_backup_path(name: str) -> Path:
    if Path(name).name != name or not name:
        raise ValueError("Nombre de archivo inválido")
    path = (backup_dir() / name).resolve()
    if path.parent.resolve() != backup_dir().resolve() or not path.is_file():
        raise FileNotFoundError("Copia de seguridad no encontrada")
    return path


def restore_backup(name: str) -> dict[str, Any]:
    """Restaura una copia de seguridad sobre la BD activa.

    - SQLite (.db): crea primero un backup de seguridad, luego sobreescribe.
    - MariaDB (.sql.gz): ejecuta el dump SQL sobre la BD activa.

    Lanza ValueError/FileNotFoundError ante parámetros incorrectos.
    Lanza RuntimeError si la restauración falla a nivel de BD.
    """
    path = safe_backup_path(name)
    db_type = os.environ.get("DB_TYPE", "mariadb").lower().strip()

    if name.endswith(".sql.gz"):
        if db_type == "sqlite":
            raise ValueError("Este backup es de MariaDB y no se puede restaurar sobre SQLite")
        _restore_mariadb(path)
    elif name.endswith((".db", ".sqlite3")):
        if db_type != "sqlite":
            raise ValueError("Este backup es de SQLite y no se puede restaurar sobre MariaDB")
        _restore_sqlite(path)
    else:
        raise ValueError(f"Formato de backup no reconocido: {name}")

    logger.info("Restauración completada desde: %s", name)
    return {"restored": name, "database": db_type}


def _restore_mariadb(path: Path) -> None:
    """Ejecuta un dump .sql.gz sobre la BD MariaDB activa."""
    import gzip as _gzip
    import pymysql

    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = int(os.environ.get("DB_PORT", "3306"))
    db_name = os.environ.get("DB_NAME", "milo")
    user = os.environ.get("DB_USER", "milo_app")
    password = os.environ.get("DB_PASSWORD", "")

    with _gzip.open(str(path), "rb") as gz:
        sql_bytes = gz.read()
    sql_text = sql_bytes.decode("utf-8")

    conn = pymysql.connect(
        host=host, port=port, user=user, password=password,
        database=db_name, charset="utf8mb4", connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            # Ejecutar sentencia a sentencia (ignorar comentarios y vacías)
            for statement in sql_text.split(";"):
                stmt = statement.strip()
                if stmt and not stmt.startswith("--"):
                    try:
                        cur.execute(stmt)
                    except Exception as exc:
                        logger.debug("Sentencia omitida: %s – %s", stmt[:60], exc)
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"Error al restaurar MariaDB: {exc}") from exc
    finally:
        conn.close()


def _restore_sqlite(path: Path) -> None:
    """Sobreescribe la BD SQLite activa con el backup dado."""
    from app.config import database_path

    target = database_path()
    # Crear backup de seguridad previo
    try:
        create_backup(reason="pre-restore")
    except Exception as exc:
        logger.warning("No se pudo crear copia previa a la restauración: %s", exc)

    src = sqlite3.connect(str(path))
    dst = sqlite3.connect(str(target))
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()
