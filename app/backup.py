"""Copias de seguridad de SQLite y tarea periódica en segundo plano."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, backup_dir, database_path, get_settings

logger = logging.getLogger("agenda.backup")

STATE_FILE = DATA_DIR / "backup_state.json"
CHECK_INTERVAL_SECONDS = 60


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


def list_backups() -> list[dict[str, Any]]:
    directory = backup_dir()
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in directory.iterdir():
        if not path.is_file() or path.suffix not in {".db", ".sqlite3"}:
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
            if path.is_file() and path.suffix in {".db", ".sqlite3"}
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


def create_backup(reason: str = "manual") -> dict[str, Any]:
    """Crea una copia consistente con la API de backup de SQLite."""
    settings = get_settings()
    source_path = database_path()
    target_dir = backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError("La base de datos todavía no existe")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"agenda-{stamp}.db"
    counter = 1
    while target.exists():
        target = target_dir / f"agenda-{stamp}-{counter}.db"
        counter += 1

    source = sqlite3.connect(str(source_path))
    destination = sqlite3.connect(str(target))
    try:
        with destination:
            source.backup(destination)
    finally:
        destination.close()
        source.close()

    _cleanup(target_dir, settings.backups.keep)
    now = datetime.now(timezone.utc).isoformat()
    _write_state({"last_backup": now, "last_reason": reason})
    logger.info("Copia de seguridad creada: %s", target.name)
    return {
        "name": target.name,
        "size": target.stat().st_size,
        "created_at": now,
        "reason": reason,
    }


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
        for path in directory.glob("agenda-*.db"):
            try:
                candidates.append(
                    datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                )
            except OSError:
                continue
    return max(candidates) if candidates else None


def maybe_scheduled_backup() -> dict[str, Any] | None:
    """Crea una copia si está activada y ha pasado el intervalo configurado."""
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
    """Bucle cooperativo; los ajustes se releen en cada comprobación."""
    await asyncio.sleep(2)
    while True:
        try:
            await asyncio.to_thread(maybe_scheduled_backup)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as exc:  # pragma: no cover
            logger.exception("Error en el planificador de copias: %s", exc)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def safe_backup_path(name: str) -> Path:
    """Evita path traversal al descargar una copia."""
    if Path(name).name != name or not name:
        raise ValueError("Nombre de archivo inválido")
    path = (backup_dir() / name).resolve()
    if path.parent != backup_dir() or not path.is_file():
        raise FileNotFoundError("Copia de seguridad no encontrada")
    return path
