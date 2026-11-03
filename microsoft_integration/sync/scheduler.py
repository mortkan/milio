"""APScheduler-based sync scheduler for Microsoft integration.

Runs a periodic sync for all accounts according to MICROSOFT_SYNC_INTERVAL_SECONDS.
Uses asyncio scheduler to avoid blocking the FastAPI event loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from microsoft_integration.config import MicrosoftSettings
from microsoft_integration.sync.engine import SyncEngineConfig, run_sync_for_all_accounts

logger = logging.getLogger("microsoft.sync.scheduler")

_scheduler: Optional[AsyncIOScheduler] = None
_sync_config: Optional[SyncEngineConfig] = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def start_scheduler(config: SyncEngineConfig) -> AsyncIOScheduler:
    """Initialize and start the APScheduler async scheduler."""
    global _scheduler, _sync_config
    _sync_config = config

    if _scheduler and _scheduler.running:
        logger.warning("Scheduler already running — not starting again")
        return _scheduler

    _scheduler = AsyncIOScheduler()

    interval_seconds = config.settings.microsoft_sync_interval_seconds
    _scheduler.add_job(
        _scheduled_sync,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id="ms_sync_all_accounts",
        name="Microsoft 365 sync",
        replace_existing=True,
        coalesce=True,  # skip missed executions when restarting
        max_instances=1,  # never run two at the same time
    )

    _scheduler.start()
    logger.info(
        "Microsoft sync scheduler started (interval=%ds)", interval_seconds
    )
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Microsoft sync scheduler stopped")
    _scheduler = None


async def _scheduled_sync() -> None:
    """Callback executed by the scheduler."""
    if _sync_config is None:
        logger.warning("Sync config not available — skipping scheduled sync")
        return
    try:
        logger.info("Scheduled sync starting...")
        await run_sync_for_all_accounts(_sync_config)
        logger.info("Scheduled sync complete")
    except Exception as exc:
        logger.error("Scheduled sync error: %s", exc)
