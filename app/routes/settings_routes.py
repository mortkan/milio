"""Ajustes de la aplicación y metadatos para el frontend."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from app import __version__
from app.config import BASE_DIR, get_settings, reset_settings, update_settings
from app.schemas import Settings, SettingsUpdate

router = APIRouter(prefix="/api", tags=["settings"])

I18N_DIR = BASE_DIR / "static" / "i18n"

COMMON_TIMEZONES = [
    "UTC",
    "Europe/Madrid",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Mexico_City",
    "America/Bogota",
    "America/Lima",
    "America/Santiago",
    "America/Sao_Paulo",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Kolkata",
    "Australia/Sydney",
]


def available_languages() -> list[dict[str, str]]:
    """Descubre los idiomas a partir de static/i18n/*.json."""
    languages: list[dict[str, str]] = []
    if not I18N_DIR.exists():
        return languages
    for path in sorted(I18N_DIR.glob("*.json")):
        code = path.stem
        name = code
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            root = data.get("root", {}) if isinstance(data, dict) else {}
            meta = data.get("_meta") or root.get("_meta", {})
            name = str(meta.get("name", code))
        except Exception:
            pass
        languages.append({"code": code, "name": name})
    return languages


@router.get("/settings", response_model=Settings)
def read_settings():
    return get_settings()


@router.put("/settings", response_model=Settings)
def write_settings(payload: SettingsUpdate):
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        return get_settings()
    try:
        return update_settings(patch)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/settings/reset", response_model=Settings)
def restore_default_settings():
    try:
        return reset_settings()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/meta")
def meta():
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    timezones = sorted(set(COMMON_TIMEZONES + [settings.timezone]))
    return {
        "version": __version__,
        "today": today.isoformat(),
        "languages": available_languages(),
        "timezones": timezones,
        "timezone": settings.timezone,
    }
