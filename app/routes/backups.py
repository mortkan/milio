"""Listado, creación y descarga de copias de seguridad."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.backup import create_backup, list_backups, safe_backup_path

router = APIRouter(prefix="/api", tags=["backups"])


@router.get("/backups")
def get_backups():
    return list_backups()


@router.post("/backups", status_code=status.HTTP_201_CREATED)
def run_backup():
    try:
        return create_backup(reason="manual")
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"No se pudo crear la copia: {exc}") from exc


@router.get("/backups/{name}")
def download_backup(name: str):
    try:
        path = safe_backup_path(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, filename=path.name, media_type="application/x-sqlite3")
