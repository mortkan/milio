"""CRUD de notas, calendario y recordatorios."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Any
from pydantic import BaseModel, Field

from app.config import get_settings
from app.database import get_db
from app.models import Note
from app.schemas import (
    CalendarResponse,
    NoteCreate,
    NoteRead,
    NoteUpdate,
    Recurrence,
    RemindersResponse,
    Settings,
)
from app.services import apply_note_data, build_reminders, calendar_days

router = APIRouter(prefix="/api", tags=["notes"])


def _sort_notes(notes: list[Note], settings: Settings) -> list[Note]:
    priority_order = {
        item.id: index for index, item in enumerate(settings.priorities)
    }
    return sorted(
        notes,
        key=lambda note: (
            -note.note_date.toordinal(),
            note.time or "99:99",
            priority_order.get(note.priority or "", 999),
            note.id,
        ),
    )


@router.get("/notes", response_model=list[NoteRead])
def list_notes(
    start: date | None = None,
    end: date | None = None,
    day: date | None = None,
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=50),
    priority: str | None = Query(default=None, max_length=30),
    completed: bool | None = None,
    recurring: bool | None = None,
    item_type: str | None = Query(default=None, max_length=20),
    area: str | None = Query(default=None, max_length=50),
    project: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=300, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Lista las notas base (sin expandir repeticiones)."""
    query = db.query(Note)
    if day is not None:
        query = query.filter(Note.note_date == day)
    if start is not None:
        query = query.filter(Note.note_date >= start)
    if end is not None:
        query = query.filter(Note.note_date <= end)
    if start and end and start > end:
        raise HTTPException(422, "El rango de fechas no es válido")
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(Note.title.ilike(pattern), Note.content.ilike(pattern))
        )
    if category:
        query = query.filter(Note.category == category)
    if priority:
        query = query.filter(Note.priority == priority)
    if completed is not None:
        query = query.filter(Note.completed.is_(completed))
    if recurring is not None:
        if recurring:
            query = query.filter(Note.recurrence != Recurrence.none.value)
        else:
            query = query.filter(Note.recurrence == Recurrence.none.value)
    if item_type and item_type in ("note", "task", "event"):
        query = query.filter(Note.item_type == item_type)
    if area:
        query = query.filter(Note.category == area)
    if project:
        query = query.filter(Note.category == project)

    notes = query.all()
    notes = _sort_notes(notes, settings)
    return notes[offset : offset + limit]


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Notas expandidas por día para un rango (máximo 400 días)."""
    if start > end:
        raise HTTPException(422, "La fecha inicial debe ser anterior a la final")
    if (end - start).days > 400:
        raise HTTPException(422, "El rango máximo del calendario es de 400 días")

    notes = (
        db.query(Note)
        .filter(Note.note_date <= end)
        .filter(
            or_(
                Note.note_date >= start,
                Note.recurrence != Recurrence.none.value,
            )
        )
        .all()
    )
    days = calendar_days(notes, start, end, settings)
    return CalendarResponse(start=start, end=end, days=days)


@router.get("/reminders", response_model=RemindersResponse)
def get_reminders(
    lookback_days: int = Query(default=60, ge=1, le=365),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Tareas de hoy y vencidas recientes, según la zona horaria configurada."""
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    today_items, overdue = build_reminders(
        db, settings, today, lookback_days=lookback_days
    )
    return RemindersResponse(
        date=today,
        timezone=settings.timezone,
        today=today_items,
        overdue=overdue,
    )


@router.get("/notes/{note_id}", response_model=NoteRead)
def get_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")
    return note


@router.post("/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreate, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    data = payload.model_dump()
    note = Note()
    try:
        apply_note_data(note, data, settings)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.put("/notes/{note_id}", response_model=NoteRead)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")

    data = payload.model_dump(exclude_unset=True)
    try:
        apply_note_data(note, data, settings)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc

    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")
    db.delete(note)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class NoteMove(BaseModel):
    column: str | None = Field(default=None, max_length=50)
    position: int | None = Field(default=None, ge=0)
    note_date: date | None = None


@router.api_route(
    "/notes/{note_id}/move",
    methods=["POST", "PATCH"],
    response_model=NoteRead,
)
def move_note(
    note_id: int,
    payload: NoteMove,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")

    data: dict[str, Any] = {}
    if payload.column is not None:
        data["status"] = payload.column
    if payload.position is not None:
        data["position"] = payload.position
    if payload.note_date is not None:
        data["note_date"] = payload.note_date

    if data:
        try:
            apply_note_data(note, data, settings)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(422, str(exc)) from exc
        db.commit()
        db.refresh(note)
    return note


class ColumnItem(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=50)
    color: str = Field(default="#64748b", pattern=r"^#[0-9a-fA-F]{6}$")


class ColumnsUpdate(BaseModel):
    columns: list[ColumnItem]


@router.get("/board/columns", response_model=list[ColumnItem])
def get_board_columns(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Obtiene las columnas configuradas para el tablero."""
    return [ColumnItem.model_validate(item) for item in settings.board_columns]


@router.put("/board/columns", response_model=list[ColumnItem])
def update_board_columns(
    payload: ColumnsUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Actualiza la configuración de columnas del tablero."""
    columns = payload.columns
    if len(columns) < 1:
        raise HTTPException(422, "Debe tener al menos una columna")
    if len(columns) != len(set(c.id for c in columns)):
        raise HTTPException(422, "IDs de columna duplicados")
    # Actualizar en la configuración de ajustes
    from app.config import update_settings
    try:
        update_settings({"board_columns": [c.model_dump() for c in columns]})
    except Exception as e:
        raise HTTPException(500, f"Error al guardar configuración: {str(e)}")
    return columns

