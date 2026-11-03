# Microsoft Integration SQL Directory

## Files

### `001_microsoft_schema.sql`

Creates all Microsoft integration tables using `CREATE TABLE IF NOT EXISTS`.

**Safe to run multiple times** — idempotent.

**Never modifies Milo tables.**

All tables use the `ms_` prefix.

## Usage

### Via the Python script (recommended)

```bash
cd microsoft_integration
python scripts/apply_microsoft_schema.py
```

### Via MariaDB CLI

```bash
mysql -u milo_app -p milo < sql/001_microsoft_schema.sql
```

## Tables created

| Table | Purpose |
|-------|---------|
| `ms_schema_version` | Tracks applied Microsoft migrations |
| `ms_accounts` | Connected Microsoft accounts |
| `ms_token_cache` | Encrypted MSAL token caches |
| `ms_sync_targets` | Selected calendars/To Do lists per account |
| `ms_entity_links` | Mapping between Milo entities and Microsoft remote entities |
| `ms_sync_state` | Delta tokens and sync window state |
| `ms_sync_runs` | History of sync operations |
| `ms_sync_errors` | Per-entity errors during sync |
| `ms_sync_conflicts` | Both-sides-changed conflicts awaiting resolution |
| `ms_subscriptions` | Graph change notification subscriptions |
| `ms_auth_flows` | In-progress Device Code Flow states |
