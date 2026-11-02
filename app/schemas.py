"""Modelos de validación de la API (Pydantic v2)."""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Tipos compartidos
# ---------------------------------------------------------------------------

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
HOLIDAY_RE = re.compile(r"^(?:\d{2}-\d{2}|\d{4}-\d{2}-\d{2})$")

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ShortId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class Recurrence(str, Enum):
    none = "none"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


# ---------------------------------------------------------------------------
# Ajustes
# ---------------------------------------------------------------------------


class CategoryItem(BaseModel):
    id: ShortId
    label: NonEmptyStr = Field(max_length=50)
    color: str = "#64748b"

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not HEX_COLOR.match(value):
            raise ValueError("El color debe tener el formato #RRGGBB")
        return value.lower()


class PriorityItem(BaseModel):
    id: ShortId
    label: NonEmptyStr = Field(max_length=50)
    color: str = "#64748b"

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not HEX_COLOR.match(value):
            raise ValueError("El color debe tener el formato #RRGGBB")
        return value.lower()


class HolidayItem(BaseModel):
    date: str
    name: NonEmptyStr = Field(max_length=80)

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        if not HOLIDAY_RE.match(value):
            raise ValueError("Formato de festivo inválido (MM-DD o YYYY-MM-DD)")
        if len(value) == 10:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Fecha de festivo inválida") from exc
        else:
            month, day = (int(part) for part in value.split("-"))
            if not 1 <= month <= 12 or not 1 <= day <= 31:
                raise ValueError("Fecha de festivo inválida")
        return value


class NoteFieldSettings(BaseModel):
    time: bool = True
    priority: bool = True
    category: bool = True
    color: bool = True


