"""Carga y persistencia de la configuración de la Agenda.

Prioridad de configuración:
1. Variables de entorno para valores de servidor (AGENDA_*).
2. Overrides guardados desde la interfaz en data/settings.json.
3. Valores por defecto de config.yaml.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.schemas import Settings

logger = logging.getLogger("agenda.config")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.yaml"
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"

_lock = threading.RLock()
_settings: Settings | None = None

_FALLBACK: dict[str, Any] = {
    "app_name": "Agenda",
    "language": "es",
    "first_day_of_week": 1,
    "date_format": "DD/MM/YYYY",
    "time_format": "24h",
    "timezone": "Europe/Madrid",
    "theme": "dark",
    "accent_color": "#7c3aed",
    "font_family": "system",
    "font_size": 16,
    "density": "comfortable",
    "default_view": "month",
    "show_week_numbers": False,
    "show_holidays": True,
    "show_completed": False,
    "show_month_previews": True,
    "show_quick_notes": True,
    "holidays": [],
    "categories": [
        {"id": "personal", "label": "Personal", "color": "#0ea5e9"},
        {"id": "work", "label": "Trabajo", "color": "#8b5cf6"},
        {"id": "health", "label": "Salud", "color": "#10b981"},
    ],
    "priorities": [
        {"id": "low", "label": "Baja", "color": "#94a3b8"},
        {"id": "medium", "label": "Media", "color": "#f59e0b"},
        {"id": "high", "label": "Alta", "color": "#ef4444"},
    ],
    "note_fields": {
        "time": True,
        "priority": True,
        "category": True,
        "color": True,
    },
    "shortcuts": {
        "new_note": "a",
        "quick_note": "n",
        "today": "t",
        "search": "/",
        "settings": ",",
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
        "database_path": "data/agenda.db",
        "backup_dir": "data/backups",
    },
    "backups": {"enabled": True, "frequency_hours": 24, "keep": 10},
}


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Devuelve un merge recursivo de diccionarios sin mutar las entradas."""
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _read_yaml() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        logger.warning("No existe %s; se usan valores por defecto", CONFIG_FILE)
        return copy.deepcopy(_FALLBACK)
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("config.yaml debe contener un objeto")
        return deep_merge(copy.deepcopy(_FALLBACK), data)
    except Exception as exc:  # pragma: no cover - error de arranque
        raise RuntimeError(f"No se pudo leer config.yaml: {exc}") from exc


def _read_overrides() -> dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        # Only keep non-server settings from overrides; server config
        # (host, port, database_path) comes from config.yaml and env vars.
        server_keys = {"host", "port", "database_path", "backup_dir"}
        filtered = {k: v for k, v in data.items() if k not in server_keys}
        return filtered if isinstance(filtered, dict) else {}
    except Exception as exc:
        logger.warning("settings.json inválido, se ignora: %s", exc)
        return {}


def _apply_env(raw: dict[str, Any]) -> dict[str, Any]:
    """Aplica variables de entorno de infraestructura (solo servidor)."""
    server = raw.setdefault("server", {})
    if host := os.environ.get("AGENDA_HOST"):
        server["host"] = host
    if port := os.environ.get("AGENDA_PORT"):
        try:
            server["port"] = int(port)
        except ValueError:
            logger.warning("AGENDA_PORT no es un número válido: %s", port)
    if db_path := os.environ.get("AGENDA_DB"):
        server["database_path"] = db_path
    if backup_dir := os.environ.get("AGENDA_BACKUP_DIR"):
        server["backup_dir"] = backup_dir
    return raw


def _validate(raw: dict[str, Any]) -> Settings:
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Configuración inválida: {exc}") from exc


def load_settings() -> Settings:
    """Relee config.yaml + overrides y refresca la caché en memoria."""
    global _settings
    with _lock:
        raw = deep_merge(_read_yaml(), _read_overrides())
        raw = _apply_env(raw)
        _settings = _validate(raw)
        return _settings


def get_settings() -> Settings:
    """Devuelve una copia de la configuración efectiva actual."""
    global _settings
    with _lock:
        if _settings is None:
            _settings = load_settings()
        return _settings.model_copy(deep=True)


def update_settings(patch: dict[str, Any]) -> Settings:
    """Valida y persiste un cambio parcial de ajustes.

    Lanza ValueError si el resultado final no es válido. El archivo se escribe
    de forma atómica para evitar configuraciones a medias.
    """
    global _settings
    with _lock:
        current = deep_merge(_read_yaml(), _read_overrides())
        candidate = _apply_env(deep_merge(current, patch))
        validated = _validate(candidate)

        overrides = deep_merge(_read_overrides(), patch)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(overrides, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        tmp.replace(SETTINGS_FILE)

        _settings = validated
        return validated


def reset_settings() -> Settings:
    """Elimina los overrides y vuelve a config.yaml."""
    global _settings
    with _lock:
        if SETTINGS_FILE.exists():
            SETTINGS_FILE.unlink()
        _settings = None
        return get_settings()


def resolve_path(value: str) -> Path:
    """Resuelve una ruta relativa al directorio raíz del proyecto."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def database_path() -> Path:
    return resolve_path(get_settings().server.database_path)


def backup_dir() -> Path:
    return resolve_path(get_settings().server.backup_dir)


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    database_path().parent.mkdir(parents=True, exist_ok=True)
    backup_dir().mkdir(parents=True, exist_ok=True)


def effective_dict() -> dict[str, Any]:
    """Configuración completa lista para serializar a JSON."""
    return get_settings().model_dump(mode="json")

def reset_settings() -> Settings:
    """Restablece todos los ajustes a sus valores por defecto de config.yaml."""
    global _settings
    _settings = None
    # Limpiar settings.json (poner valores por defecto)
    default_settings = {
        "app_name": "Agenda",
        "language": "es",
        "first_day_of_week": 1,
        "date_format": "DD/MM/YYYY",
        "time_format": "24h",
        "timezone": "Europe/Madrid",
        "theme": "dark",
        "accent_color": "#7c3aed",
        "font_family": "system",
        "font_size": 16,
        "density": "comfortable",
        "default_view": "month",
        "show_week_numbers": False,
        "show_holidays": True,
        "show_completed": False,
        "show_month_previews": True,
        "show_quick_notes": True,
        "holidays": [
            {"date": "01-01", "name": "Año Nuevo"},
            {"date": "12-25", "name": "Navidad"}
        ],
        "categories": [
            {"id": "personal", "label": "Personal", "color": "#0ea5e9"},
            {"id": "work", "label": "Trabajo", "color": "#8b5cf6"},
            {"id": "health", "label": "Salud", "color": "#10b981"},
            {"id": "study", "label": "Estudios", "color": "#f59e0b"}
        ],
        "priorities": [
            {"id": "low", "label": "Baja", "color": "#94a3b8"},
            {"id": "medium", "label": "Media", "color": "#f59e0b"},
            {"id": "high", "label": "Alta", "color": "#ef4444"}
        ],
        "note_fields": {"time": True, "priority": True, "category": True, "color": True},
        "shortcuts": {"new_note": "a", "quick_note": "n", "today": "t", "search": "/", "settings": ","},
        "server": {"host": "127.0.0.1", "port": 8000, "database_path": "data/agenda.db", "backup_dir": "data/backups"},
        "backups": {"enabled": True, "frequency_hours": 24, "keep": 10}
    }
    with SETTINGS_FILE.write_text(json.dumps(default_settings, ensure_ascii=False, indent=2)):
        pass
    _settings = load_settings()
    return _settings
