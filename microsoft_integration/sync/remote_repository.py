"""Remote repository — reads/writes Microsoft Graph resources.

Thin layer over graph/calendar.py and graph/todo.py that converts
raw Graph API dicts into internal DTOs.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from microsoft_integration.graph import calendar as cal_api
from microsoft_integration.graph import todo as todo_api
from microsoft_integration.graph.client import GraphClient
from microsoft_integration.schemas import RemoteEventDTO, RemoteTodoDTO

logger = logging.getLogger("microsoft.sync.remote_repository")


# ---------------------------------------------------------------------------
# Calendar event helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: Optional[Dict[str, Any]]) -> Optional[datetime]:
    if not value:
        return None
    dt_str = value.get("dateTime", "")
    if not dt_str:
        return None
    try:
        # Strip trailing Z or timezone for naive UTC
        dt_str = dt_str.replace("Z", "").split("+")[0].split(".")[0]
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def _graph_event_to_dto(item: Dict[str, Any], calendar_id: str) -> RemoteEventDTO:
    body = item.get("body", {})
    location = (item.get("location") or {}).get("displayName")
    ext_list = (item.get("extensions") or {}).get("value", [])
    if isinstance(item.get("extensions"), list):
        ext_list = item["extensions"]
    milo_ext = None
    for ext in ext_list:
        if isinstance(ext, dict) and ext.get("extensionName") == "com.milo.sync":
            milo_ext = ext

    is_deleted = item.get("@removed") is not None

    return RemoteEventDTO(
        id=item.get("id", ""),
        calendar_id=calendar_id,
        subject=item.get("subject", ""),
        body=body.get("content") if body else None,
        start=_parse_dt(item.get("start")),
        end=_parse_dt(item.get("end")),
        is_all_day=bool(item.get("isAllDay", False)),
        location=location,
        recurrence=item.get("recurrence"),
        categories=item.get("categories", []),
        last_modified=_parse_dt({"dateTime": item.get("lastModifiedDateTime", "")}),
        etag=item.get("@odata.etag"),
        milo_extension=milo_ext,
        is_deleted=is_deleted,
    )


def _graph_task_to_dto(item: Dict[str, Any], list_id: str) -> RemoteTodoDTO:
    ext_list = (item.get("extensions") or {}).get("value", [])
    if isinstance(item.get("extensions"), list):
        ext_list = item["extensions"]
    milo_ext = None
    for ext in ext_list:
        if isinstance(ext, dict) and ext.get("extensionName") == "com.milo.sync":
            milo_ext = ext

    return RemoteTodoDTO(
        id=item.get("id", ""),
        list_id=list_id,
        title=item.get("title", ""),
        body=(item.get("body") or {}).get("content"),
        due_date_time=_parse_dt(item.get("dueDateTime")),
        status=item.get("status", "notStarted"),
        completed_date_time=_parse_dt(item.get("completedDateTime")),
        recurrence=item.get("recurrence"),
        categories=item.get("categories", []),
        last_modified=_parse_dt({"dateTime": item.get("lastModifiedDateTime", "")}),
        etag=item.get("@odata.etag"),
        milo_extension=milo_ext,
    )


# ---------------------------------------------------------------------------
# Remote repository public interface
# ---------------------------------------------------------------------------


async def fetch_all_events(
    client: GraphClient,
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> List[RemoteEventDTO]:
    items = await cal_api.list_events(client, calendar_id, start, end)
    return [_graph_event_to_dto(item, calendar_id) for item in items]


async def fetch_delta_events(
    client: GraphClient,
    calendar_id: str,
    delta_link: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Tuple[List[RemoteEventDTO], Optional[str]]:
    items, new_delta = await cal_api.delta_events(
        client, calendar_id, delta_link=delta_link, start=start, end=end
    )
    dtos = [_graph_event_to_dto(item, calendar_id) for item in items]
    return dtos, new_delta


async def fetch_all_tasks(
    client: GraphClient, list_id: str
) -> List[RemoteTodoDTO]:
    items = await todo_api.list_tasks(client, list_id)
    return [_graph_task_to_dto(item, list_id) for item in items]


async def fetch_delta_tasks(
    client: GraphClient,
    list_id: str,
    delta_link: Optional[str] = None,
) -> Tuple[List[RemoteTodoDTO], Optional[str]]:
    items, new_delta = await todo_api.delta_tasks(client, list_id, delta_link=delta_link)
    dtos = [_graph_task_to_dto(item, list_id) for item in items]
    return dtos, new_delta
