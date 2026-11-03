"""Calendar synchronization engine.

Implements bidirectional sync between Milo events and Outlook Calendar.
Supports:
- First full sync with configurable time window
- Delta incremental sync
- Conflict detection and resolution
- Immutable IDs (via GraphClient header)
- Deletion handling via tombstones
- Idempotency
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from microsoft_integration.config import MicrosoftSettings
from microsoft_integration.graph import calendar as cal_api
from microsoft_integration.graph.client import GraphClient
from microsoft_integration.graph.extensions import add_extension_to_event
from microsoft_integration.models import MsEntityLink, MsSyncState
from microsoft_integration.schemas import LocalEventDTO, RemoteEventDTO
from microsoft_integration.sync import conflict_resolver, local_repository, mapping, remote_repository

logger = logging.getLogger("microsoft.sync.calendar_sync")


@dataclass
class CalendarSyncResult:
    created_remote: int = 0
    updated_remote: int = 0
    created_local: int = 0
    updated_local: int = 0
    deleted_remote: int = 0
    deleted_local: int = 0
    conflicts: int = 0
    errors: int = 0
    dry_run: bool = False
    details: List[str] = field(default_factory=list)


async def sync_calendar(
    *,
    account_id: int,
    calendar_id: str,
    client: GraphClient,
    db: Session,
    settings: MicrosoftSettings,
    sync_direction: str = "bidirectional",
    is_full_sync: bool = False,
    dry_run: bool = False,
    conflict_policy: str = "manual",
) -> CalendarSyncResult:
    """Main entry point for Outlook Calendar synchronization."""
    result = CalendarSyncResult(dry_run=dry_run)

    # ---- Define sync window ------------------------------------------------
    now = datetime.utcnow()
    window_start = now - timedelta(days=settings.microsoft_sync_lookback_days)
    window_end = now + timedelta(days=settings.microsoft_sync_lookahead_days)

    # ---- Fetch remote state ------------------------------------------------
    sync_state = _get_or_create_sync_state(db, account_id, "calendar", calendar_id)
    delta_link = None if is_full_sync else sync_state.delta_link

    try:
        remote_events, new_delta_link = await remote_repository.fetch_delta_events(
            client,
            calendar_id,
            delta_link=delta_link,
            start=window_start if not delta_link else None,
            end=window_end if not delta_link else None,
        )
        logger.info(
            "Calendar delta: %d changes returned (account=%d calendar=%s)",
            len(remote_events),
            account_id,
            calendar_id,
        )
    except Exception as exc:
        from microsoft_integration.graph.errors import GraphDeltaExpiredError
        if isinstance(exc, GraphDeltaExpiredError):
            logger.warning("Delta expired for calendar %s — forcing full sync", calendar_id)
            sync_state.delta_link = None
            remote_events, new_delta_link = await remote_repository.fetch_delta_events(
                client, calendar_id, delta_link=None, start=window_start, end=window_end
            )
        else:
            logger.error("Failed to fetch remote events: %s", exc)
            result.errors += 1
            return result

    # ---- Fetch local state --------------------------------------------------
    local_events: List[LocalEventDTO] = local_repository.list_all_events(db)
    local_event_map: Dict[int, LocalEventDTO] = {e.id: e for e in local_events}

    # ---- Build remote map --------------------------------------------------
    remote_event_map: Dict[str, RemoteEventDTO] = {e.id: e for e in remote_events}

    # ---- Sync Milo → Microsoft -------------------------------------------
    if sync_direction in ("bidirectional", "milo_to_microsoft"):
        await _push_local_to_remote(
            account_id=account_id,
            calendar_id=calendar_id,
            local_event_map=local_event_map,
            client=client,
            db=db,
            result=result,
            dry_run=dry_run,
            conflict_policy=conflict_policy,
            remote_event_map=remote_event_map,
            timezone_name=settings.microsoft_timezone,
        )

    # ---- Sync Microsoft → Milo -------------------------------------------
    if sync_direction in ("bidirectional", "microsoft_to_milo"):
        await _pull_remote_to_local(
            account_id=account_id,
            calendar_id=calendar_id,
            remote_events=remote_events,
            client=client,
            db=db,
            result=result,
            dry_run=dry_run,
            conflict_policy=conflict_policy,
        )

    # ---- Save delta state --------------------------------------------------
    if not dry_run and new_delta_link:
        sync_state.delta_link = new_delta_link
        sync_state.last_sync_at = datetime.utcnow()
        sync_state.sync_window_start = window_start
        sync_state.sync_window_end = window_end
        if is_full_sync:
            sync_state.last_full_sync_at = datetime.utcnow()
        db.flush()

    return result


def _get_or_create_sync_state(
    db: Session, account_id: int, resource_type: str, resource_id: str
) -> MsSyncState:
    state = (
        db.query(MsSyncState)
        .filter(
            MsSyncState.account_id == account_id,
            MsSyncState.resource_type == resource_type,
            MsSyncState.resource_id == resource_id,
        )
        .first()
    )
    if not state:
        state = MsSyncState(
            account_id=account_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        db.add(state)
        db.flush()
    return state


def _get_link_for_local_event(
    db: Session, account_id: int, local_id: int
) -> Optional[MsEntityLink]:
    return (
        db.query(MsEntityLink)
        .filter(
            MsEntityLink.account_id == account_id,
            MsEntityLink.local_entity_type == "event",
            MsEntityLink.local_entity_id == local_id,
        )
        .first()
    )


def _get_link_for_remote_event(
    db: Session, account_id: int, remote_id: str
) -> Optional[MsEntityLink]:
    return (
        db.query(MsEntityLink)
        .filter(
            MsEntityLink.account_id == account_id,
            MsEntityLink.remote_entity_type == "calendar_event",
            MsEntityLink.remote_entity_id == remote_id,
        )
        .first()
    )


async def _push_local_to_remote(
    *,
    account_id: int,
    calendar_id: str,
    local_event_map: Dict[int, LocalEventDTO],
    client: GraphClient,
    db: Session,
    result: CalendarSyncResult,
    dry_run: bool,
    conflict_policy: str,
    remote_event_map: Dict[str, RemoteEventDTO],
    timezone_name: str,
) -> None:
    for event in local_event_map.values():
        try:
            link = _get_link_for_local_event(db, account_id, event.id)

            if link and link.remote_deleted:
                continue

            local_hash = mapping.compute_event_hash(event)

            if link:
                if link.sync_hash == local_hash:
                    continue  # No local change

                remote_dto = remote_event_map.get(link.remote_entity_id)
                if remote_dto and conflict_resolver.detect_conflict(
                    link,
                    local_updated_at=event.updated_at,
                    remote_last_modified=remote_dto.last_modified,
                ):
                    if conflict_policy == "manual":
                        conflict_resolver.record_conflict(
                            db,
                            account_id=account_id,
                            entity_link=link,
                            entity_type="event",
                            local_snapshot={"title": event.title, "start": str(event.start)},
                            remote_snapshot={"subject": remote_dto.subject, "start": str(remote_dto.start)},
                            local_modified_at=event.updated_at,
                            remote_modified_at=remote_dto.last_modified,
                        )
                        result.conflicts += 1
                        continue
                    elif conflict_policy == "keep_microsoft":
                        continue

                if dry_run:
                    result.updated_remote += 1
                    result.details.append(f"Would update remote event for local event {event.id}")
                    continue

                payload = mapping.event_to_graph_payload(event, timezone_name)
                await cal_api.update_event(client, calendar_id, link.remote_entity_id, payload)
                link.sync_hash = local_hash
                link.local_last_modified = event.updated_at
                link.last_synced_at = datetime.utcnow()
                db.flush()
                result.updated_remote += 1

            else:
                if dry_run:
                    result.created_remote += 1
                    result.details.append(f"Would create remote event for local event {event.id}")
                    continue

                payload = mapping.event_to_graph_payload(event, timezone_name)
                created = await cal_api.create_event(client, calendar_id, payload)
                remote_id = created["id"]

                await add_extension_to_event(client, calendar_id, remote_id, event.id)

                new_link = MsEntityLink(
                    account_id=account_id,
                    local_entity_type="event",
                    local_entity_id=event.id,
                    remote_entity_type="calendar_event",
                    remote_entity_id=remote_id,
                    remote_container_id=calendar_id,
                    sync_hash=local_hash,
                    local_last_modified=event.updated_at,
                    last_synced_at=datetime.utcnow(),
                )
                db.add(new_link)
                db.flush()
                result.created_remote += 1
                logger.info("Created remote event %s for local event %d", remote_id, event.id)

        except Exception as exc:
            logger.error("Error pushing local event %d: %s", event.id, exc)
            result.errors += 1


async def _pull_remote_to_local(
    *,
    account_id: int,
    calendar_id: str,
    remote_events: List[RemoteEventDTO],
    client: GraphClient,
    db: Session,
    result: CalendarSyncResult,
    dry_run: bool,
    conflict_policy: str,
) -> None:
    for event in remote_events:
        try:
            link = _get_link_for_remote_event(db, account_id, event.id)

            # Handle deletion
            if event.is_deleted:
                if link and not link.remote_deleted:
                    link.remote_deleted = True
                    link.last_synced_at = datetime.utcnow()
                    if not dry_run:
                        local_repository.soft_delete_event(db, link.local_entity_id)
                        db.flush()
                        result.deleted_local += 1
                continue

            if link:
                if link.last_synced_at and event.last_modified and event.last_modified <= link.last_synced_at:
                    continue

                if dry_run:
                    result.updated_local += 1
                    result.details.append(f"Would update local event from remote {event.id}")
                    continue

                local_fields = mapping.graph_event_to_local_fields({
                    "subject": event.subject,
                    "body": {"content": event.body},
                    "start": {"dateTime": event.start.isoformat()} if event.start else None,
                    "end": {"dateTime": event.end.isoformat()} if event.end else None,
                    "isAllDay": event.is_all_day,
                    "location": {"displayName": event.location} if event.location else None,
                    "recurrence": event.recurrence,
                })
                local_repository.update_event(
                    db, link.local_entity_id, title=local_fields.get("title")
                )
                link.remote_last_modified = event.last_modified
                link.remote_etag = event.etag
                link.last_synced_at = datetime.utcnow()
                db.flush()
                result.updated_local += 1

            else:
                if event.milo_extension:
                    milo_id_str = event.milo_extension.get("miloEntityId")
                    if milo_id_str:
                        try:
                            milo_id = int(milo_id_str)
                            new_link = MsEntityLink(
                                account_id=account_id,
                                local_entity_type="event",
                                local_entity_id=milo_id,
                                remote_entity_type="calendar_event",
                                remote_entity_id=event.id,
                                remote_container_id=calendar_id,
                                remote_last_modified=event.last_modified,
                                remote_etag=event.etag,
                                last_synced_at=datetime.utcnow(),
                            )
                            db.add(new_link)
                            db.flush()
                        except (ValueError, TypeError):
                            pass
                    continue

                if dry_run:
                    result.created_local += 1
                    result.details.append(f"Would create local event from remote {event.id}")
                    continue

                local_fields = mapping.graph_event_to_local_fields({
                    "subject": event.subject,
                    "body": {"content": event.body},
                    "start": {"dateTime": event.start.isoformat()} if event.start else None,
                    "end": {"dateTime": event.end.isoformat()} if event.end else None,
                    "isAllDay": event.is_all_day,
                    "location": {"displayName": event.location} if event.location else None,
                    "recurrence": event.recurrence,
                })
                local_id = local_repository.create_event(
                    db,
                    title=local_fields.get("title", ""),
                    description=local_fields.get("description") or "",
                    start=local_fields.get("start"),
                )
                new_link = MsEntityLink(
                    account_id=account_id,
                    local_entity_type="event",
                    local_entity_id=local_id,
                    remote_entity_type="calendar_event",
                    remote_entity_id=event.id,
                    remote_container_id=calendar_id,
                    remote_last_modified=event.last_modified,
                    remote_etag=event.etag,
                    last_synced_at=datetime.utcnow(),
                )
                db.add(new_link)
                db.flush()
                result.created_local += 1
                logger.info("Created local event %d from remote %s", local_id, event.id)

        except Exception as exc:
            logger.error("Error pulling remote event %s: %s", event.id, exc)
            result.errors += 1
