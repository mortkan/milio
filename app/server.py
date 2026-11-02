"""Aplicación FastAPI y montaje de routers/estáticos."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.backup import backup_scheduler
from app.config import BASE_DIR, ensure_directories, get_settings
from app.routes import backups, data, notes, quick_notes, routines, settings_routes
from app.services import seed_demo

logger = logging.getLogger("agenda")

STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = BASE_DIR / "templates" / "index.html"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_directories()

    if os.environ.get("AGENDA_SEED") == "1":
        from app.database import get_db_session
        with get_db_session() as db:
            result = seed_demo(db, get_settings())
            logger.info("Datos de ejemplo: %s", result)

    scheduler = asyncio.create_task(backup_scheduler())
    logger.info("Agenda lista. Documentación: /docs")
    yield

    scheduler.cancel()
    with suppress(asyncio.CancelledError):
        await scheduler


app = FastAPI(
    title="Agenda API",
    version=__version__,
    description=(
        "API REST de la agenda personal: notas por día, recurrencias, "
        "notas rápidas, ajustes, recordatorios, exportación y copias."
    ),
    lifespan=lifespan,
)

app.include_router(notes.router)
app.include_router(quick_notes.router)
app.include_router(settings_routes.router)
app.include_router(routines.router)
app.include_router(data.router)
app.include_router(backups.router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """Mensajes de validación compactos y serializables."""
    errors = [
        {
            "loc": [str(part) for part in error.get("loc", [])],
            "msg": error.get("msg", "Valor inválido"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": "Datos inválidos", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Error no controlado en %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
    )


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(
        INDEX_FILE,
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "version": __version__}
