"""Tests for sync mapping (task and event field mapping)."""
from __future__ import annotations

from datetime import datetime
import pytest

from microsoft_integration.schemas import LocalTaskDTO, LocalEventDTO
from microsoft_integration.sync.mapping import (
    task_to_graph_payload,
    graph_task_to_local_fields,
    event_to_graph_payload,
    graph_event_to_local_fields,
    compute_task_hash,
    compute_event_hash,
    milo_recurrence_to_graph,
    graph_recurrence_to_milo,
    COMPLEX_RECURRENCE_TAG,
)


class TestTaskMapping:
    def _task(self, **kwargs):
        defaults = dict(id=1, title="Test Task", completed=False)
        defaults.update(kwargs)
        return LocalTaskDTO(**defaults)

    def test_basic_task_payload(self):
        task = self._task(title="Buy milk")
        payload = task_to_graph_payload(task)
        assert payload["title"] == "Buy milk"
        assert payload["status"] == "notStarted"

    def test_completed_task(self):
        task = self._task(completed=True)
        payload = task_to_graph_payload(task)
        assert payload["status"] == "completed"

    def test_due_date_mapped(self):
        due = datetime(2026, 6, 15, 10, 0, 0)
        task = self._task(due_date=due)
        payload = task_to_graph_payload(task)
        assert "dueDateTime" in payload
        assert "2026-06-15" in payload["dueDateTime"]["dateTime"]

    def test_description_mapped(self):
        task = self._task(description="Details here")
        payload = task_to_graph_payload(task)
        assert payload["body"]["content"] == "Details here"

    def test_recurrence_daily(self):
        task = self._task(recurrence="daily")
        payload = task_to_graph_payload(task)
        assert "recurrence" in payload
        assert payload["recurrence"]["pattern"]["type"] == "daily"

    def test_no_recurrence(self):
        task = self._task(recurrence="none")
        payload = task_to_graph_payload(task)
        assert "recurrence" not in payload

    def test_graph_to_local_completed(self):
        graph_task = {"title": "Done", "status": "completed", "body": None}
        fields = graph_task_to_local_fields(graph_task)
        assert fields["completed"] is True

    def test_sync_hash_changes_on_title(self):
        t1 = self._task(title="Original")
        t2 = self._task(title="Changed")
        assert compute_task_hash(t1) != compute_task_hash(t2)

    def test_sync_hash_stable(self):
        t = self._task(title="Same")
        assert compute_task_hash(t) == compute_task_hash(t)


class TestEventMapping:
    def _event(self, **kwargs):
        defaults = dict(id=1, title="Test Event", all_day=False)
        defaults.update(kwargs)
        return LocalEventDTO(**defaults)

    def test_basic_event_subject(self):
        event = self._event(title="Team meeting")
        payload = event_to_graph_payload(event)
        assert payload["subject"] == "Team meeting"

    def test_all_day_event(self):
        event = self._event(
            title="Holiday",
            all_day=True,
            start=datetime(2026, 12, 25, 0, 0, 0),
        )
        payload = event_to_graph_payload(event)
        assert payload.get("isAllDay") is True
        assert "date" in payload["start"]

    def test_timed_event_has_datetimes(self):
        event = self._event(
            title="Lunch",
            start=datetime(2026, 6, 15, 12, 0, 0),
            end=datetime(2026, 6, 15, 13, 0, 0),
        )
        payload = event_to_graph_payload(event)
        assert "dateTime" in payload["start"]
        assert "dateTime" in payload["end"]

    def test_location_mapped(self):
        event = self._event(title="Office", location="Madrid")
        payload = event_to_graph_payload(event)
        assert payload["location"]["displayName"] == "Madrid"

    def test_event_hash_changes_on_title(self):
        e1 = self._event(title="A")
        e2 = self._event(title="B")
        assert compute_event_hash(e1) != compute_event_hash(e2)


class TestRecurrenceMapping:
    def test_daily_to_graph(self):
        rec = milo_recurrence_to_graph("daily")
        assert rec["pattern"]["type"] == "daily"

    def test_none_recurrence(self):
        assert milo_recurrence_to_graph("none") is None
        assert milo_recurrence_to_graph(None) is None

    def test_graph_daily_to_milo(self):
        graph_rec = {"pattern": {"type": "daily"}, "range": {"type": "noEnd"}}
        assert graph_recurrence_to_milo(graph_rec) == "daily"

    def test_complex_recurrence_tagged(self):
        graph_rec = {"pattern": {"type": "relativeMonthly"}, "range": {"type": "noEnd"}}
        result = graph_recurrence_to_milo(graph_rec)
        # relativeMonthly maps to monthly
        assert result == "monthly"

    def test_truly_complex_recurrence(self):
        # An unknown type should be tagged as complex
        graph_rec = {"pattern": {"type": "unknownCustomType"}, "range": {"type": "noEnd"}}
        result = graph_recurrence_to_milo(graph_rec)
        assert result == COMPLEX_RECURRENCE_TAG
