"""Microsoft Graph: Microsoft To Do operations."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from microsoft_integration.graph.client import GraphClient
from microsoft_integration.graph.errors import GraphNotFoundError

logger = logging.getLogger("microsoft.graph.todo")


# ---------------------------------------------------------------------------
# List management
# ---------------------------------------------------------------------------


async def list_todo_lists(client: GraphClient) -> List[Dict[str, Any]]:
    """List all To Do task lists for the user."""
    return await client.get_all(
        "/me/todo/lists",
        params={"$select": "id,displayName,isOwner,isShared,wellknownListName"},
    )


async def get_todo_list_by_name(
    client: GraphClient, name: str
) -> Optional[Dict[str, Any]]:
    """Find a To Do list by name. Returns None if not found."""
    lists = await list_todo_lists(client)
    for lst in lists:
        if lst.get("displayName", "").lower() == name.lower():
            return lst
    return None


async def create_todo_list(client: GraphClient, name: str) -> Dict[str, Any]:
    """Create a new To Do task list."""
    return await client.post("/me/todo/lists", json={"displayName": name})


async def get_or_create_milo_list(
    client: GraphClient, list_name: str = "Milo"
) -> Dict[str, Any]:
    """Get the Milo To Do list or create it if it doesn't exist."""
    lst = await get_todo_list_by_name(client, list_name)
    if lst:
        logger.info("Found existing To Do list: %s (%s)", lst["displayName"], lst["id"])
        return lst
    logger.info("Creating To Do list: %s", list_name)
    return await create_todo_list(client, list_name)


# ---------------------------------------------------------------------------
# Task operations
# ---------------------------------------------------------------------------


async def list_tasks(
    client: GraphClient, list_id: str
) -> List[Dict[str, Any]]:
    """List all tasks in a To Do list."""
    return await client.get_all(
        f"/me/todo/lists/{list_id}/tasks",
        params={
            "$select": (
                "id,title,body,dueDateTime,status,completedDateTime,"
                "recurrence,categories,lastModifiedDateTime,extensions"
            ),
            "$expand": "extensions($filter=id eq 'com.milo.sync')",
        },
    )


async def get_task(
    client: GraphClient, list_id: str, task_id: str
) -> Optional[Dict[str, Any]]:
    """Fetch a single task. Returns None if not found."""
    try:
        return await client.get(
            f"/me/todo/lists/{list_id}/tasks/{task_id}",
            params={
                "$select": (
                    "id,title,body,dueDateTime,status,completedDateTime,"
                    "recurrence,categories,lastModifiedDateTime,extensions"
                ),
                "$expand": "extensions($filter=id eq 'com.milo.sync')",
            },
        )
    except GraphNotFoundError:
        return None


async def create_task(
    client: GraphClient, list_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a new task in a To Do list."""
    return await client.post(f"/me/todo/lists/{list_id}/tasks", json=payload)


async def update_task(
    client: GraphClient, list_id: str, task_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """PATCH an existing task with only the fields Milo controls."""
    return await client.patch(
        f"/me/todo/lists/{list_id}/tasks/{task_id}", json=payload
    )


async def delete_task(client: GraphClient, list_id: str, task_id: str) -> None:
    """Delete a task from a To Do list."""
    await client.delete(f"/me/todo/lists/{list_id}/tasks/{task_id}")


# ---------------------------------------------------------------------------
# Delta sync
# ---------------------------------------------------------------------------


async def delta_tasks(
    client: GraphClient,
    list_id: str,
    delta_link: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch changed tasks using delta query.

    Returns:
        Tuple of (list of changed tasks, new delta_link to save).
    """
    if delta_link:
        path = delta_link
        params = None
    else:
        path = f"/me/todo/lists/{list_id}/tasks/delta"
        params = {
            "$select": (
                "id,title,body,dueDateTime,status,completedDateTime,"
                "recurrence,categories,lastModifiedDateTime,extensions"
            ),
        }

    items, new_delta_link = await client.iter_delta(
        path, params=params if not delta_link else None
    )
    return items, new_delta_link
