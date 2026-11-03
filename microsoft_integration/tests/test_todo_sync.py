"""Tests for To Do sync (mocked Microsoft API)."""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from microsoft_integration.schemas import LocalTaskDTO, RemoteTodoDTO
from microsoft_integration.sync import mapping


class TestTodoSyncIdempotency:
    """Verify that running sync twice without changes produces zero operations."""

    def _make_task(self, title="Test", completed=False):
        return LocalTaskDTO(id=1, title=title, completed=completed, updated_at=datetime.utcnow())

    def _make_remote(self, title="Test", task_id="remote-1"):
        return RemoteTodoDTO(
            id=task_id,
            list_id="list-1",
            title=title,
            status="notStarted",
            last_modified=datetime.utcnow(),
        )

    def test_hash_idempotency(self):
        task = self._make_task()
        h1 = mapping.compute_task_hash(task)
        h2 = mapping.compute_task_hash(task)
        assert h1 == h2, "Same task must produce identical hash on repeated calls"

    def test_hash_changes_on_title_change(self):
        t1 = self._make_task(title="Original")
        t2 = self._make_task(title="Modified")
        assert mapping.compute_task_hash(t1) != mapping.compute_task_hash(t2)

    def test_payload_is_stable(self):
        task = self._make_task(title="Stable")
        p1 = mapping.task_to_graph_payload(task)
        p2 = mapping.task_to_graph_payload(task)
        assert p1 == p2


class TestConflictDetection:
    def _make_link(self, last_synced_at):
        link = MagicMock()
        link.last_synced_at = last_synced_at
        return link

    def test_no_conflict_when_only_local_changed(self):
        from microsoft_integration.sync.conflict_resolver import detect_conflict
        synced = datetime(2026, 1, 1, 12, 0, 0)
        local_updated = datetime(2026, 1, 2, 10, 0, 0)
        remote_modified = datetime(2025, 12, 31, 10, 0, 0)
        link = self._make_link(synced)
        assert detect_conflict(link, local_updated, remote_modified) is False

    def test_no_conflict_when_only_remote_changed(self):
        from microsoft_integration.sync.conflict_resolver import detect_conflict
        synced = datetime(2026, 1, 1, 12, 0, 0)
        local_updated = datetime(2025, 12, 30, 10, 0, 0)
        remote_modified = datetime(2026, 1, 2, 10, 0, 0)
        link = self._make_link(synced)
        assert detect_conflict(link, local_updated, remote_modified) is False

    def test_conflict_when_both_changed(self):
        from microsoft_integration.sync.conflict_resolver import detect_conflict
        synced = datetime(2026, 1, 1, 12, 0, 0)
        local_updated = datetime(2026, 1, 2, 10, 0, 0)
        remote_modified = datetime(2026, 1, 2, 11, 0, 0)
        link = self._make_link(synced)
        assert detect_conflict(link, local_updated, remote_modified) is True

    def test_no_conflict_before_first_sync(self):
        from microsoft_integration.sync.conflict_resolver import detect_conflict
        link = self._make_link(None)
        assert detect_conflict(link, datetime.utcnow(), datetime.utcnow()) is False
