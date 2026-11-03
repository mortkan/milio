# Microsoft Integration — Database Reference

## Overview

All Microsoft integration tables use the `ms_` prefix and live in the same
database as Milo. They are completely independent of Milo's own tables.

No foreign keys are created from `ms_` tables into Milo tables to avoid
coupling with ongoing Milo development.

## Tables

### ms_accounts

Stores one row per connected Microsoft account.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK | Auto-increment |
| microsoft_user_id | VARCHAR(100) | Microsoft OID/sub — unique identifier |
| tenant_id | VARCHAR(100) | Azure tenant ID |
| display_name | VARCHAR(200) | Microsoft display name |
| email | VARCHAR(200) | Email / UPN |
| account_type | VARCHAR(20) | personal / work / school |
| enabled | TINYINT | Whether sync is active |
| needs_reauthentication | TINYINT | Token refresh failed — user must re-auth |
| created_at / updated_at / last_login_at | DATETIME | Timestamps |

### ms_token_cache

Stores the encrypted MSAL SerializableTokenCache. One row per account.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK | |
| account_id | INT FK → ms_accounts | |
| encrypted_cache | LONGTEXT | Fernet-encrypted MSAL cache JSON |
| created_at / updated_at | DATETIME | |

**Security:** `encrypted_cache` contains ONLY Fernet-encrypted data. The plaintext (containing tokens) is never stored.

### ms_sync_targets

Identifies which Microsoft resources (calendars, To Do lists) are actively synced per account.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK | |
| account_id | INT FK | |
| target_type | VARCHAR(20) | `calendar` or `todo_list` |
| remote_id | VARCHAR(400) | Microsoft resource ID |
| remote_name | VARCHAR(200) | Human-readable name |
| enabled | TINYINT | |
| sync_direction | VARCHAR(30) | `bidirectional` / `milo_to_microsoft` / `microsoft_to_milo` |

### ms_entity_links

The central mapping table. Links a Milo entity to its Microsoft counterpart.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK | |
| account_id | INT FK | |
| local_entity_type | VARCHAR(20) | `task` or `event` |
| local_entity_id | INT | Milo `notes.id` |
| remote_entity_type | VARCHAR(30) | `todo_task` or `calendar_event` |
| remote_entity_id | VARCHAR(400) | Microsoft item ID (immutable for calendar) |
| remote_container_id | VARCHAR(400) | Calendar ID or list ID |
| remote_etag | VARCHAR(200) | ETag for optimistic concurrency |
| remote_last_modified | DATETIME | |
| local_last_modified | DATETIME | |
| sync_hash | VARCHAR(64) | SHA-256 of syncable local fields |
| last_synced_at | DATETIME | When this pair was last synced |
| remote_deleted | TINYINT | Remote tombstone |
| local_deleted | TINYINT | Local tombstone |

### ms_sync_state

Stores delta tokens and sync windows per resource.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK | |
| account_id | INT FK | |
| resource_type | VARCHAR(20) | `calendar` or `todo_list` |
| resource_id | VARCHAR(400) | Remote resource ID |
| delta_link | LONGTEXT | `@odata.deltaLink` from last response |
| last_sync_at | DATETIME | Last incremental sync |
| last_full_sync_at | DATETIME | Last full sync |
| sync_window_start / end | DATETIME | Current sync window |

### ms_sync_runs

History of every sync operation.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK | |
| account_id | INT FK | |
| started_at / finished_at | DATETIME | |
| status | VARCHAR(20) | `running` / `success` / `partial` / `failed` |
| is_full_sync | TINYINT | |
| is_dry_run | TINYINT | |
| calendar_created/updated/deleted | INT | Counters |
| tasks_created/updated/deleted | INT | Counters |
| conflicts_detected | INT | |
| errors_count | INT | |

### ms_sync_errors

Per-entity error log.

| Column | Description |
|--------|-------------|
| sync_run_id | FK → ms_sync_runs |
| account_id | |
| entity_type / local_entity_id / remote_entity_id | Identifies the affected item |
| error_code | Short code |
| safe_message | Human-readable message (NO tokens/secrets) |

### ms_sync_conflicts

Conflicts awaiting resolution.

| Column | Description |
|--------|-------------|
| entity_link_id | FK → ms_entity_links |
| local_snapshot / remote_snapshot | JSON snapshots of both versions |
| local_modified_at / remote_modified_at | |
| status | `pending` / `resolved` / `ignored` |
| resolution | `keep_local` / `keep_microsoft` / `merge` |

### ms_subscriptions

Graph change notification subscriptions (webhooks).

### ms_auth_flows

In-progress Device Code Flow state.

### ms_schema_version

Tracks applied Microsoft schema migrations.

## Schema Application

```bash
python microsoft_integration/scripts/apply_microsoft_schema.py
```

Or directly:

```bash
mysql -u milo_app -p milo < microsoft_integration/sql/001_microsoft_schema.sql
```

## Indexes

Key indexes for performance:
- `ms_entity_links(local_entity_type, local_entity_id)` — local lookup
- `ms_entity_links(remote_entity_type, remote_entity_id)` — remote lookup
- `ms_sync_runs(account_id, started_at)` — history queries
- `ms_sync_conflicts(account_id, status)` — pending conflict queries
