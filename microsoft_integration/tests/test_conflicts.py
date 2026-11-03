"""Tests for conflict detection and resolution."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from microsoft_integration.sync.conflict_resolver import (
    detect_conflict,
    record_conflict,
    resolve_conflict,
    count_pending_conflicts,
)
from microsoft_integration.models import MsEntityLink, MsSyncConflict


class TestDetectConflict:
    def _link(self, last_synced_at):
        m = MagicMock(spec=MsEntityLink)
        m.last_synced_at = last_synced_at
        return m

    def test_both_changed_after_sync(self):
        sync_time = datetime(2026, 1, 1)
        link = self._link(sync_time)
        assert detect_conflict(link, datetime(2026, 1, 2), datetime(2026, 1, 3)) is True

    def test_only_local_changed(self):
        sync_time = datetime(2026, 1, 1)
        link = self._link(sync_time)
        assert detect_conflict(link, datetime(2026, 1, 2), datetime(2025, 12, 31)) is False

    def test_neither_changed(self):
        sync_time = datetime(2026, 1, 5)
        link = self._link(sync_time)
        assert detect_conflict(link, datetime(2026, 1, 1), datetime(2026, 1, 2)) is False

    def test_no_prior_sync(self):
        link = self._link(None)
        assert detect_conflict(link, datetime.utcnow(), datetime.utcnow()) is False


class TestRecordAndResolveConflict:
    def _db(self, existing=None):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = existing
        db.query.return_value = q
        return db

    def test_record_conflict_adds_row(self):
        db = self._db(existing=None)
        link = MagicMock(spec=MsEntityLink)
        link.id = 1
        link.local_entity_id = 10
        link.remote_entity_id = "remote-10"
        conflict = record_conflict(
            db,
            account_id=1,
            entity_link=link,
            entity_type="task",
            local_snapshot={"title": "Local"},
            remote_snapshot={"title": "Remote"},
            local_modified_at=datetime.utcnow(),
            remote_modified_at=datetime.utcnow(),
        )
        db.add.assert_called_once()
        db.flush.assert_called()

    def test_resolve_updates_status(self):
        existing_conflict = MagicMock(spec=MsSyncConflict)
        existing_conflict.id = 1
        existing_conflict.status = "pending"
        db = self._db(existing=existing_conflict)

        resolve_conflict(db, 1, "keep_local")
        assert existing_conflict.status == "resolved"
        assert existing_conflict.resolution == "keep_local"
