# Microsoft 365 Integration for Milo

> Bidirectional synchronization between Milo and Microsoft 365 (Outlook Calendar + Microsoft To Do).
> Runs as an independent service — does NOT modify any existing Milo files.

## Overview

This module provides:

- 🔐 **Secure authentication** via OAuth 2.0 Device Code Flow (MSAL)
- 📅 **Outlook Calendar** bidirectional sync with Milo events
- ✅ **Microsoft To Do** bidirectional sync with Milo tasks
- 🔄 **Incremental delta sync** — only fetches changes, not entire collections
- ⚔️ **Conflict resolution** — detects and surfaces both-sides-changed conflicts
- 🕐 **Scheduler** — automatic sync every 5 minutes (configurable)
- 🔒 **Encrypted token storage** — MSAL caches stored with Fernet symmetric encryption
- 👥 **Multi-account** — supports multiple Microsoft accounts simultaneously

## Architecture

```
Milo (port 8000)          Microsoft Integration (port 8010)
     │                              │
     │  shared MariaDB (ms_* tables)│
     └──────────────────────────────┘
                                    │
                          Microsoft Graph API v1.0
                          ┌─────────────────────┐
                          │  Outlook Calendar    │
                          │  Microsoft To Do     │
                          │  User Profile        │
                          └─────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams.

## Quick Start

### 1. Register an App in Microsoft Entra ID

See [MICROSOFT_SETUP.md](MICROSOFT_SETUP.md) for step-by-step instructions.

Minimum permissions required:
- `User.Read`
- `Calendars.ReadWrite`
- `Tasks.ReadWrite`
- `offline_access`

### 2. Configure environment variables

```bash
cp .env.microsoft.example .env.microsoft
```

Edit `.env.microsoft`:

```env
MICROSOFT_CLIENT_ID=your-client-id-here
MICROSOFT_TENANT=common
MICROSOFT_TOKEN_ENCRYPTION_KEY=<generate below>
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=milo
DB_USER=milo_app
DB_PASSWORD=your-db-password
```

### 3. Generate an encryption key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output as `MICROSOFT_TOKEN_ENCRYPTION_KEY` in `.env.microsoft`.

**This key protects your Microsoft tokens. Never share or commit it.**

### 4. Apply the Microsoft database schema

```bash
cd microsoft_integration
python scripts/apply_microsoft_schema.py
```

### 5. Start the service

```bash
uvicorn microsoft_integration.main:app --host 0.0.0.0 --port 8010
```

Or with Docker:

```bash
docker compose -f compose.microsoft.yml up -d
```

### 6. Connect a Microsoft account

Open **http://localhost:8010/microsoft** in your browser.

Click **Conectar cuenta**, then:
1. Note the displayed URL and code
2. Open the URL in a browser (can be any device)
3. Enter the code
4. Authorize Milo
5. Return to the Milo Microsoft panel — the account will appear as connected

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MICROSOFT_ENABLED` | `true` | Enable/disable the integration |
| `MICROSOFT_CLIENT_ID` | — | **Required** — Entra ID App client ID |
| `MICROSOFT_TENANT` | `common` | Tenant ID or `common` |
| `MICROSOFT_TOKEN_ENCRYPTION_KEY` | — | **Required** — Fernet key |
| `MICROSOFT_SYNC_INTERVAL_SECONDS` | `300` | Scheduler interval |
| `MICROSOFT_SYNC_LOOKBACK_DAYS` | `90` | Calendar sync lookback |
| `MICROSOFT_SYNC_LOOKAHEAD_DAYS` | `365` | Calendar sync lookahead |
| `MICROSOFT_SERVICE_PORT` | `8010` | Service port |
| `DB_HOST` | `127.0.0.1` | MariaDB host |
| `DB_PORT` | `3306` | MariaDB port |
| `DB_NAME` | `milo` | Database name |
| `DB_USER` | `milo_app` | Database user |
| `DB_PASSWORD` | — | Database password |
| `MICROSOFT_WEBHOOK_ENABLED` | `false` | Enable Graph webhooks |
| `MICROSOFT_TIMEZONE` | `Europe/Madrid` | Timezone for datetime conversion |

## API

Full interactive API docs: **http://localhost:8010/docs**

Key endpoints:
- `GET /api/microsoft/health` — Service health
- `POST /api/microsoft/auth/device/start` — Start authentication
- `GET /api/microsoft/accounts` — List connected accounts
- `POST /api/microsoft/accounts/{id}/sync` — Sync now
- `POST /api/microsoft/accounts/{id}/sync-preview` — Dry-run preview
- `GET /api/microsoft/conflicts` — List conflicts

## Docker

```bash
# Start
docker compose -f microsoft_integration/compose.microsoft.yml up -d

# View logs
docker logs milo-ms-integration -f

# Apply schema
docker compose -f microsoft_integration/compose.microsoft.yml run --rm ms-integration \
  python -m microsoft_integration.scripts.apply_microsoft_schema
```

**Network:** The service connects to the same `mistica-net` Docker network as Milo.
Update `compose.microsoft.yml` if your network name differs.

## Tests

```bash
cd microsoft_integration
pip install -r requirements.txt
pytest tests/ -v
```

Tests do NOT call real Microsoft APIs. All Graph and MSAL calls are mocked.

## Security

- Tokens are encrypted with Fernet (AES-128-CBC) before database storage
- The encryption key never appears in logs or responses
- Token values never appear in logs or error messages
- No credentials are stored in plain text anywhere
- The service only requests the minimum required Microsoft Graph permissions

## Troubleshooting

**Service won't start:**
- Check `MICROSOFT_TOKEN_ENCRYPTION_KEY` is a valid Fernet key
- Check `MICROSOFT_CLIENT_ID` is set
- Run `python scripts/verify_connection.py` to diagnose

**Authentication fails:**
- Verify the App Registration allows Device Code Flow (public client)
- Check `MICROSOFT_TENANT` matches your account type

**Sync produces duplicates:**
- Never run two simultaneous syncs — the scheduler prevents this automatically
- If duplicates appeared after a crash, run `full-resync` from the UI

**Delta expired error:**
- Normal after 30 days without sync. The service automatically re-initiates full sync.
