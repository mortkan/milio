"""Tests for authentication layer (encryption, token cache, device flow)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from cryptography.fernet import Fernet

from microsoft_integration.auth.encryption import TokenEncryptor, generate_key


class TestTokenEncryptor:
    def test_generate_key_is_valid(self):
        key = generate_key()
        enc = TokenEncryptor(key)
        assert enc is not None

    def test_encrypt_decrypt_roundtrip(self):
        key = generate_key()
        enc = TokenEncryptor(key)
        plaintext = '{"accounts": [], "refreshTokens": {}}'
        ciphertext = enc.encrypt(plaintext)
        assert ciphertext != plaintext
        assert enc.decrypt(ciphertext) == plaintext

    def test_different_key_cannot_decrypt(self):
        from cryptography.fernet import InvalidToken
        key1 = generate_key()
        key2 = generate_key()
        enc1 = TokenEncryptor(key1)
        enc2 = TokenEncryptor(key2)
        ct = enc1.encrypt("secret data")
        with pytest.raises(InvalidToken):
            enc2.decrypt(ct)

    def test_empty_key_raises(self):
        with pytest.raises(ValueError, match="MICROSOFT_TOKEN_ENCRYPTION_KEY"):
            TokenEncryptor("")

    def test_invalid_key_raises(self):
        with pytest.raises(ValueError):
            TokenEncryptor("not-a-valid-fernet-key")
