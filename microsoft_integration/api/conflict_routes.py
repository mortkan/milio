"""Conflict management routes."""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from microsoft_integration.database import get_db
from microsoft_integration.models import MsSyncConflict
from microsoft_integration.schemas import ConflictOut, ConflictResolveIn
from microsoft_integration.sync.conflict_resolver import resolve_conflict

logger = logging.getLogger("microsoft.api.conflict_routes")

router = APIRouter(prefix="/api/microsoft/conflicts", tags=["Microsoft Conflicts"])


@router.get("", response_model=List[ConflictOut], summary="List pending conflicts")
def list_conflicts(
    account_id: int | None = None,
    status: str = "pending",
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(MsSyncConflict).filter(MsSyncConflict.status == status)
    if account_id is not None:
        q = q.filter(MsSyncConflict.account_id == account_id)
    conflicts = q.order_by(MsSyncConflict.created_at.desc()).limit(limit).all()
    return [ConflictOut.model_validate(c) for c in conflicts]


@router.get("/{conflict_id}", response_model=ConflictOut, summary="Get conflict details")
def get_conflict(conflict_id: int, db: Session = Depends(get_db)):
    conflict = db.query(MsSyncConflict).filter(MsSyncConflict.id == conflict_id).first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return ConflictOut.model_validate(conflict)


@router.post("/{conflict_id}/resolve", response_model=ConflictOut, summary="Resolve a conflict")
async def resolve_conflict_endpoint(
    conflict_id: int,
    body: ConflictResolveIn,
    db: Session = Depends(get_db),
):
    """Resolve a sync conflict with one of: keep_local, keep_microsoft, merge."""
    valid_resolutions = {"keep_local", "keep_microsoft", "merge"}
    if body.resolution not in valid_resolutions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution. Must be one of: {valid_resolutions}",
        )

    conflict = db.query(MsSyncConflict).filter(MsSyncConflict.id == conflict_id).first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")

    if conflict.status != "pending":
        raise HTTPException(status_code=409, detail=f"Conflict is already {conflict.status}")

    # Apply the resolution
    if body.resolution == "keep_local":
        await _apply_keep_local(conflict, db)
    elif body.resolution == "keep_microsoft":
        await _apply_keep_microsoft(conflict, db)
    # merge: user resolves manually — just mark it resolved

    resolved = resolve_conflict(db, conflict_id, body.resolution)
    db.commit()
    return ConflictOut.model_validate(resolved)


async def _apply_keep_local(conflict: MsSyncConflict, db: Session) -> None:
    """Push local version to Microsoft, overwriting remote."""
    from microsoft_integration.main import get_sync_config
    from microsoft_integration.auth.token_cache import PersistedTokenCache
    from microsoft_integration.graph.client import GraphClient
    from microsoft_integration.sync import local_repository, mapping
    from microsoft_integration.graph import calendar as cal_api, todo as todo_api
    from microsoft_integration.models import MsEntityLink

    config = get_sync_config()
    persisted_cache = PersistedTokenCache(conflict.account_id, config.encryptor, db)

    link = db.query(MsEntityLink).filter(MsEntityLink.id == conflict.entity_link_id).first()
    if not link:
        return

    async with GraphClient(config.settings, persisted_cache) as client:
        if conflict.entity_type == "task":
            task = local_repository.get_task(db, conflict.local_entity_id)
            if task:
                payload = mapping.task_to_graph_payload(task)
                await todo_api.update_task(client, link.remote_container_id or "", link.remote_entity_id, payload)
        elif conflict.entity_type == "event":
            event = local_repository.get_event(db, conflict.local_entity_id)
            if event:
                payload = mapping.event_to_graph_payload(event, config.settings.microsoft_timezone)
                await cal_api.update_event(client, link.remote_container_id or "", link.remote_entity_id, payload)


async def _apply_keep_microsoft(conflict: MsSyncConflict, db: Session) -> None:
    """Pull remote version into Milo, overwriting local."""
    import json as json_mod
    from microsoft_integration.sync import local_repository, mapping

    if conflict.remote_snapshot:
        try:
            snapshot = json_mod.loads(conflict.remote_snapshot)
            if conflict.entity_type == "task":
                local_repository.update_task(
                    db,
                    conflict.local_entity_id,
                    title=snapshot.get("title"),
                    completed=snapshot.get("completed", False),
                )
            elif conflict.entity_type == "event":
                local_repository.update_event(
                    db, conflict.local_entity_id, title=snapshot.get("subject")
                )
        except Exception as exc:
            logger.error("Failed to apply keep_microsoft resolution: %s", exc)
