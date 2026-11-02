"""Exportación, importación y datos de ejemplo."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.config import deep_merge, get_settings, update_settings
from app.database import get_db
from app.models import Note, QuickNote
from app.schemas import (
    ImportPayload,
    ImportResult,
    Settings,
)
from app.services import (
    apply_note_data,
    export_payload,
    seed_demo,
)

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/export")
def export_data(
    fmt: Literal["json", "csv"] = Query(default="json", alias="format"),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if fmt == "json":
        payload = export_payload(db, settings)
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(
            content=content.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="agenda-{timestamp}.json"'
                )
            },
        )

    notes = db.query(Note).order_by(Note.note_date, Note.id).all()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "title",
            "content",
            "date",
            "time",
            "category",
            "priority",
            "color",
            "completed",
            "recurrence",
            "recurrence_end",
            "created_at",
            "updated_at",
        ]
    )
    for note in notes:
        writer.writerow(
            [
                note.id,
                note.title,
                note.content,
                note.note_date.isoformat(),
                note.time or "",
                note.category or "",
                note.priority or "",
                note.color or "",
                "true" if note.completed else "false",
                note.recurrence,
                note.recurrence_end.isoformat() if note.recurrence_end else "",
                note.created_at.isoformat(),
                note.updated_at.isoformat(),
            ]
        )
    body = "\ufeff" + buffer.getvalue()
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="agenda-{timestamp}.csv"'
            )
        },
    )


@router.post("/import", response_model=ImportResult)
def import_data(
    payload: ImportPayload,
    mode: Literal["merge", "replace"] = Query(default="merge"),
    import_settings: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    settings = get_settings()

    if import_settings and payload.settings:
        candidate = deep_merge(
            settings.model_dump(mode="json"), payload.settings
        )
        try:
            Settings.model_validate(candidate)
        except Exception as exc:
            raise HTTPException(
                422, f"Los ajustes importados no son válidos: {exc}"
            ) from exc

    try:
        if mode == "replace":
            db.query(Note).delete()
            db.query(QuickNote).delete()

        for item in payload.notes:
            note = Note()
            apply_note_data(note, item.model_dump())
            db.add(note)

        for item in payload.quick_notes:
            db.add(QuickNote(content=item.content))

        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"No se pudo importar: {exc}") from exc

    if import_settings and payload.settings:
        try:
            update_settings(payload.settings)
        except ValueError as exc:
            raise HTTPException(
                422, f"Los datos se importaron, pero los ajustes no: {exc}"
            ) from exc

    return ImportResult(
        notes_imported=len(payload.notes),
        quick_notes_imported=len(payload.quick_notes),
        mode=mode,
        settings_imported=bool(import_settings and payload.settings),
    )


@router.post("/demo/seed")
def load_demo_data(
    reset: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    result = seed_demo(db, settings, reset=reset)
    return result
