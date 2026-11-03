"""Microsoft 365 Integration — FastAPI application entry point.

Runs as an independent service on port 8010 (configurable via MICROSOFT_SERVICE_PORT).
Shares the same MariaDB instance as Milo but uses only ms_* tables.

Usage:
    python -m microsoft_integration.main
    uvicorn microsoft_integration.main:app --host 0.0.0.0 --port 8010
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Load .env.microsoft early
try:
    from dotenv import load_dotenv
    for candidate in [
        Path.cwd() / ".env.microsoft",
        Path(__file__).parent / ".env.microsoft",
        Path(__file__).parent.parent / ".env.microsoft",
    ]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break
except ImportError:
    pass

from microsoft_integration.config import MicrosoftSettings, get_settings
from microsoft_integration.logging_config import configure_logging

configure_logging()

logger = logging.getLogger("microsoft.main")

# ---------------------------------------------------------------------------
# Singletons (set during startup)
# ---------------------------------------------------------------------------

_settings: Optional[MicrosoftSettings] = None
_encryptor = None
_device_flow_manager = None
_sync_config = None


def get_settings() -> MicrosoftSettings:
    global _settings
    if _settings is None:
        from microsoft_integration.config import get_settings as _gs
        _settings = _gs()
    return _settings


def get_encryptor():
    global _encryptor
    if _encryptor is None:
        from microsoft_integration.auth.encryption import TokenEncryptor
        settings = get_settings()
        _encryptor = TokenEncryptor(settings.microsoft_token_encryption_key)
    return _encryptor


def get_device_flow_manager():
    global _device_flow_manager
    return _device_flow_manager


def get_sync_config():
    global _sync_config
    return _sync_config


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="Milo — Microsoft 365 Integration",
        version="1.0.0",
        description=(
            "Bidirectional synchronization between Milo and Microsoft 365 "
            "(Outlook Calendar + Microsoft To Do). "
            "Runs as an independent service on port 8010."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ---- Static files and templates ----------------------------------------
    static_dir = Path(__file__).parent / "ui" / "static"
    templates_dir = Path(__file__).parent / "ui" / "templates"

    if static_dir.exists():
        app.mount("/static/microsoft", StaticFiles(directory=str(static_dir)), name="ms_static")

    _templates = Jinja2Templates(directory=str(templates_dir)) if templates_dir.exists() else None

    # ---- Routers -----------------------------------------------------------
    from microsoft_integration.api.auth_routes import router as auth_router
    from microsoft_integration.api.account_routes import router as account_router
    from microsoft_integration.api.sync_routes import router as sync_router
    from microsoft_integration.api.config_routes import router as config_router
    from microsoft_integration.api.conflict_routes import router as conflict_router
    from microsoft_integration.api.webhook_routes import router as webhook_router
    from microsoft_integration.api.health_routes import router as health_router

    for r in [
        health_router,
        auth_router,
        account_router,
        sync_router,
        config_router,
        conflict_router,
        webhook_router,
    ]:
        app.include_router(r)

    # ---- UI routes ---------------------------------------------------------
    if _templates:
        from fastapi import Request

        @app.get("/microsoft", include_in_schema=False)
        async def microsoft_ui(request: Request):
            return _templates.TemplateResponse(
                "microsoft.html", {"request": request}
            )

        @app.get("/microsoft/accounts", include_in_schema=False)
        async def accounts_ui(request: Request):
            return _templates.TemplateResponse(
                "accounts.html", {"request": request}
            )

        @app.get("/microsoft/sync", include_in_schema=False)
        async def sync_ui(request: Request):
            return _templates.TemplateResponse(
                "sync.html", {"request": request}
            )

        @app.get("/microsoft/conflicts", include_in_schema=False)
        async def conflicts_ui(request: Request):
            return _templates.TemplateResponse(
                "conflicts.html", {"request": request}
            )

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/microsoft")

    # ---- Startup / shutdown ------------------------------------------------
    @app.on_event("startup")
    async def on_startup():
        global _settings, _encryptor, _device_flow_manager, _sync_config

        settings = get_settings()
        logger.info(
            "Microsoft Integration service starting (port=%d)",
            settings.microsoft_service_port,
        )

        if not settings.microsoft_enabled:
            logger.warning("MICROSOFT_ENABLED=false — integration disabled")
            return

        if not settings.encryption_key_valid:
            logger.error(
                "MICROSOFT_TOKEN_ENCRYPTION_KEY is not set. "
                "Sync and authentication are DISABLED until a valid key is provided."
            )
            return

        if not settings.client_configured:
            logger.error(
                "MICROSOFT_CLIENT_ID is not configured. "
                "Authentication is DISABLED until a client ID is provided."
            )
            return

        # Apply Microsoft schema
        try:
            from microsoft_integration.scripts.apply_microsoft_schema import apply_schema
            apply_schema()
        except Exception as exc:
            logger.error("Failed to apply Microsoft schema: %s", exc)
            raise

        # Initialize singletons
        from microsoft_integration.auth.encryption import TokenEncryptor
        from microsoft_integration.auth.device_flow import DeviceFlowManager
        from microsoft_integration.database import get_db_session
        from microsoft_integration.sync.engine import SyncEngineConfig

        _encryptor = TokenEncryptor(settings.microsoft_token_encryption_key)

        _device_flow_manager = DeviceFlowManager(
            settings=settings,
            encryptor=_encryptor,
            db_session_factory=lambda: get_db_session().__enter__(),
        )

        _sync_config = SyncEngineConfig(settings=settings, encryptor=_encryptor)

        # Start scheduler
        from microsoft_integration.sync.scheduler import start_scheduler
        start_scheduler(_sync_config)

        logger.info("Microsoft Integration service ready.")

    @app.on_event("shutdown")
    async def on_shutdown():
        from microsoft_integration.sync.scheduler import stop_scheduler
        stop_scheduler()
        logger.info("Microsoft Integration service stopped.")

    return app


app = create_app()


# ---------------------------------------------------------------------------
# Standalone startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "microsoft_integration.main:app",
        host=settings.microsoft_service_host,
        port=settings.microsoft_service_port,
        reload="--reload" in sys.argv,
        log_level="info",
    )
