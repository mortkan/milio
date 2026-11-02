"""Rutas para gestión de rutinas y hábitos."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Routine, RoutineRecord
from app.schemas import NoteRead, Recurrence, Settings
from app.services import (
    get_checklist_items,
    get_routine_streak,
    get_routine_templates,
    mark_routine_complete,
    get_today_routine_records,
)

router = APIRouter(prefix="/api", tags=["routines"])


@router.get("/templates", response_model=dict[str, Any])
def get_routine_templates() -> dict[str, Any]:
    """Obtiene las plantillas de rutinas predefinidas."""
    from app.services import get_routine_templates as _get_templates
    return _get_templates()


@router.get("/checklist/{template_name}")
def get_checklist(template_name: str) -> list[str]:
    """Obtiene los ítems de checklist de una plantilla."""
    from app.services import get_checklist_items as _get_checklist
    return _get_checklist(template_name)


@router.get("/today-records", response_model=dict[int, Any])
def get_today_routine_records(
    db: Session = Depends(get_db),
) -> dict[int, Any]:
    """Obtiene los registros de rutinas de hoy."""
    from app.services import get_today_routine_records as _get_today_records
    return _get_today_records(db)


@router.get("/streak/{routine_id}")
def get_routine_streak(
    routine_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Calcula la racha y porcentaje de cumplimiento de una rutina."""
    from app.services import get_routine_streak as _get_streak
    return _get_streak(routine_id, db)


@router.post("/{routine_id}/complete", response_model=NoteRead)
def complete_routine(
    routine_id: int,
    db: Session = Depends(get_db),
    notes: str = Query(default="", alias="notes"),
) -> Any:
    """Marca una rutina como completada para hoy."""
    from app.services import mark_routine_complete as _mark_complete
    record = _mark_complete(routine_id, db, notes)
    return {"id": record.id, "routine_id": record.routine_id, "date": record.date.isoformat(), "completed": record.completed}