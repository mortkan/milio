"""Modelos ORM de la Agenda."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


def utcnow():
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


class Note(Base):
    __tablename__ = "notes"

    id = mapped_column(Integer, primary_key=True)
    title = mapped_column(String(100), nullable=False)
    content = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at = mapped_column(DateTime, nullable=False, default=utcnow)
    type = mapped_column(String(30), nullable=True)
    status = mapped_column(String(20), nullable=False, default="none")
    position = mapped_column(Integer, nullable=False, default=0)
    note_date = mapped_column(Date, nullable=True)


class QuickNote(Base):
    __tablename__ = "quick_notes"

    id = mapped_column(Integer, primary_key=True)
    content = mapped_column(String(200), nullable=False)
    created_at = mapped_column(DateTime, nullable=False, default=utcnow)


class Routine(Base):
    __tablename__ = "routines"

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(100), nullable=False)
    description = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime, nullable=False, default=utcnow)


class RoutineRecord(Base):
    __tablename__ = "routine_records"

    id = mapped_column(Integer, primary_key=True)
    routine_id = mapped_column(Integer, nullable=False)
    record_date = mapped_column(Date, nullable=False)
    completed = mapped_column(Boolean, nullable=False, default=False)
