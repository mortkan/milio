"""Field mapping between Milo DTOs and Microsoft Graph payloads.

Converts LocalTaskDTO → Graph To Do payload (and back).
Converts LocalEventDTO → Graph Calendar event payload (and back).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from microsoft_integration.schemas import LocalEventDTO, LocalTaskDTO

logger = logging.getLogger("microsoft.sync.mapping")

# ---------------------------------------------------------------------------
# Recurrence mapping (Milo simple ↔ Graph recurrence pattern)
# ---------------------------------------------------------------------------

_MILO_TO_GRAPH_RECURRENCE: Dict[str, Dict[str, Any]] = {
    "daily": {
        "pattern": {"type": "daily", "interval": 1},
        "range": {"type": "noEnd"},
    },
    "weekly": {
        "pattern": {"type": "weekly", "interval": 1, "daysOfWeek": []},
        "range": {"type": "noEnd"},
    },
    "monthly": {
        "pattern": {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": 1},
        "range": {"type": "noEnd"},
    },
    "yearly": {
        "pattern": {"type": "absoluteYearly", "interval": 1, "dayOfMonth": 1, "month": 1},
        "range": {"type": "noEnd"},
    },
}

_GRAPH_TO_MILO_RECURRENCE: Dict[str, str] = {
    "daily": "daily",
    "weekly": "weekly",
    "absoluteMonthly": "monthly",
    "relativeMonthly": "monthly",
    "absoluteYearly": "yearly",
    "relativeYearly": "yearly",
}

COMPLEX_RECURRENCE_TAG = "remote_complex_recurrence"


def milo_recurrence_to_graph(recurrence: Optional[str]) -> Optional[Dict[str, Any]]:
    if not recurrence or recurrence in ("none", "", None):
        return None
    return _MILO_TO_GRAPH_RECURRENCE.get(recurrence)


def graph_recurrence_to_milo(
    graph_recurrence: Optional[Dict[str, Any]]
) -> Optional[str]:
    """Convert Graph recurrence to Milo recurrence string.

    Returns COMPLEX_RECURRENCE_TAG if the pattern cannot be represented simply.
    """
    if not graph_recurrence:
        return None
    pattern_type = (graph_recurrence.get("pattern") or {}).get("type", "")
    milo_rec = _GRAPH_TO_MILO_RECURRENCE.get(pattern_type)
    if milo_rec:
        return milo_rec
    logger.warning("Complex recurrence type '%s' — tagging as complex", pattern_type)
    return COMPLEX_RECURRENCE_TAG


# ---------------------------------------------------------------------------
# Sync hash — computed over syncable fields to detect real changes
# ---------------------------------------------------------------------------


def compute_task_hash(task: LocalTaskDTO) -> str:
    """Hash the syncable fields of a local task."""
    data = {
        "title": task.title or "",
        "description": (task.description or "")[:2000],
        "due_date": task.due_date.isoformat() if task.due_date else "",
        "completed": task.completed,
        "recurrence": task.recurrence or "none",
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def compute_event_hash(event: LocalEventDTO) -> str:
    """Hash the syncable fields of a local event."""
    data = {
        "title": event.title or "",
        "description": (event.description or "")[:2000],
        "start": event.start.isoformat() if event.start else "",
        "end": event.end.isoformat() if event.end else "",
        "all_day": event.all_day,
        "location": event.location or "",
        "recurrence": event.recurrence or "none",
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def compute_remote_task_hash(task_payload: Dict[str, Any]) -> str:
    """Hash the syncable fields of a remote To Do task."""
    data = {
        "title": task_payload.get("title", ""),
        "body": (task_payload.get("body") or {}).get("content", "")[:2000],
        "dueDateTime": (task_payload.get("dueDateTime") or {}).get("dateTime", ""),
        "status": task_payload.get("status", ""),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# LocalTaskDTO → Graph To Do payload
# ---------------------------------------------------------------------------


def task_to_graph_payload(task: LocalTaskDTO) -> Dict[str, Any]:
    """Convert a Milo task to a Microsoft To Do creation/update payload."""
    payload: Dict[str, Any] = {
        "title": task.title,
    }

    if task.description:
        payload["body"] = {"content": task.description, "contentType": "text"}

    if task.due_date:
        payload["dueDateTime"] = {
            "dateTime": task.due_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
            "timeZone": "UTC",
        }

    payload["status"] = "completed" if task.completed else "notStarted"

    if task.completed and task.completed_at:
        payload["completedDateTime"] = {
            "dateTime": task.completed_at.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
            "timeZone": "UTC",
        }

    recurrence = milo_recurrence_to_graph(task.recurrence)
    if recurrence:
        payload["recurrence"] = recurrence

    if task.tags:
        payload["categories"] = task.tags[:5]  # Graph limits categories

    return payload


def graph_task_to_local_fields(graph_task: Dict[str, Any]) -> Dict[str, Any]:
    """Extract syncable fields from a Graph To Do task as a plain dict."""
    body_content = None
    body = graph_task.get("body")
    if body:
        body_content = body.get("content") or body.get("text")

    due: Optional[datetime] = None
    due_raw = graph_task.get("dueDateTime")
    if due_raw and isinstance(due_raw, dict):
        try:
            dt_str = due_raw.get("dateTime", "").replace("Z", "").split(".")[0]
            due = datetime.fromisoformat(dt_str)
        except Exception:
            pass

    completed = graph_task.get("status") == "completed"
    recurrence = graph_recurrence_to_milo(graph_task.get("recurrence"))

    return {
        "title": graph_task.get("title", ""),
        "description": body_content,
        "due_date": due,
        "completed": completed,
        "recurrence": recurrence if recurrence != COMPLEX_RECURRENCE_TAG else None,
    }


# ---------------------------------------------------------------------------
# LocalEventDTO → Graph Calendar event payload
# ---------------------------------------------------------------------------


def _tz_str(timezone_name: str = "UTC") -> str:
    return timezone_name


def event_to_graph_payload(
    event: LocalEventDTO, timezone_name: str = "UTC"
) -> Dict[str, Any]:
    """Convert a Milo event to a Graph Calendar event creation/update payload."""
    payload: Dict[str, Any] = {
        "subject": event.title,
    }

    if event.description:
        payload["body"] = {"content": event.description, "contentType": "text"}

    if event.all_day:
        date_str = (event.start or datetime.utcnow()).strftime("%Y-%m-%d")
        payload["start"] = {"date": date_str}
        payload["end"] = {"date": date_str}
        payload["isAllDay"] = True
    else:
        if event.start:
            payload["start"] = {
                "dateTime": event.start.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": _tz_str(timezone_name),
            }
        if event.end:
            payload["end"] = {
                "dateTime": event.end.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": _tz_str(timezone_name),
            }

    if event.location:
        payload["location"] = {"displayName": event.location}

    recurrence = milo_recurrence_to_graph(event.recurrence)
    if recurrence:
        if event.start:
            recurrence["range"]["startDate"] = event.start.strftime("%Y-%m-%d")
        payload["recurrence"] = recurrence

    if event.tags:
        payload["categories"] = event.tags[:5]

    return payload


def graph_event_to_local_fields(graph_event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract syncable fields from a Graph Calendar event as a plain dict."""
    body = graph_event.get("body", {})
    body_content = (body.get("content") if body else None)

    def parse_dt(d: Optional[Dict]) -> Optional[datetime]:
        if not d:
            return None
        dt_str = (d.get("dateTime", "") or "").replace("Z", "").split(".")[0].split("+")[0]
        try:
            return datetime.fromisoformat(dt_str) if dt_str else None
        except Exception:
            return None

    start = parse_dt(graph_event.get("start"))
    end = parse_dt(graph_event.get("end"))
    is_all_day = bool(graph_event.get("isAllDay", False))
    location = (graph_event.get("location") or {}).get("displayName")
    recurrence = graph_recurrence_to_milo(graph_event.get("recurrence"))

    return {
        "title": graph_event.get("subject", ""),
        "description": body_content,
        "start": start,
        "end": end,
        "all_day": is_all_day,
        "location": location,
        "recurrence": recurrence if recurrence != COMPLEX_RECURRENCE_TAG else None,
    }
