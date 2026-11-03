"""Pydantic schemas / DTOs for Microsoft integration API and internal use."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Internal DTOs — decouple sync engine from Milo ORM and Microsoft Graph
# ---------------------------------------------------------------------------


class LocalTaskDTO(BaseModel):
    """Milo task as seen by the sync engine."""
    id: int
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    completed: bool = False
    completed_at: Optional[datetime] = None
    recurrence: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LocalEventDTO(BaseModel):
    """Milo event as seen by the sync engine."""
    id: int
    title: str
    description: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    all_day: bool = False
    location: Optional[str] = None
    recurrence: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RemoteTodoDTO(BaseModel):
    """Microsoft To Do task as seen by the sync engine."""
    id: str
    list_id: str
    title: str
    body: Optional[str] = None
    due_date_time: Optional[datetime] = None
    status: str = "notStarted"
    completed_date_time: Optional[datetime] = None
    recurrence: Optional[Dict[str, Any]] = None
    categories: List[str] = Field(default_factory=list)
    last_modified: Optional[datetime] = None
    etag: Optional[str] = None
    milo_extension: Optional[Dict[str, Any]] = None


class RemoteEventDTO(BaseModel):
    """Microsoft Calendar event as seen by the sync engine."""
    id: str
    immutable_id: Optional[str] = None
    calendar_id: str
    subject: str
    body: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    is_all_day: bool = False
    location: Optional[str] = None
    recurrence: Optional[Dict[str, Any]] = None
    categories: List[str] = Field(default_factory=list)
    last_modified: Optional[datetime] = None
    etag: Optional[str] = None
    milo_extension: Optional[Dict[str, Any]] = None
    is_deleted: bool = False


# ---------------------------------------------------------------------------
# API response schemas
# ---------------------------------------------------------------------------


class AccountOut(BaseModel):
    id: int
    microsoft_user_id: str
    display_name: str
    email: str
    account_type: str
    enabled: bool
    needs_reauthentication: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SyncTargetOut(BaseModel):
    id: int
    account_id: int
    target_type: str
    remote_id: str
    remote_name: str
    enabled: bool
    sync_direction: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyncRunOut(BaseModel):
    id: int
    account_id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    is_full_sync: bool
    is_dry_run: bool
    calendar_created: int
    calendar_updated: int
    calendar_deleted: int
    tasks_created: int
    tasks_updated: int
    tasks_deleted: int
    conflicts_detected: int
    errors_count: int

    model_config = {"from_attributes": True}


class ConflictOut(BaseModel):
    id: int
    account_id: int
    entity_type: str
    local_entity_id: int
    remote_entity_id: str
    local_snapshot: Optional[str] = None
    remote_snapshot: Optional[str] = None
    local_modified_at: Optional[datetime] = None
    remote_modified_at: Optional[datetime] = None
    status: str
    resolution: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DeviceFlowStartOut(BaseModel):
    flow_id: str
    user_code: str
    verification_uri: str
    message: str
    expires_at: datetime


class DeviceFlowStatusOut(BaseModel):
    flow_id: str
    status: str  # pending | completed | failed | expired
    account: Optional[AccountOut] = None


class CalendarOut(BaseModel):
    id: str
    name: str
    is_default: bool = False
    can_edit: bool = True


class TodoListOut(BaseModel):
    id: str
    display_name: str
    is_owner: bool = True


class SyncPreviewOut(BaseModel):
    tasks_would_create_remote: int = 0
    tasks_would_update_remote: int = 0
    tasks_would_create_local: int = 0
    tasks_would_update_local: int = 0
    events_would_create_remote: int = 0
    events_would_update_remote: int = 0
    events_would_create_local: int = 0
    events_would_update_local: int = 0
    conflicts_detected: int = 0
    details: List[str] = Field(default_factory=list)


class HealthOut(BaseModel):
    status: str
    database: str
    service: str
    scheduler: str
    version: str = "1.0.0"


class AccountConfigOut(BaseModel):
    account_id: int
    calendar_sync_enabled: bool = True
    todo_sync_enabled: bool = True
    calendar_id: Optional[str] = None
    calendar_name: Optional[str] = None
    todo_list_id: Optional[str] = None
    todo_list_name: Optional[str] = None
    calendar_sync_direction: str = "bidirectional"
    todo_sync_direction: str = "bidirectional"
    sync_interval_seconds: int = 300
    conflict_policy: str = "manual"  # manual | keep_local | keep_microsoft


class AccountConfigIn(BaseModel):
    calendar_sync_enabled: Optional[bool] = None
    todo_sync_enabled: Optional[bool] = None
    calendar_id: Optional[str] = None
    calendar_name: Optional[str] = None
    todo_list_id: Optional[str] = None
    todo_list_name: Optional[str] = None
    calendar_sync_direction: Optional[str] = None
    todo_sync_direction: Optional[str] = None
    sync_interval_seconds: Optional[int] = None
    conflict_policy: Optional[str] = None


class ConflictResolveIn(BaseModel):
    resolution: str  # keep_local | keep_microsoft | merge
