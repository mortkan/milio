"""Lógica de negocio: recurrencias, serialización, recordatorios y demo."""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Note, QuickNote, Routine, RoutineRecord, utcnow
from app.schemas import (
    NoteRead,
    OccurrenceRead,
    Recurrence,
    Settings,
)

MAX_OCCURRENCES = 10_000


# ---------------------------------------------------------------------------
# Fechas y recurrencias
# ---------------------------------------------------------------------------


def add_months(value: date, months: int) -> date:
    """Suma meses conservando el día o usando el último del mes destino."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:  # 29 de febrero en año no bisiesto
        return value.replace(year=value.year + years, day=28)


def iter_occurrences(
    base: date,
    recurrence: str,
    recurrence_end: date | None,
    start: date,
    end: date,
) -> Iterator[date]:
    """Genera las fechas de una nota dentro del rango [start, end]."""
    if start > end or recurrence_end is not None and recurrence_end < start:
        return

    if recurrence == Recurrence.none.value:
        if start <= base <= end:
            yield base
        return

    limit = end if recurrence_end is None else min(end, recurrence_end)
    if base > limit:
        return

    produced = 0
    if recurrence == Recurrence.daily.value:
        offset = max(0, (start - base).days)
        current = base + timedelta(days=offset)
        while current <= limit and produced < MAX_OCCURRENCES:
            if current >= start:
                yield current
                produced += 1
            current += timedelta(days=1)
    elif recurrence == Recurrence.weekly.value:
        offset = max(0, (start - base).days)
        weeks = offset // 7
        current = base + timedelta(weeks=weeks)
        if current < start:
            current += timedelta(weeks=1)
        while current <= limit and produced < MAX_OCCURRENCES:
            yield current
            produced += 1
            current += timedelta(weeks=1)
    elif recurrence == Recurrence.monthly.value:
        if start <= base:
            index = 0
        else:
            index = max(
                0,
                (start.year - base.year) * 12
                + (start.month - base.month)
                - 1,
            )
        current = add_months(base, index)
        while current < start:
            index += 1
            current = add_months(base, index)
        while current <= limit and produced < MAX_OCCURRENCES:
            yield current
            produced += 1
            index += 1
            current = add_months(base, index)
    elif recurrence == Recurrence.yearly.value:
        index = max(0, start.year - base.year - 1) if start > base else 0
        current = add_years(base, index)
        while current < start:
            index += 1
            current = add_years(base, index)
        while current <= limit and produced < MAX_OCCURRENCES:
            yield current
            produced += 1
            index += 1
            current = add_years(base, index)


# ---------------------------------------------------------------------------
# Serialización y ordenación
# ---------------------------------------------------------------------------


def build_occurrence(
    note: Note,
    occurrence_date: date,
    missed_count: int = 1,
) -> OccurrenceRead:
    data = NoteRead.model_validate(note).model_dump()
    data["occurrence_date"] = occurrence_date
    data["is_recurring"] = note.recurrence != Recurrence.none.value
    data["missed_count"] = missed_count
    return OccurrenceRead(**data)


def sort_occurrences(
    occurrences: Iterable[OccurrenceRead],
    settings: Settings,
) -> list[OccurrenceRead]:
    priority_order = {
        item.id: index for index, item in enumerate(settings.priorities)
    }

    def key(item: OccurrenceRead):
        return (
            1 if item.completed else 0,
            item.time or "99:99",
            priority_order.get(item.priority or "", 999),
            item.title.lower(),
            item.id,
        )

    return sorted(occurrences, key=key)


def calendar_days(
    notes: Iterable[Note],
    start: date,
    end: date,
    settings: Settings,
) -> dict[str, list[OccurrenceRead]]:
    days: dict[str, list[OccurrenceRead]] = {}
    for note in notes:
        for occurrence_date in iter_occurrences(
            note.note_date,
            note.recurrence,
            note.recurrence_end,
            start,
            end,
        ):
            days.setdefault(occurrence_date.isoformat(), []).append(
                build_occurrence(note, occurrence_date)
            )
    for key, items in days.items():
        days[key] = sort_occurrences(items, settings)
    return days


def build_reminders(
    db: Session,
    settings: Settings,
    today: date,
    lookback_days: int = 60,
) -> tuple[list[OccurrenceRead], list[OccurrenceRead]]:
    """Devuelve (notas de hoy, notas vencidas agrupadas por nota)."""
    start = today - timedelta(days=lookback_days)
    notes = (
        db.query(Note)
        .filter(Note.note_date <= today)
        .filter(
            or_(
                Note.note_date >= start,
                Note.recurrence != Recurrence.none.value,
            )
        )
        .all()
    )

    today_items: list[OccurrenceRead] = []
    overdue_by_note: dict[int, OccurrenceRead] = {}

    for note in notes:
        for occurrence_date in iter_occurrences(
            note.note_date,
            note.recurrence,
            note.recurrence_end,
            start,
            today,
        ):
            if occurrence_date == today:
                today_items.append(build_occurrence(note, occurrence_date))
            elif not note.completed:
                previous = overdue_by_note.get(note.id)
                if previous is None:
                    overdue_by_note[note.id] = build_occurrence(
                        note, occurrence_date
                    )
                else:
                    total = previous.missed_count + 1
                    if occurrence_date > previous.occurrence_date:
                        overdue_by_note[note.id] = build_occurrence(
                            note, occurrence_date, total
                        )
                    else:
                        previous.missed_count = total

    overdue = list(overdue_by_note.values())
    overdue.sort(
        key=lambda item: (item.occurrence_date, item.time or "99:99"),
        reverse=True,
    )
    return sort_occurrences(today_items, settings), overdue


# ---------------------------------------------------------------------------
# Normalización de notas
# ---------------------------------------------------------------------------


def derive_title(content: str, max_length: int = 80) -> str:
    """Obtiene un título legible a partir de la primera línea del contenido."""
    for line in content.splitlines():
        cleaned = re.sub(r"^[#>*\-\s]+", "", line).strip()
        if cleaned:
            return cleaned[:max_length].strip()
    return ""


def _db_has_type_column() -> bool:
    """Check if the 'type' column exists in the notes table."""
    from sqlalchemy import inspect
    from app.database import engine
    inspector = inspect(engine)
    columns = inspector.get_columns('notes')
    return any(c['name'] == 'type' for c in columns)


def _is_field_active(note: Note, field: str, settings: Any) -> bool:
    """Determina si un campo está activo para el tipo de la nota."""
    note_type = note.type or getattr(settings, 'note_types', {}).get('default', 'Tarea')
    type_config = getattr(settings, 'note_types', {}).get('types', {}).get(note_type, {})
    field_config = type_config.get('fields', {})
    # Si el tipo no tiene configuración de campos, todos los campos comunes están activos
    common_fields = {'title', 'content', 'note_date', 'time', 'category', 'color', 'priority', 'completed'}
    if field in common_fields:
        return field_config.get(field, True)
    return True


def apply_note_data(note: Note, data: dict[str, Any], settings: Any = None) -> None:
    """Aplica un patch ya validado, limpiando opcionales y derivando título."""
    # Determinar si la BD tiene la columna type
    has_type_col = _db_has_type_column()

    for field in (
        "title",
        "content",
        "note_date",
        "time",
        "category",
        "color",
        "priority",
        "completed",
        "recurrence",
        "recurrence_end",
        "status",
        "position",
        "type",  # Added type field
    ):
        if field in data:
            # Solo aplicar si el campo está activo para el tipo de nota
            # y si es 'type', solo si la BD tiene la columna
            if field == "type" and not has_type_col:
                # Almacenar como atributo puro (no columna de BD)
                note.type = data[field]
                continue
            if not _is_field_active(note, field, settings):
                continue
            value = data[field]
            if field in ("time", "category", "color", "priority"):
                value = value.strip() if isinstance(value, str) else value
                value = value or None
            setattr(note, field, value)

    if "recurrence" in data and note.recurrence == Recurrence.none.value:
        note.recurrence_end = None

    if not note.title and note.content:
        note.title = derive_title(note.content)

    if not note.title and not note.content:
        raise ValueError("La nota necesita un título o contenido")
    if (
        note.recurrence != Recurrence.none.value
        and note.recurrence_end is not None
        and note.recurrence_end < note.note_date
    ):
        raise ValueError("La fecha fin no puede ser anterior a la fecha de la nota")
    if note.recurrence == Recurrence.none.value:
        note.recurrence_end = None

    note.updated_at = utcnow()


# ---------------------------------------------------------------------------
# Exportación / demo
# ---------------------------------------------------------------------------


def note_dict(note: Note) -> dict[str, Any]:
    return NoteRead.model_validate(note).model_dump(mode="json")


def export_payload(db: Session, settings: Settings) -> dict[str, Any]:
    notes = db.query(Note).order_by(Note.note_date, Note.id).all()
    quick_notes = db.query(QuickNote).order_by(QuickNote.created_at).all()
    routines = db.query(Routine).all()
    routine_records = (
        db.query(RoutineRecord)
        .filter(RoutineRecord.record_date >= date.today())
        .order_by(RoutineRecord.record_date.desc())
        .all()
    )
    return {
        "app": "agenda",
        "version": 1,
        "exported_at": datetime.now(ZoneInfo(settings.timezone)).isoformat(),
        "settings": settings.model_dump(mode="json"),
        "notes": [note_dict(note) for note in notes],
        "quick_notes": [
            {
                "id": item.id,
                "content": item.content,
                "created_at": item.created_at.isoformat(),
            }
            for item in quick_notes
        ],
        "routines": [routine_dict(r) for r in routines],
        "routine_records": [
            {
                "id": item.id,
                "routine_id": item.routine_id,
                "date": item.date.isoformat(),
                "completed": item.completed,
            }
            for item in routine_records
        ],
    }


def get_today_routine_records(db: Session) -> dict[int, RoutineRecord]:
    """Obtiene los registros de rutinas de hoy, claveados por routine_id."""
    from app.models import RoutineRecord
    
    today = date.today()
    records = (
        db.query(RoutineRecord)
        .filter(RoutineRecord.record_date == today)
        .all()
    )
    return {record.routine_id: record for record in records}


def get_routine_streak(routine_id: int, db: Session) -> dict[str, any]:
    """Calcula la racha y porcentaje de cumplimiento de una rutina."""
    from app.models import RoutineRecord
    
    # Obtener todos los registros de esta rutina ordenados por fecha
    records = (
        db.query(RoutineRecord)
        .filter(RoutineRecord.routine_id == routine_id)
        .order_by(RoutineRecord.record_date.asc())
        .all()
    )
    
    if not records:
        return {"streak": 0, "weekly_percentage": 0, "monthly_percentage": 0, "total_days": 0}
    
    # Calcular racha actual (días consecutivos al final)
    today = date.today()
    streak = 0
    # Verificar días consecutivos terminando en hoy o ayer
    consecutive_days = 0
    for i, record in enumerate(reversed(records)):
        check_date = today - timedelta(days=i)
        if record.date == check_date and record.completed:
            consecutive_days += 1
        else:
            break
    streak = consecutive_days
    
    # Calcular porcentaje de cumplimiento semanal (últimos 7 días)
    week_start = today - timedelta(days=6)  # Inclusive: 7 days
    week_records = [r for r in records if week_start <= r.date <= today]
    week_completed = sum(1 for r in week_records if r.completed)
    weekly_percentage = (week_completed / max(len(week_records), 1)) * 100
    
    # Calcular porcentaje de cumplimiento mensual (últimos 30 días)
    month_start = today - timedelta(days=29)  # Inclusive: 30 days
    month_records = [r for r in records if month_start <= r.date <= today]
    month_completed = sum(1 for r in month_records if r.completed)
    monthly_percentage = (month_completed / max(len(month_records), 1)) * 100
    
    # Total de días en el registro
    total_days = len(records)
    
    return {
        "streak": streak,
        "weekly_percentage": round(weekly_percentage, 1),
        "monthly_percentage": round(monthly_percentage, 1),
        "total_days": total_days,
    }


def routine_dict(routine: Routine) -> dict[str, Any]:
    return {
        "id": routine.id,
        "title": routine.title,
        "description": routine.description,
        "schedule": routine.schedule,
        "color": routine.color,
        "icon": routine.icon,
        "checklist_template": routine.checklist_template,
    }


def mark_routine_complete(routine_id: int, db: Session, notes: str = "") -> RoutineRecord:
    """Marca una rutina como completada para hoy."""
    from app.models import RoutineRecord
    
    # Obtener o crear el registro de hoy
    today = date.today()
    record = db.query(RoutineRecord).filter(
        RoutineRecord.routine_id == routine_id,
        RoutineRecord.record_date == today,
    ).first()
    
    if record is None:
        record = RoutineRecord(routine_id=routine_id, date=today)
        db.add(record)
    
    record.completed = True
    record.notes = notes
    record.completed_at = utcnow()
    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Rutinas y Hábitos
# ---------------------------------------------------------------------------


def get_routine_templates() -> dict[str, Any]:
    """Obtiene plantillas de rutinas predefinidas."""
    return {
        "morning_journal": {
            "title": "Inicio de jornada",
            "schedule": "daily",
            "icon": "🌅",
            "checklist": [
                "Revisar correo y PRs",
                "Planificar las 3 prioridades del día",
                "Revisar calendario",
                "Activar modo enfoque"
            ]
        },
        "evening_journal": {
            "title": "Cierre de jornada",
            "schedule": "daily",
            "icon": "🌆",
            "checklist": [
                "Revisar qué se completó hoy",
                "Mover tareas pendientes al día siguiente",
                "Actualizar el tablero",
                "Desconectar y descansar"
            ]
        },
        "weekly_review": {
            "title": "Revisión semanal",
            "schedule": "weekly",
            "icon": "📋",
            "checklist": [
                "¿Qué completé esta semana?",
                "¿Qué quedó pendiente?",
                "Objetivos para la próxima semana",
                "Revisar proyectos y áreas"
            ]
        },
        "exercise": {
            "title": "Ejercicio físico",
            "schedule": "daily",
            "icon": "💪",
            "checklist": [
                "Calentamiento",
                "Rutina principal",
                "Estiramientos"
            ]
        },
        "reading": {
            "title": "Lectura",
            "schedule": "daily",
            "icon": "📚",
            "checklist": [
                "Capítulo o sección asignada",
                "Notas y resaltados",
                "Reflexión del día"
            ]
        }
    }


def get_checklist_items(template: str) -> list[str]:
    """Obtiene los ítems de checklist de una plantilla."""
    templates = get_routine_templates()
    if template in templates:
        return templates[template]["checklist"]
    return []


def seed_demo(db: Session, settings: Settings, reset: bool = False) -> dict[str, Any]:
    """Crea datos de ejemplo relativos a hoy. No duplica si ya hay notas."""
    if reset:
        db.query(Note).delete()
        db.query(QuickNote).delete()
        db.commit()

    if db.query(Note).count() > 0:
        return {"created_notes": 0, "created_quick_notes": 0, "skipped": True}

    today = datetime.now(ZoneInfo(settings.timezone)).date()
    category_ids = [item.id for item in settings.categories]
    priority_ids = [item.id for item in settings.priorities]

    def category(index: int) -> str | None:
        return category_ids[index] if len(category_ids) > index else None

    def priority(index: int) -> str | None:
        return priority_ids[index] if len(priority_ids) > index else None

    samples = [
        Note(
            title="Revisión semanal",
            content=(
                "## Objetivos de la semana\n\n"
                "- Revisar el correo pendiente\n"
                "- Preparar la reunión del **miércoles**\n"
                "- Actualizar el tablero del proyecto\n\n"
                "> Dedicar 30 minutos sin interrupciones."
            ),
            note_date=today,
            time="09:30",
            category=category(1),
            priority=priority(2),
            color="#8b5cf6",
        ),
        Note(
            title="Llamar a Ana",
            content="Confirmar la cena del sábado y reservar mesa.",
            note_date=today,
            time="18:00",
            category=category(0),
            priority=priority(1),
        ),
        Note(
            title="Comprar café",
            content="Grano, molienda media. Aprovechar para comprar fruta.",
            note_date=today,
            category=category(2),
            priority=priority(0),
        ),
        Note(
            title="Enviar informe mensual",
            content="Incluir métricas de uso y próximos pasos.",
            note_date=today - timedelta(days=2),
            time="12:00",
            category=category(1),
            priority=priority(2),
        ),
        Note(
            title="Cita con el dentista",
            content="Llevar el informe de la última revisión.",
            note_date=today + timedelta(days=1),
            time="16:45",
            category=category(2),
            priority=priority(1),
        ),
        Note(
            title="Cumpleaños de Luis",
            content="Llamarle y preparar una tarjeta.",
            note_date=today + timedelta(days=3),
            category=category(0),
            priority=priority(0),
            recurrence=Recurrence.yearly.value,
        ),
        Note(
            title="Planificar la semana",
            content=(
                "1. Elegir tres prioridades\n"
                "2. Reservar bloques de concentración\n"
                "3. Revisar la agenda el viernes"
            ),
            note_date=today + timedelta(days=7),
            time="08:30",
            category=category(1),
            priority=priority(1),
            recurrence=Recurrence.weekly.value,
        ),
        Note(
            title="Leer capítulo 3",
            content="Subrayar las ideas principales y anotar dudas.",
            note_date=today - timedelta(days=1),
            category=category(3),
            priority=priority(0),
            completed=True,
        ),
    ]
    db.add_all(samples)
    quick = [
        QuickNote(content="Idea: probar una rutina de mañana más corta"),
        QuickNote(content="Buscar un regalo para Marta"),
    ]
    db.add_all(quick)
    db.commit()
    return {
        "created_notes": len(samples),
        "created_quick_notes": len(quick),
        "skipped": False,
    }
