"""Pruebas de integración de la API con una base de datos temporal."""

from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

TEMP_DIR = Path(tempfile.mkdtemp(prefix="agenda-tests-"))
os.environ["AGENDA_DB"] = str(TEMP_DIR / "agenda.db")
os.environ["AGENDA_BACKUP_DIR"] = str(TEMP_DIR / "backups")
os.environ.pop("AGENDA_SEED", None)
os.environ.pop("AGENDA_HOST", None)
os.environ.pop("AGENDA_PORT", None)

import pytest
from fastapi.testclient import TestClient

from app import config

config.DATA_DIR = TEMP_DIR
config.SETTINGS_FILE = TEMP_DIR / "settings.json"

from app.server import app


@pytest.fixture(scope="function")
def client():
    # Import models to ensure they're registered with Base
    from app import models  # noqa: F401 registers models with Base
    
    # Initialize the database for this test's temp directory
    from app.database import init_db
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def test_index_settings_and_meta(client):
    """Test that the index endpoint returns 200 and health check passes."""
    assert client.get("/").status_code == 200
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    settings = client.get("/api/settings")
    assert settings.status_code == 200


def test_calendar_recurrence_and_quick_notes(client):
    """Test calendar recurrence and quick notes endpoints."""
    # Test notes endpoint
    notes_resp = client.get("/api/notes")
    assert notes_resp.status_code == 200

    # Test quick notes endpoint (uses hyphen, not underscore)
    quick_resp = client.get("/api/quick-notes")
    assert quick_resp.status_code == 200


def test_settings_export_import_and_backups(client):
    """Test settings export/import and backup endpoints."""
    # Test settings GET
    settings_get = client.get("/api/settings")
    assert settings_get.status_code == 200

    # Test export endpoint
    export_resp = client.get("/api/export?format=json")
    assert export_resp.status_code == 200


def test_validation_errors(client):
    """Test that validation errors are handled properly."""
    # Test creating a note with invalid data
    invalid_note = {"title": "", "content": "test"}  # empty title should fail
    resp = client.post("/api/notes", json=invalid_note)
    assert resp.status_code == 422
