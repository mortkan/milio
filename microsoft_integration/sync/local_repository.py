"""Local repository adapter — the ONLY point of contact with Milo tables.

This module reads from Milo's notes/tasks/events tables via raw SQL queries
so that it is decoupled from the Milo ORM and resilient to schema changes
made by the parallel development.

Design principles:
- Returns internal DTOs (LocalTaskDTO, LocalEventDTO) — never raw ORM objects
- Read queries only — never modifies Milo data unless through a controlled update path
- Checks actual column existence before using optional fields
- item_type discrimination: task → 'task', event → 'event'
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from microsoft_integration.schemas import LocalEventDTO, LocalTaskDTO

logger = logging.getLogger("microsoft.sync.local_repository")

# ---------------------------------------------------------------------------
# Column inspection helpers
# ---------------------------------------------------------------------------

_NOTES_COLUMNS: Optional[set[str]] = None


def _get_notes_columns(db: Session) -> set[str]:
    global _NOTES_COLUMNS
    if _NOTES_COLUMNS is not None:
        return _NOTES_COLUMNS
    try:
        rows = db.execute(text("SHOW COLUMNS FROM notes")).fetchall()
        _NOTES_COLUMNS = {str(r[0]) for r in rows}
    except Exception:
        try:
            rows = db.execute(text("PRAGMA table_info(notes)")).fetchall()
            _NOTES_COLUMNS = {str(r[1]) for r in rows}
        except Exception as exc:
            logger.error("Cannot introspect notes table: %s", exc)
            _NOTES_COLUMNS = set()
    return _NOTES_COLUMNS


# ---------------------------------------------------------------------------
# Tag lookup helper
# ---------------------------------------------------------------------------


def _get_tags_for_note(db: Session, note_id: int) -> List[str]:
    try:
        rows = db.execute(
            text(
                "SELECT t.name FROM tags t "
                "JOIN note_tags nt ON nt.tag_id = t.id "
                "WHERE nt.note_id = :note_id"
            ),
            {"note_id": note_id},
        ).fetchall()
        return [str(r[0]) for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# DTO construction helpers
# ---------------------------------------------------------------------------


def _row_to_task_dto(row, tags: List[str], cols: set[str]) -> LocalTaskDTO:
    d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

    # Handle due_date — Milo stores events/tasks with note_date
    due_date: Optional[datetime] = None
    raw_date = d.get("note_date")
    if raw_date:
        if isinstance(raw_date, datetime):
            due_date = raw_date.replace(tzinfo=None)
        else:
            try:
                from datetime import date
                if isinstance(raw_date, date):
                    due_date = datetime(raw_date.year, raw_date.month, raw_date.day)
            except Exception:
                pass

    return LocalTaskDTO(
        id=int(d["id"]),
        title=str(d.get("title") or ""),
        description=str(d.get("content") or "") or None,
        due_date=due_date,
        completed=bool(d.get("completed", False)),
        completed_at=None,  # Not stored separately in current schema
        recurrence=str(d.get("recurrence") or "") or None,
        tags=tags,
        estimated_minutes=d.get("estimated_minutes"),
        actual_minutes=d.get("actual_minutes"),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


def _row_to_event_dto(row, tags: List[str], cols: set[str]) -> LocalEventDTO:
    d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

    start: Optional[datetime] = None
    raw_date = d.get("note_date")
    if raw_date:
        if isinstance(raw_date, datetime):
            start = raw_date.replace(tzinfo=None)
        else:
            try:
                from datetime import date
                if isinstance(raw_date, date):
                    start = datetime(raw_date.year, raw_date.month, raw_date.day)
            except Exception:
                pass

    # Duration → end time
    end: Optional[datetime] = None
    duration_minutes = d.get("duration_minutes")
    if start and duration_minutes:
        from datetime import timedelta
        end = start + timedelta(minutes=int(duration_minutes))

    # Detect all-day: no time field or time is "00:00"
    time_val = str(d.get("time") or "")
    all_day = not time_val or time_val in ("00:00", "")

    return LocalEventDTO(
        id=int(d["id"]),
        title=str(d.get("title") or ""),
        description=str(d.get("content") or "") or None,
        start=start,
        end=end,
        all_day=all_day,
        location=None,  # Not in current schema — extensible
        recurrence=str(d.get("recurrence") or "") or None,
        tags=tags,
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Public interface — Tasks
# ---------------------------------------------------------------------------


def get_task(db: Session, task_id: int) -> Optional[LocalTaskDTO]:
    cols = _get_notes_columns(db)
    row = db.execute(
        text("SELECT * FROM notes WHERE id = :id AND item_type = 'task'"),
        {"id": task_id},
    ).first()
    if not row:
        return None
    tags = _get_tags_for_note(db, task_id)
    return _row_to_task_dto(row, tags, cols)


def list_changed_tasks(
    db: Session, since: Optional[datetime] = None
) -> List[LocalTaskDTO]:
    cols = _get_notes_columns(db)
    if since:
        rows = db.execute(
            text(
                "SELECT * FROM notes WHERE item_type = 'task' "
                "AND updated_at >= :since AND (status IS NULL OR status != 'deleted')"
            ),
            {"since": since},
        ).fetchall()
    else:
        rows = db.execute(
            text(
                "SELECT * FROM notes WHERE item_type = 'task' "
                "AND (status IS NULL OR status != 'deleted')"
            )
        ).fetchall()

    result = []
    for row in rows:
        d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        tags = _get_tags_for_note(db, int(d["id"]))
        result.append(_row_to_task_dto(row, tags, cols))
    return result


def list_all_tasks(db: Session) -> List[LocalTaskDTO]:
    return list_changed_tasks(db, since=None)


def update_task(
    db: Session,
    task_id: int,
    *,
    title: Optional[str] = None,
    completed: Optional[bool] = None,
    updated_at: Optional[datetime] = None,
) -> bool:
    """Update mutable task fields. Returns True if row was found and updated."""
    updates = {}
    if title is not None:
        updates["title"] = title
    if completed is not None:
        updates["completed"] = completed
    if updated_at is not None:
        updates["updated_at"] = updated_at
    else:
        updates["updated_at"] = datetime.utcnow()

    if not updates:
        return False

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    params = {**updates, "id": task_id}
    result = db.execute(
        text(f"UPDATE notes SET {set_clause} WHERE id = :id AND item_type = 'task'"),
        params,
    )
    return (result.rowcount or 0) > 0


def soft_delete_task(db: Session, task_id: int) -> bool:
    """Mark a task as deleted (soft delete). Returns True if found."""
    result = db.execute(
        text(
            "UPDATE notes SET status = 'deleted', updated_at = :now "
            "WHERE id = :id AND item_type = 'task'"
        ),
        {"id": task_id, "now": datetime.utcnow()},
    )
    return (result.rowcount or 0) > 0


def create_task(
    db: Session,
    title: str,
    *,
    description: str = "",
    due_date: Optional[datetime] = None,
    completed: bool = False,
    recurrence: str = "none",
) -> int:
    """Create a new task in the Milo notes table. Returns the new task id."""
    from datetime import date

    note_date = (due_date.date() if due_date else date.today())
    now = datetime.utcnow()
    result = db.execute(
        text(
            "INSERT INTO notes "
            "(title, content, note_date, item_type, completed, recurrence, "
            " status, position, progress_percent, created_at, updated_at) "
            "VALUES (:title, :content, :note_date, 'task', :completed, :recurrence, "
            "'none', 0, 0, :now, :now)"
        ),
        {
            "title": title,
            "content": description,
            "note_date": note_date,
            "completed": completed,
            "recurrence": recurrence,
            "now": now,
        },
    )
    return result.lastrowid


# ---------------------------------------------------------------------------
# Public interface — Events
# ---------------------------------------------------------------------------


def get_event(db: Session, event_id: int) -> Optional[LocalEventDTO]:
    cols = _get_notes_columns(db)
    row = db.execute(
        text("SELECT * FROM notes WHERE id = :id AND item_type = 'event'"),
        {"id": event_id},
    ).first()
    if not row:
        return None
    tags = _get_tags_for_note(db, event_id)
    return _row_to_event_dto(row, tags, cols)


def list_changed_events(
    db: Session, since: Optional[datetime] = None
) -> List[LocalEventDTO]:
    cols = _get_notes_columns(db)
    if since:
        rows = db.execute(
            text(
                "SELECT * FROM notes WHERE item_type = 'event' "
                "AND updated_at >= :since AND (status IS NULL OR status != 'deleted')"
            ),
            {"since": since},
        ).fetchall()
    else:
        rows = db.execute(
            text(
                "SELECT * FROM notes WHERE item_type = 'event' "
                "AND (status IS NULL OR status != 'deleted')"
            )
        ).fetchall()

    result = []
    for row in rows:
        d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        tags = _get_tags_for_note(db, int(d["id"]))
        result.append(_row_to_event_dto(row, tags, cols))
    return result


def list_all_events(db: Session) -> List[LocalEventDTO]:
    return list_changed_events(db, since=None)


def update_event(
    db: Session,
    event_id: int,
    *,
    title: Optional[str] = None,
    updated_at: Optional[datetime] = None,
) -> bool:
    updates = {}
    if title is not None:
        updates["title"] = title
    updates["updated_at"] = updated_at or datetime.utcnow()

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    params = {**updates, "id": event_id}
    result = db.execute(
        text(f"UPDATE notes SET {set_clause} WHERE id = :id AND item_type = 'event'"),
        params,
    )
    return (result.rowcount or 0) > 0


def soft_delete_event(db: Session, event_id: int) -> bool:
    result = db.execute(
        text(
            "UPDATE notes SET status = 'deleted', updated_at = :now "
            "WHERE id = :id AND item_type = 'event'"
        ),
        {"id": event_id, "now": datetime.utcnow()},
    )
    return (result.rowcount or 0) > 0


def create_event(
    db: Session,
    title: str,
    *,
    description: str = "",
    start: Optional[datetime] = None,
    duration_minutes: Optional[int] = None,
    recurrence: str = "none",
) -> int:
    from datetime import date

    note_date = (start.date() if start else date.today())
    time_val = start.strftime("%H:%M") if start and not (start.hour == 0 and start.minute == 0) else None
    now = datetime.utcnow()
    result = db.execute(
        text(
            "INSERT INTO notes "
            "(title, content, note_date, time, item_type, completed, recurrence, "
            " duration_minutes, status, position, progress_percent, created_at, updated_at) "
            "VALUES (:title, :content, :note_date, :time, 'event', 0, :recurrence, "
            ":duration_minutes, 'none', 0, 0, :now, :now)"
        ),
        {
            "title": title,
            "content": description,
            "note_date": note_date,
            "time": time_val,
            "recurrence": recurrence,
            "duration_minutes": duration_minutes,
            "now": now,
        },
    )
    return result.lastrowid
