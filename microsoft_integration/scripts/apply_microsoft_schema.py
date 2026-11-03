"""Apply Microsoft integration schema to MariaDB.

Reads the SQL file and executes it against the configured database.
Idempotent — safe to run multiple times.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure the project root is in sys.path
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    for candidate in [
        Path.cwd() / ".env.microsoft",
        _PROJECT_ROOT / "microsoft_integration" / ".env.microsoft",
        _PROJECT_ROOT / ".env.microsoft",
    ]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break
except ImportError:
    pass

from microsoft_integration.config import get_settings
from microsoft_integration.database import get_engine

logger = logging.getLogger("microsoft.scripts.apply_schema")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

SQL_FILE = Path(__file__).parent.parent / "sql" / "001_microsoft_schema.sql"


def apply_schema() -> None:
    """Apply the Microsoft schema SQL file to the database."""
    settings = get_settings()

    if not settings.encryption_key_valid:
        print("WARNING: MICROSOFT_TOKEN_ENCRYPTION_KEY not set — schema applied but service will not start.")

    print(f"Connecting to database: {settings.db_host}:{settings.db_port}/{settings.db_name}")

    engine = get_engine()

    # Test connection
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        if result != 1:
            raise RuntimeError("Database connectivity check failed")
    print("✓ Database connected")

    # Read SQL file
    if not SQL_FILE.exists():
        raise FileNotFoundError(f"SQL file not found: {SQL_FILE}")

    sql_content = SQL_FILE.read_text(encoding="utf-8")

    # Split by semicolons and execute each statement
    statements = [s.strip() for s in sql_content.split(";") if s.strip()]

    with engine.begin() as conn:
        created = 0
        skipped = 0
        for stmt in statements:
            if not stmt or stmt.startswith("--") or stmt.startswith("SET "):
                continue
            try:
                conn.execute(text(stmt))
                if "CREATE TABLE" in stmt.upper():
                    table_name = _extract_table_name(stmt)
                    print(f"✓ Table created/verified: {table_name}")
                    created += 1
                elif "INSERT IGNORE" in stmt.upper():
                    print("✓ Schema version registered")
            except Exception as exc:
                print(f"✗ Statement failed: {exc}")
                raise

    print(f"\n✓ Microsoft schema applied: {created} table(s) created/verified")
    _print_version(engine)


def _extract_table_name(stmt: str) -> str:
    import re
    m = re.search(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", stmt, re.IGNORECASE)
    return m.group(1) if m else "unknown"


def _print_version(engine) -> None:
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT version, applied_at, description FROM ms_schema_version ORDER BY version")
            ).fetchall()
            print("\nApplied Microsoft schema versions:")
            for row in result:
                print(f"  v{row[0]} — {row[2]} (applied: {row[1]})")
    except Exception:
        pass


if __name__ == "__main__":
    apply_schema()