class ShortcutSettings(BaseModel):
    new_note: str = "a"
    quick_note: str = "n"
    today: str = "t"
    search: str = "/"
    settings: str = ","

    @field_validator("*")
    @classmethod
    def validate_shortcut(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 30:
            raise ValueError("Atajo inválido")
        return value


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_path: str = "data/agenda.db"
    backup_dir: str = "data/backups"

    @field_validator("host", "database_path", "backup_dir")
    @classmethod
    def validate_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Este campo no puede estar vacío")
        return value


class BackupSettings(BaseModel):
    enabled: bool = True
    frequency_hours: int = Field(default=24, ge=1, le=720)
    keep: int = Field(default=10, ge=1, le=200)


class Settings(BaseModel):
    """Configuración completa de la aplicación."""

    model_config = ConfigDict(extra="ignore")

    app_name: str = Field(default="Agenda", min_length=1, max_length=60)
    language: str = "es"
    first_day_of_week: int = Field(default=1, ge=0, le=6)
    date_format: Literal[
        "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD", "DD.MM.YYYY"
    ] = "DD/MM/YYYY"
    time_format: Literal["24h", "12h"] = "24h"
    timezone: str = "Europe/Madrid"

    theme: Literal["auto", "light", "dark"] = "dark"
    accent_color: str = "#7c3aed"
    font_family: Literal["system", "sans", "serif", "mono"] = "system"
    font_size: int = Field(default=16, ge=12, le=22)
    density: Literal["comfortable", "compact"] = "comfortable"

    default_view: Literal["month", "week", "day"] = "month"
    show_week_numbers: bool = False
    show_holidays: bool = True
    show_completed: bool = False
    show_month_previews: bool = True
    show_quick_notes: bool = True
    board_columns: list[dict] = Field(default_factory=lambda: [
        {"id": "bandeja", "label": "Bandeja", "color": "#64748b"},
        {"id": "por-hacer", "label": "Por hacer", "color": "#8b5cf6"},
        {"id": "en-curso", "label": "En curso", "color": "#10b981"},
        {"id": "hecho", "label": "Hecho", "color": "#f59e0b"},
    ])

    holidays: list[HolidayItem] = Field(default_factory=list)
    categories: list[CategoryItem] = Field(min_length=1)
    priorities: list[PriorityItem] = Field(min_length=1)
    note_fields: NoteFieldSettings = Field(default_factory=NoteFieldSettings)
    shortcuts: ShortcutSettings = Field(default_factory=ShortcutSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    backups: BackupSettings = Field(default_factory=BackupSettings)

    @field_validator("accent_color")
    @classmethod
    def validate_accent(cls, value: str) -> str:
        if not HEX_COLOR.match(value):
            raise ValueError("El color de acento debe tener formato #RRGGBB")
        return value.lower()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Zona horaria desconocida: {value}") from exc
        return value

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.match(r"^[a-z]{2}(?:-[a-z]{2})?$", value):
            raise ValueError("Idioma inválido")
        return value

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "Settings":
        for items, label in (
            (self.categories, "categorías"),
            (self.priorities, "prioridades"),
        ):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Hay identificadores duplicados en {label}")
        shortcut_values = list(self.shortcuts.model_dump().values())
        if len(shortcut_values) != len(set(shortcut_values)):
            raise ValueError("Los atajos de teclado deben ser únicos")
        return self


class SettingsUpdate(BaseModel):
    """Actualización parcial de ajustes (merge profundo)."""

    model_config = ConfigDict(extra="ignore")

    app_name: str | None = Field(default=None, min_length=1, max_length=60)
    language: str | None = None
    first_day_of_week: int | None = Field(default=None, ge=0, le=6)
    date_format: Literal[
        "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD", "DD.MM.YYYY"
    ] | None = None
    time_format: Literal["24h", "12h"] | None = None
    timezone: str | None = None

    theme: Literal["auto", "light", "dark"] | None = None
    accent_color: str | None = None
    font_family: Literal["system", "sans", "serif", "mono"] | None = None
    font_size: int | None = Field(default=None, ge=12, le=22)
    density: Literal["comfortable", "compact"] | None = None

    default_view: Literal["month", "week", "day"] | None = None
    show_week_numbers: bool | None = None
    show_holidays: bool | None = None
    show_completed: bool | None = None
    show_month_previews: bool | None = None
    show_quick_notes: bool | None = None

    holidays: list[HolidayItem] | None = None
    categories: list[CategoryItem] | None = None
    priorities: list[PriorityItem] | None = None
    note_fields: NoteFieldSettings | None = None
    shortcuts: ShortcutSettings | None = None
    server: ServerSettings | None = None
    backups: BackupSettings | None = None


# ---------------------------------------------------------------------------
# Notas
# ---------------------------------------------------------------------------


class NoteBase(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=50_000)
    note_date: date
    time: str | None = None
    category: str | None = Field(default=None, max_length=50)
    color: str | None = None
    priority: str | None = Field(default=None, max_length=30)
    completed: bool = False
    recurrence: Recurrence = Recurrence.none
    recurrence_end: date | None = None
    status: str | None = None
    position: int | None = None

    @field_validator("title", "content")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not TIME_RE.match(value):
            raise ValueError("La hora debe tener formato HH:MM")
        return value

    @field_validator("category", "priority")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not HEX_COLOR.match(value):
            raise ValueError("El color debe tener formato #RRGGBB")
        return value.lower()

    @model_validator(mode="after")
    def validate_recurrence(self) -> "NoteBase":
        if self.recurrence == Recurrence.none and self.recurrence_end is not None:
            raise ValueError("Una nota sin repetición no puede tener fecha fin")
        if (
            self.recurrence != Recurrence.none
            and self.recurrence_end is not None
            and self.recurrence_end < self.note_date
        ):
            raise ValueError("La fecha fin no puede ser anterior a la fecha de la nota")
        return self


class NoteCreate(NoteBase):
    @model_validator(mode="after")
    def require_title_or_content(self) -> "NoteCreate":
        if not self.title and not self.content:
            raise ValueError("La nota necesita un título o contenido")
        return self


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=50_000)
    note_date: date | None = None
    time: str | None = None
    category: str | None = Field(default=None, max_length=50)
    color: str | None = None
    priority: str | None = Field(default=None, max_length=30)
    completed: bool | None = None
    recurrence: Recurrence | None = None
    recurrence_end: date | None = None
    status: str | None = None
    position: int | None = None

    @field_validator("title", "content")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not TIME_RE.match(value):
            raise ValueError("La hora debe tener formato HH:MM")
        return value

    @field_validator("category", "priority")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not HEX_COLOR.match(value):
            raise ValueError("El color debe tener formato #RRGGBB")
        return value.lower()


class NoteRead(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class OccurrenceRead(NoteRead):
    occurrence_date: date
    is_recurring: bool = False
    missed_count: int = 1


class CalendarResponse(BaseModel):
    start: date
    end: date
    days: dict[str, list[OccurrenceRead]]


class RemindersResponse(BaseModel):
    date: date
    timezone: str
    today: list[OccurrenceRead]
    overdue: list[OccurrenceRead]


# ---------------------------------------------------------------------------
# Notas rápidas
# ---------------------------------------------------------------------------


class QuickNoteCreate(BaseModel):
    content: NonEmptyStr = Field(max_length=5_000)


class QuickNoteUpdate(BaseModel):
    content: NonEmptyStr = Field(max_length=5_000)


class QuickNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime


class QuickNoteAssign(BaseModel):
    note_date: date
    category: str | None = Field(default=None, max_length=50)
    priority: str | None = Field(default=None, max_length=30)


# ---------------------------------------------------------------------------
# Importación
# ---------------------------------------------------------------------------


class ImportNote(NoteCreate):
    pass


class ImportQuickNote(QuickNoteCreate):
    pass


class ImportPayload(BaseModel):
    app: str | None = None
    version: int | None = None
    exported_at: str | None = None
    notes: list[ImportNote] = Field(default_factory=list)
    quick_notes: list[ImportQuickNote] = Field(default_factory=list)
    settings: dict | None = None


class ImportResult(BaseModel):
    notes_imported: int
    quick_notes_imported: int
    mode: Literal["merge", "replace"]
    settings_imported: bool


class BulkResult(BaseModel):
    deleted_notes: int
    deleted_quick_notes: int
