"""Verify database and configuration before starting the integration service."""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    for c in [Path.cwd() / ".env.microsoft", _PROJECT_ROOT / ".env.microsoft"]:
        if c.exists():
            load_dotenv(c, override=False)
            break
except ImportError:
    pass

from microsoft_integration.config import get_settings
from microsoft_integration.database import check_db_health


def main():
    settings = get_settings()
    print("\n== Microsoft Integration — Connection Verification ==\n")

    # DB check
    health = check_db_health()
    db_ok = health["database"] == "connected"
    print(f"Database:  {'✓ Connected' if db_ok else '✗ FAILED'}")

    # Encryption key check
    enc_ok = settings.encryption_key_valid
    print(f"Enc. key:  {'✓ Set' if enc_ok else '✗ NOT SET (MICROSOFT_TOKEN_ENCRYPTION_KEY)'}")

    # Client ID check
    client_ok = settings.client_configured
    print(f"Client ID: {'✓ Set' if client_ok else '✗ NOT SET (MICROSOFT_CLIENT_ID)'}")

    print(f"\nService will start on: http://{settings.microsoft_service_host}:{settings.microsoft_service_port}")
    print()

    if not (db_ok and enc_ok and client_ok):
        print("⚠  Some checks failed. Review the missing values in .env.microsoft")
        sys.exit(1)
    else:
        print("✓ All checks passed — ready to start!")


if __name__ == "__main__":
    main()
