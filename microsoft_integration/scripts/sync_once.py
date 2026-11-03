"""Run a one-shot sync for all accounts (useful for cron jobs or manual triggering)."""
from __future__ import annotations

import asyncio
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
from microsoft_integration.auth.encryption import TokenEncryptor
from microsoft_integration.sync.engine import SyncEngineConfig, run_sync_for_all_accounts
from microsoft_integration.logging_config import configure_logging

configure_logging()


async def main():
    settings = get_settings()
    if not settings.encryption_key_valid:
        print("ERROR: MICROSOFT_TOKEN_ENCRYPTION_KEY not set")
        sys.exit(1)

    encryptor = TokenEncryptor(settings.microsoft_token_encryption_key)
    config = SyncEngineConfig(settings=settings, encryptor=encryptor)

    print("Running one-shot sync for all accounts...")
    await run_sync_for_all_accounts(config)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
