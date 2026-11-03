"""Distributed sync locks using MariaDB advisory locks.

Prevents simultaneous scheduler + manual syncs from corrupting state.
Uses GET_LOCK / RELEASE_LOCK for MariaDB advisory locking.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("microsoft.sync.locks")

_LOCK_TIMEOUT_SECONDS = 0  # 0 = fail immediately if locked


@contextmanager
def sync_lock(db: Session, account_id: int, resource_type: str) -> Iterator[bool]:
    """Context manager that acquires an advisory lock for a specific sync job.

    Yields:
        True if lock was acquired, False if resource is already being synced.

    Usage::
        with sync_lock(db, account_id=1, resource_type="calendar") as acquired:
            if not acquired:
                # Skip — another sync is running
                return
            # Do sync work
    """
    lock_name = f"milo_ms_sync_{account_id}_{resource_type}"
    acquired = False
    try:
        result = db.execute(
            text("SELECT GET_LOCK(:name, :timeout)"),
            {"name": lock_name, "timeout": _LOCK_TIMEOUT_SECONDS},
        ).scalar()
        acquired = bool(result)
        if not acquired:
            logger.info(
                "Sync lock busy for account=%d type=%s — skipping",
                account_id,
                resource_type,
            )
        yield acquired
    finally:
        if acquired:
            try:
                db.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
            except Exception as exc:
                logger.warning("Failed to release lock %s: %s", lock_name, exc)


@contextmanager
def sync_lock_sqlite(db: Session, account_id: int, resource_type: str) -> Iterator[bool]:
    """Fallback lock implementation for SQLite (single-process only).

    Uses an in-memory dict — only safe in single-process environments.
    """
    import threading
    _sqlite_locks: dict = getattr(sync_lock_sqlite, "_locks", {})  # type: ignore[attr-defined]
    if not hasattr(sync_lock_sqlite, "_locks"):
        sync_lock_sqlite._locks = {}  # type: ignore[attr-defined]
        sync_lock_sqlite._mutex = threading.Lock()  # type: ignore[attr-defined]

    key = f"{account_id}_{resource_type}"
    mutex = sync_lock_sqlite._mutex  # type: ignore[attr-defined]
    locks = sync_lock_sqlite._locks  # type: ignore[attr-defined]

    with mutex:
        if locks.get(key):
            yield False
            return
        locks[key] = True

    try:
        yield True
    finally:
        with mutex:
            locks.pop(key, None)
