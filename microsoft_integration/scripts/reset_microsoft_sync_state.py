"""Reset Microsoft sync state for an account (invalidates delta tokens).

Use this when you want to force a full resync without disconnecting the account.
"""
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

from microsoft_integration.database import get_db_session
from microsoft_integration.models import MsSyncState
from microsoft_integration.logging_config import configure_logging

configure_logging()


def reset_sync_state(account_id: int | None = None) -> None:
    with get_db_session() as db:
        q = db.query(MsSyncState)
        if account_id is not None:
            q = q.filter(MsSyncState.account_id == account_id)
        count = q.count()
        q.delete()
        db.commit()
        print(f"Deleted {count} sync state record(s).")
        print("Next sync will perform a full resync for affected accounts.")


if __name__ == "__main__":
    account_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if account_id:
        print(f"Resetting sync state for account {account_id}")
    else:
        print("Resetting sync state for ALL accounts")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)
    reset_sync_state(account_id)
