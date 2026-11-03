"""MSAL token cache management with database persistence and encryption.

The cache serializes to/from the MSAL SerializableTokenCache format.
Serialized bytes are encrypted via Fernet before being stored in ms_token_cache.
"""
from __future__ import annotations

import logging
from typing import Optional

import msal
from sqlalchemy.orm import Session

from microsoft_integration.auth.encryption import TokenEncryptor
from microsoft_integration.models import MsTokenCache

logger = logging.getLogger("microsoft.auth.token_cache")


class PersistedTokenCache:
    """A token cache backed by the ms_token_cache database table."""

    def __init__(self, account_id: int, encryptor: TokenEncryptor, db: Session) -> None:
        self._account_id = account_id
        self._encryptor = encryptor
        self._db = db
        self._cache = msal.SerializableTokenCache()
        self._dirty = False
        self._load()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        row = (
            self._db.query(MsTokenCache)
            .filter(MsTokenCache.account_id == self._account_id)
            .first()
        )
        if row:
            try:
                serialized = self._encryptor.decrypt(row.encrypted_cache)
                self._cache.deserialize(serialized)
                logger.debug("Token cache loaded for account %d", self._account_id)
            except Exception as exc:
                logger.error(
                    "Failed to load token cache for account %d: %s",
                    self._account_id,
                    exc,
                )
                # Cache remains empty; triggers re-auth flow

    def save_if_dirty(self) -> None:
        """Persist the cache to the database if it changed since last load/save."""
        if not self._cache.has_state_changed:
            return
        try:
            serialized = self._cache.serialize()
            encrypted = self._encryptor.encrypt(serialized)
            row = (
                self._db.query(MsTokenCache)
                .filter(MsTokenCache.account_id == self._account_id)
                .first()
            )
            if row:
                row.encrypted_cache = encrypted
            else:
                row = MsTokenCache(
                    account_id=self._account_id,
                    encrypted_cache=encrypted,
                )
                self._db.add(row)
            self._db.flush()
            logger.debug("Token cache saved for account %d", self._account_id)
        except Exception as exc:
            logger.error(
                "Failed to save token cache for account %d: %s", self._account_id, exc
            )
            raise

    @property
    def msal_cache(self) -> msal.SerializableTokenCache:
        return self._cache


def delete_token_cache(account_id: int, db: Session) -> None:
    """Delete the token cache for an account (on disconnect)."""
    db.query(MsTokenCache).filter(MsTokenCache.account_id == account_id).delete()
    db.flush()
