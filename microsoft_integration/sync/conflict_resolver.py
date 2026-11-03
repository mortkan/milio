"""Conflict detection and resolution for bidirectional sync.

A conflict occurs when BOTH the local entity AND the remote entity have been
modified since the last sync. Conflicts are stored in ms_sync_conflicts and
must be manually resolved (or automatically resolved per configured policy).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from microsoft_integration.models import MsEntityLink, MsSyncConflict

logger = logging.getLogger("microsoft.sync.conflict_resolver")


def detect_conflict(
    link: MsEntityLink,
    local_updated_at: Optional[datetime],
    remote_last_modified: Optional[datetime],
) -> bool:
    """Return True if both sides changed since last sync (a conflict exists)."""
    if not link.last_synced_at:
        return False  # No prior sync — treat as first sync

    local_changed = (
        local_updated_at is not None
        and local_updated_at > link.last_synced_at
    )
    remote_changed = (
        remote_last_modified is not None
        and remote_last_modified > link.last_synced_at
    )
    return local_changed and remote_changed


def record_conflict(
    db: Session,
    *,
    account_id: int,
    entity_link: MsEntityLink,
    entity_type: str,
    local_snapshot: Any,
    remote_snapshot: Any,
    local_modified_at: Optional[datetime],
    remote_modified_at: Optional[datetime],
) -> MsSyncConflict:
    """Record a detected conflict in ms_sync_conflicts."""
    # Check if there's already a pending conflict for this link
    existing = (
        db.query(MsSyncConflict)
        .filter(
            MsSyncConflict.entity_link_id == entity_link.id,
            MsSyncConflict.status == "pending",
        )
        .first()
    )
    if existing:
        # Update the existing conflict
        if local_snapshot is not None:
            existing.local_snapshot = json.dumps(local_snapshot, default=str)
        if remote_snapshot is not None:
            existing.remote_snapshot = json.dumps(remote_snapshot, default=str)
        existing.local_modified_at = local_modified_at
        existing.remote_modified_at = remote_modified_at
        db.flush()
        return existing

    conflict = MsSyncConflict(
        account_id=account_id,
        entity_link_id=entity_link.id,
        entity_type=entity_type,
        local_entity_id=entity_link.local_entity_id,
        remote_entity_id=entity_link.remote_entity_id,
        local_snapshot=json.dumps(local_snapshot, default=str) if local_snapshot else None,
        remote_snapshot=json.dumps(remote_snapshot, default=str) if remote_snapshot else None,
        local_modified_at=local_modified_at,
        remote_modified_at=remote_modified_at,
        status="pending",
    )
    db.add(conflict)
    db.flush()
    logger.info(
        "Conflict recorded: type=%s local_id=%d remote_id=%s",
        entity_type,
        entity_link.local_entity_id,
        entity_link.remote_entity_id,
    )
    return conflict


def resolve_conflict(
    db: Session,
    conflict_id: int,
    resolution: str,  # keep_local | keep_microsoft | merge
) -> Optional[MsSyncConflict]:
    """Mark a conflict as resolved with the given resolution strategy."""
    conflict = db.query(MsSyncConflict).filter(MsSyncConflict.id == conflict_id).first()
    if not conflict:
        return None
    if conflict.status != "pending":
        return conflict

    conflict.status = "resolved"
    conflict.resolution = resolution
    conflict.resolved_at = datetime.utcnow()
    db.flush()
    return conflict


def count_pending_conflicts(db: Session, account_id: int) -> int:
    return (
        db.query(MsSyncConflict)
        .filter(
            MsSyncConflict.account_id == account_id,
            MsSyncConflict.status == "pending",
        )
        .count()
    )
