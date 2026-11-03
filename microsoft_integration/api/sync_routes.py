"""Sync operation routes: manual sync, full resync, preview, history."""
from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from microsoft_integration.database import get_db
from microsoft_integration.models import MsAccount, MsSyncRun
from microsoft_integration.schemas import SyncPreviewOut, SyncRunOut

logger = logging.getLogger("microsoft.api.sync_routes")

router = APIRouter(prefix="/api/microsoft/accounts", tags=["Microsoft Sync"])


def _get_sync_config():
    from microsoft_integration.main import get_sync_config
    return get_sync_config()


@router.post("/{account_id}/sync", summary="Trigger incremental sync for an account")
async def trigger_sync(
    account_id: int,
    db: Session = Depends(get_db),
    sync_config=Depends(_get_sync_config),
):
    """Run an incremental sync for the given account."""
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account or not account.enabled:
        raise HTTPException(status_code=404, detail="Account not found or disabled")

    from microsoft_integration.sync.engine import run_sync_for_account
    try:
        sync_run = await run_sync_for_account(
            account_id=account_id,
            config=sync_config,
            db=db,
            is_full_sync=False,
            dry_run=False,
        )
        db.commit()
        return SyncRunOut.model_validate(sync_run)
    except Exception as exc:
        logger.error("Manual sync error for account %d: %s", account_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{account_id}/full-resync", summary="Full resync for an account")
async def trigger_full_resync(
    account_id: int,
    db: Session = Depends(get_db),
    sync_config=Depends(_get_sync_config),
):
    """Force a full resync, discarding saved delta state."""
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account or not account.enabled:
        raise HTTPException(status_code=404, detail="Account not found or disabled")

    # Invalidate delta tokens
    from microsoft_integration.models import MsSyncState
    db.query(MsSyncState).filter(MsSyncState.account_id == account_id).delete()
    db.flush()

    from microsoft_integration.sync.engine import run_sync_for_account
    try:
        sync_run = await run_sync_for_account(
            account_id=account_id,
            config=sync_config,
            db=db,
            is_full_sync=True,
            dry_run=False,
        )
        db.commit()
        return SyncRunOut.model_validate(sync_run)
    except Exception as exc:
        logger.error("Full resync error for account %d: %s", account_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{account_id}/sync-preview", response_model=SyncPreviewOut, summary="Dry-run sync preview")
async def sync_preview(
    account_id: int,
    db: Session = Depends(get_db),
    sync_config=Depends(_get_sync_config),
):
    """Return a preview of what would change without making any modifications."""
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account or not account.enabled:
        raise HTTPException(status_code=404, detail="Account not found or disabled")

    from microsoft_integration.sync.engine import run_sync_for_account
    try:
        sync_run = await run_sync_for_account(
            account_id=account_id,
            config=sync_config,
            db=db,
            is_full_sync=False,
            dry_run=True,
        )
        db.rollback()  # Preview — no changes committed
        return SyncPreviewOut(
            tasks_created_remote=sync_run.tasks_created,
            tasks_updated_remote=sync_run.tasks_updated,
            events_created_remote=sync_run.calendar_created,
            events_updated_remote=sync_run.calendar_updated,
            conflicts_detected=sync_run.conflicts_detected,
        )
    except Exception as exc:
        logger.error("Sync preview error for account %d: %s", account_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{account_id}/sync-history", response_model=List[SyncRunOut], summary="Get sync history")
def get_sync_history(
    account_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    runs = (
        db.query(MsSyncRun)
        .filter(MsSyncRun.account_id == account_id)
        .order_by(MsSyncRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [SyncRunOut.model_validate(r) for r in runs]
