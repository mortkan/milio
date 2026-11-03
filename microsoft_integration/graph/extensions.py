"""Microsoft Graph: Open extensions (com.milo.sync) for resource identification.

We add an Open Extension to each remote resource we create/manage so we can
identify which Milo entity it corresponds to, independent of title matching.
"""
from __future__ import annotations

import logging
from typing import Optional

from microsoft_integration.graph.client import GraphClient

logger = logging.getLogger("microsoft.graph.extensions")

EXTENSION_NAME = "com.milo.sync"


def make_milo_extension(
    local_entity_id: int,
    local_entity_type: str,
    milo_version: str = "1",
) -> dict:
    """Build the Open Extension payload to attach to a Graph resource."""
    return {
        "@odata.type": "microsoft.graph.openTypeExtension",
        "extensionName": EXTENSION_NAME,
        "miloEntityId": str(local_entity_id),
        "miloEntityType": local_entity_type,
        "miloVersion": milo_version,
    }


async def add_extension_to_event(
    client: GraphClient,
    calendar_id: str,
    event_id: str,
    local_entity_id: int,
) -> None:
    """Attach a Milo extension to an Outlook Calendar event."""
    try:
        payload = make_milo_extension(local_entity_id, "event")
        await client.post(
            f"/me/calendars/{calendar_id}/events/{event_id}/extensions",
            json=payload,
        )
        logger.debug("Extension added to event %s", event_id)
    except Exception as exc:
        logger.warning("Failed to add extension to event %s: %s", event_id, exc)


async def add_extension_to_todo(
    client: GraphClient,
    list_id: str,
    task_id: str,
    local_entity_id: int,
) -> None:
    """Attach a Milo extension to a Microsoft To Do task."""
    try:
        payload = make_milo_extension(local_entity_id, "task")
        await client.post(
            f"/me/todo/lists/{list_id}/tasks/{task_id}/extensions",
            json=payload,
        )
        logger.debug("Extension added to todo task %s", task_id)
    except Exception as exc:
        logger.warning("Failed to add extension to todo task %s: %s", task_id, exc)


async def get_extension_from_resource(
    client: GraphClient, resource_path: str
) -> Optional[dict]:
    """Fetch the Milo extension from a resource, returns None if not present."""
    try:
        resp = await client.get(
            f"{resource_path}/extensions/{EXTENSION_NAME}"
        )
        return resp
    except Exception:
        return None
