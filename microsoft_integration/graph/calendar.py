"""Microsoft Graph: Outlook Calendar operations.

All calendar operations use the v1.0 endpoint.
Immutable IDs are requested where applicable via the GraphClient header.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from microsoft_integration.graph.client import GraphClient
from microsoft_integration.graph.errors import GraphNotFoundError

logger = logging.getLogger("microsoft.graph.calendar")


# ---------------------------------------------------------------------------
# Calendar management
# ---------------------------------------------------------------------------


async def list_calendars(client: GraphClient) -> List[Dict[str, Any]]:
    """List all calendars accessible to the user."""
    return await client.get_all(
        "/me/calendars",
        params={"$select": "id,name,isDefaultCalendar,canEdit,color,hexColor"},
    )


async def get_calendar_by_name(
    client: GraphClient, name: str
) -> Optional[Dict[str, Any]]:
    """Find a calendar by name. Returns None if not found."""
    calendars = await list_calendars(client)
    for cal in calendars:
        if cal.get("name", "").lower() == name.lower():
            return cal
    return None


async def create_calendar(client: GraphClient, name: str) -> Dict[str, Any]:
    """Create a new Outlook calendar."""
    return await client.post("/me/calendars", json={"name": name})


async def get_or_create_milo_calendar(
    client: GraphClient, calendar_name: str = "Milo"
) -> Dict[str, Any]:
    """Get the Milo calendar or create it if it doesn't exist."""
    cal = await get_calendar_by_name(client, calendar_name)
    if cal:
        logger.info("Found existing calendar: %s (%s)", cal["name"], cal["id"])
        return cal
    logger.info("Creating calendar: %s", calendar_name)
    return await create_calendar(client, calendar_name)


# ---------------------------------------------------------------------------
# Event operations
# ---------------------------------------------------------------------------


async def list_events(
    client: GraphClient,
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    """List events in a calendar within a time window."""
    start_str = start.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end.strftime("%Y-%m-%dT%H:%M:%S")
    return await client.get_all(
        f"/me/calendars/{calendar_id}/events",
        params={
            "$filter": f"start/dateTime ge '{start_str}' and end/dateTime le '{end_str}'",
            "$select": (
                "id,subject,body,start,end,isAllDay,location,recurrence,"
                "categories,lastModifiedDateTime,changeKey,extensions"
            ),
            "$expand": "extensions($filter=id eq 'com.milo.sync')",
        },
    )


async def get_event(
    client: GraphClient, calendar_id: str, event_id: str
) -> Optional[Dict[str, Any]]:
    """Fetch a single event. Returns None if not found."""
    try:
        return await client.get(
            f"/me/calendars/{calendar_id}/events/{event_id}",
            params={
                "$select": (
                    "id,subject,body,start,end,isAllDay,location,recurrence,"
                    "categories,lastModifiedDateTime,changeKey,extensions"
                ),
                "$expand": "extensions($filter=id eq 'com.milo.sync')",
            },
        )
    except GraphNotFoundError:
        return None


async def create_event(
    client: GraphClient, calendar_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a new event in the calendar."""
    return await client.post(f"/me/calendars/{calendar_id}/events", json=payload)


async def update_event(
    client: GraphClient, calendar_id: str, event_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """PATCH an existing event with only the fields Milo controls."""
    return await client.patch(
        f"/me/calendars/{calendar_id}/events/{event_id}", json=payload
    )


async def delete_event(
    client: GraphClient, calendar_id: str, event_id: str
) -> None:
    """Delete an event from the calendar."""
    await client.delete(f"/me/calendars/{calendar_id}/events/{event_id}")


# ---------------------------------------------------------------------------
# Delta sync
# ---------------------------------------------------------------------------


async def delta_events(
    client: GraphClient,
    calendar_id: str,
    delta_link: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch changed events using delta query.

    Returns:
        Tuple of (list of changed items, new delta_link to save).
    """
    if delta_link:
        # Resume incremental sync
        path = delta_link
        params = None
    else:
        # First delta sync — define the window
        path = f"/me/calendars/{calendar_id}/events/delta"
        params = {
            "$select": (
                "id,subject,body,start,end,isAllDay,location,recurrence,"
                "categories,lastModifiedDateTime,changeKey,extensions"
            ),
        }
        if start:
            params["startDateTime"] = start.strftime("%Y-%m-%dT%H:%M:%S")
        if end:
            params["endDateTime"] = end.strftime("%Y-%m-%dT%H:%M:%S")

    items, new_delta_link = await client.iter_delta(path, params=params if not delta_link else None)
    return items, new_delta_link
