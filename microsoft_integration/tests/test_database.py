"""Tests for database layer (schema application, connectivity)."""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock


class TestDatabaseConfig:
    def test_database_url_construction(self):
        with patch.dict(os.environ, {
            "DB_HOST": "testhost",
            "DB_PORT": "3307",
            "DB_NAME": "testdb",
            "DB_USER": "testuser",
            "DB_PASSWORD": "testpass",
        }):
            from microsoft_integration import config as cfg
            cfg._settings = None  # Reset singleton
            settings = cfg.get_settings()
            url = settings.database_url
            assert "testhost" in url
            assert "3307" in url
            assert "testdb" in url
            assert "testuser" in url
            cfg._settings = None  # Reset again

    def test_encryption_key_validation(self):
        with patch.dict(os.environ, {"MICROSOFT_TOKEN_ENCRYPTION_KEY": ""}):
            from microsoft_integration import config as cfg
            cfg._settings = None
            settings = cfg.get_settings()
            assert not settings.encryption_key_valid
            cfg._settings = None

    def test_client_configured_false_when_empty(self):
        with patch.dict(os.environ, {"MICROSOFT_CLIENT_ID": ""}):
            from microsoft_integration import config as cfg
            cfg._settings = None
            settings = cfg.get_settings()
            assert not settings.client_configured
            cfg._settings = None
