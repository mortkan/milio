"""Bandeja de notas rápidas y conversión a notas de un día."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Note, QuickNote
from app.schemas import (
    NoteRead,
    QuickNoteAssign,
    QuickNoteCreate,
    QuickNoteRead,
    QuickNoteUpdate,
)
from app.services import apply_note_data, derive_title

router = APIRouter(prefix="/api", tags=["quick-notes"])


@router.get("/quick-notes", response_model=list[QuickNoteRead])
def list_quick_notes(db: Session = Depends(get_db)):
    return (
        db.query(QuickNote)
        .order_by(QuickNote.created_at.desc(), QuickNote.id.desc())
        .all()
    )


@router.post(
    "/quick-notes",
    response_model=QuickNoteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_quick_note(payload: QuickNoteCreate, db: Session = Depends(get_db)):
    item = QuickNote(content=payload.content)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/quick-notes/{quick_id}", response_model=QuickNoteRead)
def update_quick_note(
    quick_id: int,
    payload: QuickNoteUpdate,
    db: Session = Depends(get_db),
):
    item = db.get(QuickNote, quick_id)
    if item is None:
        raise HTTPException(404, "Nota rápida no encontrada")
    item.content = payload.content
    db.commit()
    db.refresh(item)
    return item


@router.delete("/quick-notes/{quick_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quick_note(quick_id: int, db: Session = Depends(get_db)):
    item = db.get(QuickNote, quick_id)
    if item is None:
        raise HTTPException(404, "Nota rápida no encontrada")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/quick-notes/{quick_id}/assign",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_quick_note(
    quick_id: int,
    payload: QuickNoteAssign,
    db: Session = Depends(get_db),
):
    item = db.get(QuickNote, quick_id)
    if item is None:
        raise HTTPException(404, "Nota rápida no encontrada")

    note = Note()
    data = {
        "title": derive_title(item.content),
        "content": item.content,
        "note_date": payload.note_date,
        "category": payload.category,
        "priority": payload.priority,
        "recurrence": "none",
        "completed": False,
    }
    try:
        apply_note_data(note, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    db.add(note)
    db.delete(item)
    db.commit()
    db.refresh(note)
    return note
