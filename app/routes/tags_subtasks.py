"""Rutas para etiquetas (tags) y subtareas (subtasks)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Note, NoteTag, Subtask, Tag
from app.schemas import (
    SubtaskCreate,
    SubtaskRead,
    SubtaskUpdate,
    TagCreate,
    TagRead,
)

router = APIRouter(prefix="/api", tags=["tags", "subtasks"])


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@router.get("/tags", response_model=list[TagRead])
def list_tags(db: Session = Depends(get_db)):
    return db.query(Tag).order_by(Tag.name).all()


@router.post("/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(payload: TagCreate, db: Session = Depends(get_db)):
    existing = db.query(Tag).filter(Tag.name == payload.name).first()
    if existing:
        raise HTTPException(409, f"La etiqueta '{payload.name}' ya existe")
    tag = Tag(name=payload.name, color=payload.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(404, "Etiqueta no encontrada")
    db.delete(tag)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notes/{note_id}/tags", response_model=list[TagRead])
def get_note_tags(note_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")
    return note.tags


@router.post(
    "/notes/{note_id}/tags/{tag_id}",
    response_model=list[TagRead],
    status_code=status.HTTP_201_CREATED,
)
def add_tag_to_note(note_id: int, tag_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(404, "Etiqueta no encontrada")
    if tag not in note.tags:
        note.tags.append(tag)
        db.commit()
        db.refresh(note)
    return note.tags


@router.delete(
    "/notes/{note_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_tag_from_note(note_id: int, tag_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(404, "Etiqueta no encontrada")
    if tag in note.tags:
        note.tags.remove(tag)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Subtasks
# ---------------------------------------------------------------------------


@router.get("/notes/{note_id}/subtasks", response_model=list[SubtaskRead])
def list_subtasks(note_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")
    return sorted(note.subtasks, key=lambda s: s.position)


@router.post(
    "/notes/{note_id}/subtasks",
    response_model=SubtaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_subtask(
    note_id: int,
    payload: SubtaskCreate,
    db: Session = Depends(get_db),
):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nota no encontrada")
    subtask = Subtask(
        note_id=note_id,
        title=payload.title,
        completed=payload.completed,
        position=payload.position,
    )
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return subtask


@router.put("/notes/{note_id}/subtasks/{subtask_id}", response_model=SubtaskRead)
def update_subtask(
    note_id: int,
    subtask_id: int,
    payload: SubtaskUpdate,
    db: Session = Depends(get_db),
):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None or subtask.note_id != note_id:
        raise HTTPException(404, "Subtarea no encontrada")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(subtask, field, value)
    db.commit()
    db.refresh(subtask)
    return subtask


@router.delete(
    "/notes/{note_id}/subtasks/{subtask_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_subtask(
    note_id: int,
    subtask_id: int,
    db: Session = Depends(get_db),
):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None or subtask.note_id != note_id:
        raise HTTPException(404, "Subtarea no encontrada")
    db.delete(subtask)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
