"""Sync orchestration engine.

Coordinates calendar and To Do sync for one or all accounts.
Called by the scheduler and by manual sync API endpoints.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from microsoft_integration.auth.encryption import TokenEncryptor
from microsoft_integration.auth.msal_client import create_public_client
from microsoft_integration.auth.token_cache import PersistedTokenCache
from microsoft_integration.config import MicrosoftSettings
from microsoft_integration.database import get_db_session
from microsoft_integration.graph import calendar as cal_api
from microsoft_integration.graph import todo as todo_api
from microsoft_integration.graph.client import GraphClient
from microsoft_integration.graph.errors import GraphAuthError
from microsoft_integration.models import MsAccount, MsSyncRun, MsSyncTarget
from microsoft_integration.sync import calendar_sync, todo_sync
from microsoft_integration.sync.locks import sync_lock

logger = logging.getLogger("microsoft.sync.engine")


@dataclass
class SyncEngineConfig:
    settings: MicrosoftSettings
    encryptor: TokenEncryptor


async def run_sync_for_account(
    *,
    account_id: int,
    config: SyncEngineConfig,
    db: Session,
    is_full_sync: bool = False,
    dry_run: bool = False,
) -> MsSyncRun:
    """Run a complete sync cycle for one account.

    Creates an ms_sync_runs record and updates it on completion.
    """
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account or not account.enabled:
        logger.info("Account %d not found or disabled — skipping sync", account_id)
        return _make_failed_run(db, account_id, "Account not found or disabled")

    if account.needs_reauthentication:
        logger.warning("Account %d needs re-authentication — skipping sync", account_id)
        return _make_failed_run(db, account_id, "Needs re-authentication")

    sync_run = MsSyncRun(
        account_id=account_id,
        started_at=datetime.utcnow(),
        status="running",
        is_full_sync=is_full_sync,
        is_dry_run=dry_run,
    )
    db.add(sync_run)
    db.flush()

    try:
        # Build Graph client for this account
        persisted_cache = PersistedTokenCache(account_id, config.encryptor, db)
        async with GraphClient(config.settings, persisted_cache) as client:

            # ---- Calendar targets ----------------------------------------
            calendar_targets = (
                db.query(MsSyncTarget)
                .filter(
                    MsSyncTarget.account_id == account_id,
                    MsSyncTarget.target_type == "calendar",
                    MsSyncTarget.enabled.is_(True),
                )
                .all()
            )

            for target in calendar_targets:
                with sync_lock(db, account_id, f"calendar_{target.remote_id}") as acquired:
                    if not acquired:
                        logger.info("Calendar sync already running for account %d", account_id)
                        continue

                    cal_result = await calendar_sync.sync_calendar(
                        account_id=account_id,
                        calendar_id=target.remote_id,
                        client=client,
                        db=db,
                        settings=config.settings,
                        sync_direction=target.sync_direction,
                        is_full_sync=is_full_sync,
                        dry_run=dry_run,
                        conflict_policy="manual",
                    )
                    sync_run.calendar_created += cal_result.created_remote + cal_result.created_local
                    sync_run.calendar_updated += cal_result.updated_remote + cal_result.updated_local
                    sync_run.calendar_deleted += cal_result.deleted_remote + cal_result.deleted_local
                    sync_run.conflicts_detected += cal_result.conflicts
                    sync_run.errors_count += cal_result.errors

            # ---- To Do targets -------------------------------------------
            todo_targets = (
                db.query(MsSyncTarget)
                .filter(
                    MsSyncTarget.account_id == account_id,
                    MsSyncTarget.target_type == "todo_list",
                    MsSyncTarget.enabled.is_(True),
                )
                .all()
            )

            for target in todo_targets:
                with sync_lock(db, account_id, f"todo_{target.remote_id}") as acquired:
                    if not acquired:
                        logger.info("Todo sync already running for account %d", account_id)
                        continue

                    todo_result = await todo_sync.sync_todo_list(
                        account_id=account_id,
                        list_id=target.remote_id,
                        client=client,
                        db=db,
                        sync_direction=target.sync_direction,
                        is_full_sync=is_full_sync,
                        dry_run=dry_run,
                        conflict_policy="manual",
                    )
                    sync_run.tasks_created += todo_result.created_remote + todo_result.created_local
                    sync_run.tasks_updated += todo_result.updated_remote + todo_result.updated_local
                    sync_run.tasks_deleted += todo_result.deleted_remote + todo_result.deleted_local
                    sync_run.conflicts_detected += todo_result.conflicts
                    sync_run.errors_count += todo_result.errors

        sync_run.status = "partial" if sync_run.errors_count > 0 else "success"
        sync_run.finished_at = datetime.utcnow()
        db.flush()

        logger.info(
            "Sync complete for account %d: cal_created=%d cal_updated=%d "
            "tasks_created=%d tasks_updated=%d conflicts=%d errors=%d",
            account_id,
            sync_run.calendar_created,
            sync_run.calendar_updated,
            sync_run.tasks_created,
            sync_run.tasks_updated,
            sync_run.conflicts_detected,
            sync_run.errors_count,
        )

    except GraphAuthError as exc:
        logger.error("Auth error during sync for account %d: %s", account_id, exc)
        account.needs_reauthentication = True
        db.flush()
        sync_run.status = "failed"
        sync_run.errors_count += 1
        sync_run.finished_at = datetime.utcnow()
        db.flush()

    except Exception as exc:
        logger.error("Unexpected error during sync for account %d: %s", account_id, exc)
        sync_run.status = "failed"
        sync_run.errors_count += 1
        sync_run.finished_at = datetime.utcnow()
        db.flush()

    return sync_run


def _make_failed_run(db: Session, account_id: int, reason: str) -> MsSyncRun:
    run = MsSyncRun(
        account_id=account_id,
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        status="failed",
        errors_count=1,
    )
    db.add(run)
    db.flush()
    return run


async def run_sync_for_all_accounts(config: SyncEngineConfig) -> None:
    """Triggered by the scheduler — sync all enabled accounts."""
    with get_db_session() as db:
        accounts = (
            db.query(MsAccount)
            .filter(
                MsAccount.enabled.is_(True),
                MsAccount.needs_reauthentication.is_(False),
            )
            .all()
        )
        for account in accounts:
            try:
                await run_sync_for_account(
                    account_id=account.id,
                    config=config,
                    db=db,
                    is_full_sync=False,
                    dry_run=False,
                )
                db.commit()
            except Exception as exc:
                logger.error("Scheduler sync failed for account %d: %s", account.id, exc)
                db.rollback()
