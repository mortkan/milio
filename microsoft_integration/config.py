"""Configuration for Microsoft 365 integration.

Reads from environment variables (with .env.microsoft support).
All Microsoft-specific settings are prefixed with MICROSOFT_.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MicrosoftSettings(BaseSettings):
    """All configuration for the Microsoft integration service."""

    model_config = SettingsConfigDict(
        env_file=".env.microsoft",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Feature flag -------------------------------------------------------
    microsoft_enabled: bool = Field(default=True, alias="MICROSOFT_ENABLED")

    # ---- Entra ID / MSAL ----------------------------------------------------
    microsoft_client_id: str = Field(default="", alias="MICROSOFT_CLIENT_ID")
    microsoft_tenant: str = Field(default="common", alias="MICROSOFT_TENANT")

    # ---- Graph --------------------------------------------------------------
    microsoft_graph_base_url: str = Field(
        default="https://graph.microsoft.com/v1.0",
        alias="MICROSOFT_GRAPH_BASE_URL",
    )

    # ---- Token encryption ---------------------------------------------------
    microsoft_token_encryption_key: str = Field(
        default="", alias="MICROSOFT_TOKEN_ENCRYPTION_KEY"
    )

    # ---- Sync behaviour -----------------------------------------------------
    microsoft_sync_interval_seconds: int = Field(
        default=300, alias="MICROSOFT_SYNC_INTERVAL_SECONDS"
    )
    microsoft_sync_lookback_days: int = Field(
        default=90, alias="MICROSOFT_SYNC_LOOKBACK_DAYS"
    )
    microsoft_sync_lookahead_days: int = Field(
        default=365, alias="MICROSOFT_SYNC_LOOKAHEAD_DAYS"
    )

    # ---- Default resource names ---------------------------------------------
    microsoft_default_calendar_name: str = Field(
        default="Milo", alias="MICROSOFT_DEFAULT_CALENDAR_NAME"
    )
    microsoft_default_todo_list_name: str = Field(
        default="Milo", alias="MICROSOFT_DEFAULT_TODO_LIST_NAME"
    )

    # ---- Service ------------------------------------------------------------
    microsoft_service_host: str = Field(
        default="0.0.0.0", alias="MICROSOFT_SERVICE_HOST"
    )
    microsoft_service_port: int = Field(
        default=8010, alias="MICROSOFT_SERVICE_PORT"
    )

    # ---- Database (shared with Milo) ----------------------------------------
    db_host: str = Field(default="127.0.0.1", alias="DB_HOST")
    db_port: int = Field(default=3306, alias="DB_PORT")
    db_name: str = Field(default="milo", alias="DB_NAME")
    db_user: str = Field(default="milo_app", alias="DB_USER")
    db_password: str = Field(default="", alias="DB_PASSWORD")

    # ---- Webhooks -----------------------------------------------------------
    microsoft_webhook_enabled: bool = Field(
        default=False, alias="MICROSOFT_WEBHOOK_ENABLED"
    )
    microsoft_webhook_public_url: str = Field(
        default="", alias="MICROSOFT_WEBHOOK_PUBLIC_URL"
    )

    # ---- Timezone -----------------------------------------------------------
    microsoft_timezone: str = Field(
        default="Europe/Madrid", alias="MICROSOFT_TIMEZONE"
    )

    # ---- OAuth scopes -------------------------------------------------------
    microsoft_scopes: List[str] = Field(
        default=[
            "User.Read",
            "Calendars.ReadWrite",
            "Tasks.ReadWrite",
            "offline_access",
        ],
        alias="MICROSOFT_SCOPES",
    )

    # ---- PKCE / Auth code flow (future) ------------------------------------
    microsoft_redirect_uri: str = Field(
        default="http://localhost:8010/api/microsoft/auth/callback",
        alias="MICROSOFT_REDIRECT_URI",
    )

    @field_validator("microsoft_token_encryption_key", mode="before")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        # Allow empty — startup will warn
        return v

    @property
    def encryption_key_valid(self) -> bool:
        """Returns True if a non-empty encryption key is present."""
        return bool(self.microsoft_token_encryption_key.strip())

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def authority(self) -> str:
        tenant = self.microsoft_tenant or "common"
        return f"https://login.microsoftonline.com/{tenant}"

    @property
    def client_configured(self) -> bool:
        return bool(self.microsoft_client_id.strip())


def _load_settings() -> MicrosoftSettings:
    """Load settings, looking for .env.microsoft in common locations."""
    # Try several paths: cwd, parent of this file, project root
    env_candidates: list[Path] = [
        Path.cwd() / ".env.microsoft",
        Path(__file__).parent / ".env.microsoft",
        Path(__file__).parent.parent / ".env.microsoft",
    ]
    for candidate in env_candidates:
        if candidate.exists():
            os.environ.setdefault("ENV_FILE", str(candidate))
            break

    return MicrosoftSettings()


_settings: Optional[MicrosoftSettings] = None


def get_settings() -> MicrosoftSettings:
    global _settings
    if _settings is None:
        _settings = _load_settings()
    return _settings


def reload_settings() -> MicrosoftSettings:
    global _settings
    _settings = _load_settings()
    return _settings
