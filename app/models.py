"""Modelos ORM de la Agenda — compatibles con MariaDB y SQLite."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC para MariaDB


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note_date: Mapped[date] = mapped_column(Date, nullable=False)
    time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(30), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recurrence: Mapped[str] = mapped_column(
        String(10), nullable=False, default="none"
    )
    recurrence_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="none"
    )
    position: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    # Tipo de ítem: note | task | event
    item_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="note"
    )
    # Campos de gestión de trabajo (tareas y eventos)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    # Relaciones
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary="note_tags", back_populates="notes", lazy="select"
    )
    subtasks: Mapped[list["Subtask"]] = relationship(
        "Subtask", back_populates="note", cascade="all, delete-orphan", lazy="select"
    )

    __table_args__ = (
        Index("ix_notes_note_date", "note_date"),
        Index("ix_notes_status", "status"),
        Index("ix_notes_item_type", "item_type"),
    )


class QuickNote(Base):
    __tablename__ = "quick_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    notes: Mapped[list["Note"]] = relationship(
        "Note", secondary="note_tags", back_populates="tags", lazy="select"
    )

    __table_args__ = (
        Index("ix_tags_name", "name"),
    )


class NoteTag(Base):
    __tablename__ = "note_tags"

    note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (
        Index("ix_note_tags_tag_id", "tag_id"),
    )


class Subtask(Base):
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    note: Mapped["Note"] = relationship("Note", back_populates="subtasks")

    __table_args__ = (
        Index("ix_subtasks_note_id", "note_id"),
    )


class Routine(Base):
    __tablename__ = "routines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule: Mapped[str] = mapped_column(String(20), nullable=False, default="daily")
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(10), nullable=True)
    checklist_template: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class RoutineRecord(Base):
    __tablename__ = "routine_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    routine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routines.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("routine_id", "date", name="uq_routine_records_routine_date"),
        Index("ix_routine_records_routine_id", "routine_id"),
        Index("ix_routine_records_date", "date"),
    )
