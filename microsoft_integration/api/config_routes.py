"""Account configuration routes (calendar/todo preferences)."""
from __future__ import annotations

import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from microsoft_integration.auth.encryption import TokenEncryptor
from microsoft_integration.auth.msal_client import create_public_client
from microsoft_integration.auth.token_cache import PersistedTokenCache
from microsoft_integration.database import get_db
from microsoft_integration.graph import calendar as cal_api
from microsoft_integration.graph import todo as todo_api
from microsoft_integration.graph.client import GraphClient
from microsoft_integration.models import MsAccount, MsSyncTarget
from microsoft_integration.schemas import (
    AccountConfigIn,
    AccountConfigOut,
    CalendarOut,
    SyncTargetOut,
    TodoListOut,
)

logger = logging.getLogger("microsoft.api.config_routes")

router = APIRouter(prefix="/api/microsoft/accounts", tags=["Microsoft Config"])


def _get_settings():
    from microsoft_integration.main import get_settings
    return get_settings()


def _get_encryptor():
    from microsoft_integration.main import get_encryptor
    return get_encryptor()


@router.get("/{account_id}/calendars", response_model=List[CalendarOut], summary="List Outlook calendars")
async def list_calendars(
    account_id: int,
    db: Session = Depends(get_db),
    settings=Depends(_get_settings),
    encryptor: TokenEncryptor = Depends(_get_encryptor),
):
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account or not account.enabled:
        raise HTTPException(status_code=404, detail="Account not found or disabled")

    persisted_cache = PersistedTokenCache(account_id, encryptor, db)
    async with GraphClient(settings, persisted_cache) as client:
        calendars = await cal_api.list_calendars(client)

    return [
        CalendarOut(
            id=c["id"],
            name=c.get("name", ""),
            is_default=bool(c.get("isDefaultCalendar", False)),
            can_edit=bool(c.get("canEdit", True)),
        )
        for c in calendars
    ]


@router.get("/{account_id}/todo-lists", response_model=List[TodoListOut], summary="List Microsoft To Do lists")
async def list_todo_lists(
    account_id: int,
    db: Session = Depends(get_db),
    settings=Depends(_get_settings),
    encryptor: TokenEncryptor = Depends(_get_encryptor),
):
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account or not account.enabled:
        raise HTTPException(status_code=404, detail="Account not found or disabled")

    persisted_cache = PersistedTokenCache(account_id, encryptor, db)
    async with GraphClient(settings, persisted_cache) as client:
        lists = await todo_api.list_todo_lists(client)

    return [
        TodoListOut(
            id=lst["id"],
            display_name=lst.get("displayName", ""),
            is_owner=bool(lst.get("isOwner", True)),
        )
        for lst in lists
    ]


@router.get("/{account_id}/config", response_model=AccountConfigOut, summary="Get sync configuration")
def get_account_config(account_id: int, db: Session = Depends(get_db)):
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    cal_target = (
        db.query(MsSyncTarget)
        .filter(
            MsSyncTarget.account_id == account_id,
            MsSyncTarget.target_type == "calendar",
        )
        .first()
    )
    todo_target = (
        db.query(MsSyncTarget)
        .filter(
            MsSyncTarget.account_id == account_id,
            MsSyncTarget.target_type == "todo_list",
        )
        .first()
    )

    from microsoft_integration.config import get_settings as _gs
    s = _gs()

    return AccountConfigOut(
        account_id=account_id,
        calendar_sync_enabled=cal_target.enabled if cal_target else False,
        todo_sync_enabled=todo_target.enabled if todo_target else False,
        calendar_id=cal_target.remote_id if cal_target else None,
        calendar_name=cal_target.remote_name if cal_target else None,
        todo_list_id=todo_target.remote_id if todo_target else None,
        todo_list_name=todo_target.remote_name if todo_target else None,
        calendar_sync_direction=cal_target.sync_direction if cal_target else "bidirectional",
        todo_sync_direction=todo_target.sync_direction if todo_target else "bidirectional",
        sync_interval_seconds=s.microsoft_sync_interval_seconds,
    )


@router.put("/{account_id}/config", response_model=AccountConfigOut, summary="Update sync configuration")
def update_account_config(
    account_id: int,
    config_in: AccountConfigIn,
    db: Session = Depends(get_db),
):
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Update calendar target
    if config_in.calendar_id is not None:
        cal_target = (
            db.query(MsSyncTarget)
            .filter(
                MsSyncTarget.account_id == account_id,
                MsSyncTarget.target_type == "calendar",
            )
            .first()
        )
        if cal_target:
            cal_target.remote_id = config_in.calendar_id
            if config_in.calendar_name:
                cal_target.remote_name = config_in.calendar_name
            if config_in.calendar_sync_enabled is not None:
                cal_target.enabled = config_in.calendar_sync_enabled
            if config_in.calendar_sync_direction:
                cal_target.sync_direction = config_in.calendar_sync_direction
        else:
            cal_target = MsSyncTarget(
                account_id=account_id,
                target_type="calendar",
                remote_id=config_in.calendar_id,
                remote_name=config_in.calendar_name or "",
                enabled=config_in.calendar_sync_enabled if config_in.calendar_sync_enabled is not None else True,
                sync_direction=config_in.calendar_sync_direction or "bidirectional",
            )
            db.add(cal_target)

    # Update To Do target
    if config_in.todo_list_id is not None:
        todo_target = (
            db.query(MsSyncTarget)
            .filter(
                MsSyncTarget.account_id == account_id,
                MsSyncTarget.target_type == "todo_list",
            )
            .first()
        )
        if todo_target:
            todo_target.remote_id = config_in.todo_list_id
            if config_in.todo_list_name:
                todo_target.remote_name = config_in.todo_list_name
            if config_in.todo_sync_enabled is not None:
                todo_target.enabled = config_in.todo_sync_enabled
            if config_in.todo_sync_direction:
                todo_target.sync_direction = config_in.todo_sync_direction
        else:
            todo_target = MsSyncTarget(
                account_id=account_id,
                target_type="todo_list",
                remote_id=config_in.todo_list_id,
                remote_name=config_in.todo_list_name or "",
                enabled=config_in.todo_sync_enabled if config_in.todo_sync_enabled is not None else True,
                sync_direction=config_in.todo_sync_direction or "bidirectional",
            )
            db.add(todo_target)

    db.commit()
    return get_account_config(account_id, db)
