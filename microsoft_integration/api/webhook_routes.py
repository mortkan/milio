"""Webhook routes for Microsoft Graph change notifications.

Disabled by default (MICROSOFT_WEBHOOK_ENABLED=false).
When enabled, provides endpoints for Graph validation and notification processing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

logger = logging.getLogger("microsoft.api.webhook_routes")

router = APIRouter(prefix="/api/microsoft/webhooks", tags=["Microsoft Webhooks"])


@router.post(
    "/graph",
    summary="Receive Microsoft Graph change notifications",
)
async def receive_graph_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    validationToken: str | None = Query(default=None),
):
    """Graph notification endpoint.

    During subscription creation, Graph sends a GET/POST with validationToken
    that must be echoed back within 10 seconds to confirm the endpoint.

    For actual notifications, the body contains a list of change events.
    Heavy processing is offloaded to a background task.
    """
    if validationToken:
        # Validation handshake — respond within 10 seconds
        return Response(content=validationToken, media_type="text/plain", status_code=200)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    notifications = body.get("value", [])
    logger.info("Received %d Graph notification(s)", len(notifications))

    for notification in notifications:
        background_tasks.add_task(_process_notification, notification)

    # Must respond quickly to Graph
    return Response(status_code=202)


@router.post(
    "/lifecycle",
    summary="Receive Microsoft Graph lifecycle notifications",
)
async def receive_lifecycle_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    validationToken: str | None = Query(default=None),
):
    """Handle subscription lifecycle events (reauthorizationRequired, subscriptionRemoved, missed)."""
    if validationToken:
        return Response(content=validationToken, media_type="text/plain", status_code=200)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    notifications = body.get("value", [])
    for notification in notifications:
        background_tasks.add_task(_process_lifecycle_notification, notification)

    return Response(status_code=202)


async def _process_notification(notification: Dict[str, Any]) -> None:
    """Background: validate client_state and trigger an incremental sync."""
    try:
        expected_state = notification.get("clientState", "")
        # Validate clientState
        from microsoft_integration.models import MsSubscription
        from microsoft_integration.database import get_db_session
        with get_db_session() as db:
            sub = (
                db.query(MsSubscription)
                .filter(MsSubscription.subscription_id == notification.get("subscriptionId", ""))
                .first()
            )
            if sub and sub.client_state != expected_state:
                logger.warning(
                    "Graph notification clientState mismatch — ignoring notification"
                )
                return

            account_id = sub.account_id if sub else None

        if account_id:
            from microsoft_integration.main import get_sync_config
            from microsoft_integration.sync.engine import run_sync_for_account
            config = get_sync_config()
            with get_db_session() as db:
                await run_sync_for_account(
                    account_id=account_id,
                    config=config,
                    db=db,
                    is_full_sync=False,
                )
                db.commit()
    except Exception as exc:
        logger.error("Error processing Graph notification: %s", exc)


async def _process_lifecycle_notification(notification: Dict[str, Any]) -> None:
    """Handle lifecycle events: missed notifications → force delta sync."""
    try:
        lifecycle_event = notification.get("lifecycleEvent", "")
        logger.info("Graph lifecycle event: %s", lifecycle_event)

        if lifecycle_event in ("missed", "subscriptionRemoved"):
            # Force a delta sync to catch up
            sub_id = notification.get("subscriptionId", "")
            from microsoft_integration.models import MsSubscription
            from microsoft_integration.database import get_db_session
            with get_db_session() as db:
                sub = (
                    db.query(MsSubscription)
                    .filter(MsSubscription.subscription_id == sub_id)
                    .first()
                )
                if sub:
                    sub.status = "expired"
                    db.commit()
                    from microsoft_integration.main import get_sync_config
                    from microsoft_integration.sync.engine import run_sync_for_account
                    config = get_sync_config()
                    with get_db_session() as db2:
                        await run_sync_for_account(
                            account_id=sub.account_id,
                            config=config,
                            db=db2,
                            is_full_sync=False,
                        )
                        db2.commit()
    except Exception as exc:
        logger.error("Error processing lifecycle notification: %s", exc)
