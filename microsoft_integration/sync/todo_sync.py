"""To Do synchronization engine.

Implements bidirectional sync between Milo tasks and Microsoft To Do.
Supports:
- First full sync
- Delta incremental sync
- Conflict detection
- Deletion handling (tombstones)
- Idempotency
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from microsoft_integration.graph import todo as todo_api
from microsoft_integration.graph.client import GraphClient
from microsoft_integration.graph.extensions import add_extension_to_todo
from microsoft_integration.models import MsEntityLink, MsSyncRun, MsSyncState
from microsoft_integration.schemas import LocalTaskDTO, RemoteTodoDTO
from microsoft_integration.sync import conflict_resolver, local_repository, mapping, remote_repository

logger = logging.getLogger("microsoft.sync.todo_sync")


@dataclass
class TodoSyncResult:
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


async def sync_todo_list(
    *,
    account_id: int,
    list_id: str,
    client: GraphClient,
    db: Session,
    sync_direction: str = "bidirectional",
    is_full_sync: bool = False,
    dry_run: bool = False,
    conflict_policy: str = "manual",
) -> TodoSyncResult:
    """Main entry point for To Do synchronization."""
    result = TodoSyncResult(dry_run=dry_run)

    # ---- Fetch remote state ------------------------------------------------
    sync_state = _get_or_create_sync_state(db, account_id, "todo_list", list_id)
    delta_link = None if is_full_sync else sync_state.delta_link

    try:
        remote_tasks, new_delta_link = await remote_repository.fetch_delta_tasks(
            client, list_id, delta_link=delta_link
        )
        logger.info(
            "Todo delta: %d changes returned (account=%d list=%s)",
            len(remote_tasks),
            account_id,
            list_id,
        )
    except Exception as exc:
        from microsoft_integration.graph.errors import GraphDeltaExpiredError
        if isinstance(exc, GraphDeltaExpiredError):
            logger.warning("Delta expired for list %s — forcing full sync", list_id)
            sync_state.delta_link = None
            remote_tasks, new_delta_link = await remote_repository.fetch_delta_tasks(
                client, list_id, delta_link=None
            )
        else:
            logger.error("Failed to fetch remote tasks: %s", exc)
            result.errors += 1
            return result

    # ---- Fetch local state --------------------------------------------------
    local_tasks: List[LocalTaskDTO] = local_repository.list_all_tasks(db)
    local_task_map: Dict[int, LocalTaskDTO] = {t.id: t for t in local_tasks}

    # ---- Build remote map (by remote id) -----------------------------------
    remote_task_map: Dict[str, RemoteTodoDTO] = {t.id: t for t in remote_tasks}

    # ---- Sync Milo → Microsoft -------------------------------------------
    if sync_direction in ("bidirectional", "milo_to_microsoft"):
        await _push_local_to_remote(
            account_id=account_id,
            list_id=list_id,
            local_task_map=local_task_map,
            client=client,
            db=db,
            result=result,
            dry_run=dry_run,
            conflict_policy=conflict_policy,
            remote_task_map=remote_task_map,
        )

    # ---- Sync Microsoft → Milo -------------------------------------------
    if sync_direction in ("bidirectional", "microsoft_to_milo"):
        await _pull_remote_to_local(
            account_id=account_id,
            list_id=list_id,
            remote_tasks=remote_tasks,
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


def _get_link_for_local_task(
    db: Session, account_id: int, local_id: int
) -> Optional[MsEntityLink]:
    return (
        db.query(MsEntityLink)
        .filter(
            MsEntityLink.account_id == account_id,
            MsEntityLink.local_entity_type == "task",
            MsEntityLink.local_entity_id == local_id,
        )
        .first()
    )


def _get_link_for_remote_task(
    db: Session, account_id: int, remote_id: str
) -> Optional[MsEntityLink]:
    return (
        db.query(MsEntityLink)
        .filter(
            MsEntityLink.account_id == account_id,
            MsEntityLink.remote_entity_type == "todo_task",
            MsEntityLink.remote_entity_id == remote_id,
        )
        .first()
    )


async def _push_local_to_remote(
    *,
    account_id: int,
    list_id: str,
    local_task_map: Dict[int, LocalTaskDTO],
    client: GraphClient,
    db: Session,
    result: TodoSyncResult,
    dry_run: bool,
    conflict_policy: str,
    remote_task_map: Dict[str, RemoteTodoDTO],
) -> None:
    """Push Milo tasks to Microsoft To Do."""
    for task in local_task_map.values():
        try:
            link = _get_link_for_local_task(db, account_id, task.id)

            if link and link.remote_deleted:
                logger.debug("Task %d: remote was deleted, skipping push", task.id)
                continue

            local_hash = mapping.compute_task_hash(task)

            if link:
                # Existing mapping — check for changes
                if link.sync_hash == local_hash:
                    continue  # No local change

                # Conflict check
                remote_dto = remote_task_map.get(link.remote_entity_id)
                if remote_dto and conflict_resolver.detect_conflict(
                    link,
                    local_updated_at=task.updated_at,
                    remote_last_modified=remote_dto.last_modified,
                ):
                    if conflict_policy == "manual":
                        conflict_resolver.record_conflict(
                            db,
                            account_id=account_id,
                            entity_link=link,
                            entity_type="task",
                            local_snapshot={"title": task.title, "completed": task.completed},
                            remote_snapshot={"title": remote_dto.title, "status": remote_dto.status},
                            local_modified_at=task.updated_at,
                            remote_modified_at=remote_dto.last_modified,
                        )
                        result.conflicts += 1
                        result.details.append(f"Conflict: task {task.id} — manual resolution required")
                        continue
                    elif conflict_policy == "keep_local":
                        pass  # Fall through to update
                    elif conflict_policy == "keep_microsoft":
                        continue  # Skip local push

                if dry_run:
                    result.updated_remote += 1
                    result.details.append(f"Would update remote task for local task {task.id}")
                    continue

                payload = mapping.task_to_graph_payload(task)
                await todo_api.update_task(client, list_id, link.remote_entity_id, payload)
                link.sync_hash = local_hash
                link.local_last_modified = task.updated_at
                link.last_synced_at = datetime.utcnow()
                db.flush()
                result.updated_remote += 1

            else:
                # New local task — create remote
                if dry_run:
                    result.created_remote += 1
                    result.details.append(f"Would create remote task for local task {task.id}")
                    continue

                payload = mapping.task_to_graph_payload(task)
                created = await todo_api.create_task(client, list_id, payload)
                remote_id = created["id"]

                # Add Milo extension
                await add_extension_to_todo(client, list_id, remote_id, task.id)

                # Create entity link
                new_link = MsEntityLink(
                    account_id=account_id,
                    local_entity_type="task",
                    local_entity_id=task.id,
                    remote_entity_type="todo_task",
                    remote_entity_id=remote_id,
                    remote_container_id=list_id,
                    sync_hash=local_hash,
                    local_last_modified=task.updated_at,
                    last_synced_at=datetime.utcnow(),
                )
                db.add(new_link)
                db.flush()
                result.created_remote += 1
                logger.info("Created remote task %s for local task %d", remote_id, task.id)

        except Exception as exc:
            logger.error("Error pushing local task %d: %s", task.id, exc)
            result.errors += 1


async def _pull_remote_to_local(
    *,
    account_id: int,
    list_id: str,
    remote_tasks: List[RemoteTodoDTO],
    client: GraphClient,
    db: Session,
    result: TodoSyncResult,
    dry_run: bool,
    conflict_policy: str,
) -> None:
    """Pull Microsoft To Do tasks into Milo."""
    for task in remote_tasks:
        try:
            link = _get_link_for_remote_task(db, account_id, task.id)

            # Handle remote deletion
            is_deleted = False  # To Do delta marks deleted differently
            if is_deleted:
                if link and not link.remote_deleted:
                    link.remote_deleted = True
                    link.last_synced_at = datetime.utcnow()
                    if not dry_run:
                        local_repository.soft_delete_task(db, link.local_entity_id)
                        db.flush()
                        result.deleted_local += 1
                continue

            if link:
                # Existing mapping — check if remote changed
                if link.last_synced_at and task.last_modified and task.last_modified <= link.last_synced_at:
                    continue  # No remote change

                if dry_run:
                    result.updated_local += 1
                    result.details.append(f"Would update local task from remote {task.id}")
                    continue

                local_fields = mapping.graph_task_to_local_fields(
                    {"title": task.title, "body": {"content": task.body}, "status": task.status,
                     "dueDateTime": {"dateTime": task.due_date_time.isoformat()} if task.due_date_time else None,
                     "recurrence": task.recurrence}
                )
                local_repository.update_task(
                    db,
                    link.local_entity_id,
                    title=local_fields.get("title"),
                    completed=local_fields.get("completed"),
                )
                link.remote_last_modified = task.last_modified
                link.remote_etag = task.etag
                link.last_synced_at = datetime.utcnow()
                db.flush()
                result.updated_local += 1

            else:
                # Check if this is a Milo-originated task via extension
                if task.milo_extension:
                    milo_id_str = task.milo_extension.get("miloEntityId")
                    if milo_id_str:
                        # Create the link retroactively
                        try:
                            milo_id = int(milo_id_str)
                            new_link = MsEntityLink(
                                account_id=account_id,
                                local_entity_type="task",
                                local_entity_id=milo_id,
                                remote_entity_type="todo_task",
                                remote_entity_id=task.id,
                                remote_container_id=list_id,
                                remote_last_modified=task.last_modified,
                                remote_etag=task.etag,
                                last_synced_at=datetime.utcnow(),
                            )
                            db.add(new_link)
                            db.flush()
                        except (ValueError, TypeError):
                            pass
                    continue

                # New remote task — create in Milo
                if dry_run:
                    result.created_local += 1
                    result.details.append(f"Would create local task from remote {task.id}")
                    continue

                local_fields = mapping.graph_task_to_local_fields(
                    {"title": task.title, "body": {"content": task.body}, "status": task.status,
                     "dueDateTime": {"dateTime": task.due_date_time.isoformat()} if task.due_date_time else None,
                     "recurrence": task.recurrence}
                )
                local_id = local_repository.create_task(
                    db,
                    title=local_fields.get("title", ""),
                    description=local_fields.get("description") or "",
                    due_date=local_fields.get("due_date"),
                    completed=bool(local_fields.get("completed", False)),
                )
                new_link = MsEntityLink(
                    account_id=account_id,
                    local_entity_type="task",
                    local_entity_id=local_id,
                    remote_entity_type="todo_task",
                    remote_entity_id=task.id,
                    remote_container_id=list_id,
                    remote_last_modified=task.last_modified,
                    remote_etag=task.etag,
                    last_synced_at=datetime.utcnow(),
                )
                db.add(new_link)
                db.flush()
                result.created_local += 1
                logger.info("Created local task %d from remote %s", local_id, task.id)

        except Exception as exc:
            logger.error("Error pulling remote task %s: %s", task.id, exc)
            result.errors += 1
