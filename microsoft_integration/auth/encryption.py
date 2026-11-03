"""Token cache encryption using Fernet (symmetric encryption).

Tokens are NEVER stored in plain text.
The encryption key must come from the MICROSOFT_TOKEN_ENCRYPTION_KEY env var.
"""
from __future__ import annotations

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("microsoft.auth.encryption")


class TokenEncryptor:
    """Encrypts/decrypts MSAL token cache blobs using Fernet."""

    def __init__(self, key: str) -> None:
        if not key or not key.strip():
            raise ValueError(
                "MICROSOFT_TOKEN_ENCRYPTION_KEY is required and must not be empty. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        try:
            key_bytes = key.strip().encode()
            # Validate it is a valid Fernet key (32 bytes base64-url-encoded)
            self._fernet = Fernet(key_bytes)
        except Exception as exc:
            raise ValueError(
                f"MICROSOFT_TOKEN_ENCRYPTION_KEY is not a valid Fernet key: {exc}"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string and return base64-encoded ciphertext."""
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt previously encrypted ciphertext. Raises InvalidToken on failure."""
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("ascii"))
            return plaintext.decode("utf-8")
        except InvalidToken as exc:
            logger.error("Token cache decryption failed — key mismatch or corruption")
            raise


def generate_key() -> str:
    """Generate a new valid Fernet key for MICROSOFT_TOKEN_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()
