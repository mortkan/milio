"""Rutas para gestión de rutinas y hábitos (CRUD completo + registros)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Routine, RoutineRecord
from app.schemas import (
    RoutineCreate,
    RoutineRead,
    RoutineRecordRead,
    RoutineUpdate,
)
from app.services import (
    get_checklist_items,
    get_routine_streak,
    get_routine_templates,
    get_today_routine_records,
    mark_routine_complete,
    routine_dict,
    utcnow,
)

router = APIRouter(prefix="/api", tags=["routines"])


# ---------------------------------------------------------------------------
# Plantillas (sin BD)
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=dict[str, Any])
def read_routine_templates() -> dict[str, Any]:
    return get_routine_templates()


@router.get("/checklist/{template_name}", response_model=list[str])
def read_checklist(template_name: str) -> list[str]:
    return get_checklist_items(template_name)


# ---------------------------------------------------------------------------
# CRUD de rutinas
# ---------------------------------------------------------------------------


@router.get("/routines", response_model=list[RoutineRead])
def list_routines(db: Session = Depends(get_db)) -> list[Any]:
    return db.query(Routine).order_by(Routine.id).all()


@router.post(
    "/routines",
    response_model=RoutineRead,
    status_code=status.HTTP_201_CREATED,
)
def create_routine(payload: RoutineCreate, db: Session = Depends(get_db)) -> Any:
    routine = Routine(
        title=payload.title,
        description=payload.description,
        schedule=payload.schedule,
        color=payload.color,
        icon=payload.icon,
        checklist_template=payload.checklist_template,
    )
    db.add(routine)
    db.commit()
    db.refresh(routine)
    return routine


@router.get("/routines/today")
def list_today_routines(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    routines = db.query(Routine).order_by(Routine.id).all()
    return [routine_dict(routine) for routine in routines]


@router.get("/routines/today-records")
@router.get("/today-records", include_in_schema=False)
def read_today_routine_records(
    db: Session = Depends(get_db),
) -> dict[int, dict[str, Any]]:
    records = get_today_routine_records(db)
    return {
        routine_id: {
            "id": record.id,
            "routine_id": record.routine_id,
            "date": record.date.isoformat(),
            "completed": record.completed,
            "completed_at": (
                record.completed_at.isoformat() if record.completed_at else None
            ),
            "notes": record.notes,
        }
        for routine_id, record in records.items()
    }


@router.get("/routines/{routine_id}", response_model=RoutineRead)
def get_routine(routine_id: int, db: Session = Depends(get_db)) -> Any:
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Rutina no encontrada")
    return routine


@router.put("/routines/{routine_id}", response_model=RoutineRead)
def update_routine(
    routine_id: int,
    payload: RoutineUpdate,
    db: Session = Depends(get_db),
) -> Any:
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Rutina no encontrada")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(routine, field, value)
    routine.updated_at = utcnow()
    db.commit()
    db.refresh(routine)
    return routine


@router.delete("/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_routine(routine_id: int, db: Session = Depends(get_db)) -> Response:
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Rutina no encontrada")
    db.delete(routine)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Registros de completado
# ---------------------------------------------------------------------------


@router.get("/routines/{routine_id}/streak")
@router.get("/streak/{routine_id}", include_in_schema=False)
def read_routine_streak(
    routine_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if db.get(Routine, routine_id) is None:
        raise HTTPException(404, "Rutina no encontrada")
    return get_routine_streak(routine_id, db)


@router.post("/routines/{routine_id}/complete")
@router.post("/{routine_id}/complete", include_in_schema=False)
def complete_routine(
    routine_id: int,
    db: Session = Depends(get_db),
    notes: str = Query(default="", max_length=2000),
) -> dict[str, Any]:
    if db.get(Routine, routine_id) is None:
        raise HTTPException(404, "Rutina no encontrada")
    record = mark_routine_complete(routine_id, db, notes)
    return {
        "id": record.id,
        "routine_id": record.routine_id,
        "date": record.date.isoformat(),
        "completed": record.completed,
        "completed_at": (
            record.completed_at.isoformat() if record.completed_at else None
        ),
        "notes": record.notes,
    }


@router.post("/routines/{routine_id}/uncomplete", response_model=RoutineRecordRead)
def uncomplete_routine(
    routine_id: int,
    db: Session = Depends(get_db),
) -> Any:
    """Marca el registro de hoy como no completado."""
    from datetime import date

    if db.get(Routine, routine_id) is None:
        raise HTTPException(404, "Rutina no encontrada")
    today = date.today()
    record = (
        db.query(RoutineRecord)
        .filter(RoutineRecord.routine_id == routine_id, RoutineRecord.date == today)
        .first()
    )
    if record is None:
        raise HTTPException(404, "No hay registro de hoy para esta rutina")
    record.completed = False
    record.completed_at = None
    db.commit()
    db.refresh(record)
    return record
