# Microsoft Integration — Implementation Report

## Summary

Full Microsoft 365 integration for Milo has been implemented as an isolated,
independent FastAPI service under `microsoft_integration/`. No existing Milo
files were modified.

---

## Architecture

- **Service:** FastAPI on port 8010 (configurable)
- **Database:** Shared MariaDB — exclusive use of `ms_*` tables
- **Auth:** MSAL Device Code Flow (primary) + Auth Code PKCE (prepared)
- **Token storage:** Fernet-encrypted MSAL cache in `ms_token_cache`
- **Sync:** Bidirectional with delta queries, conflict detection, scheduler
- **UI:** Independent Jinja2/CSS/JS — no dependency on Milo's UI stack

---

## Microsoft Graph APIs Used

| API | Purpose |
|-----|---------|
| `GET /me` | User profile |
| `GET /me/calendars` | List calendars |
| `POST /me/calendars` | Create calendar |
| `GET /me/calendars/{id}/events/delta` | Delta sync events |
| `POST /me/calendars/{id}/events` | Create event |
| `PATCH /me/calendars/{id}/events/{id}` | Update event |
| `DELETE /me/calendars/{id}/events/{id}` | Delete event |
| `GET /me/todo/lists` | List To Do lists |
| `POST /me/todo/lists` | Create To Do list |
| `GET /me/todo/lists/{id}/tasks/delta` | Delta sync tasks |
| `POST /me/todo/lists/{id}/tasks` | Create task |
| `PATCH /me/todo/lists/{id}/tasks/{id}` | Update task |
| `DELETE /me/todo/lists/{id}/tasks/{id}` | Delete task |
| `POST /{resource}/extensions` | Add Milo Open Extension |

All endpoints use **Microsoft Graph v1.0** (no beta).

---

## Permissions Required

| Permission | Type | Purpose |
|-----------|------|---------|
| `User.Read` | Delegated | Read user profile |
| `Calendars.ReadWrite` | Delegated | Full calendar access |
| `Tasks.ReadWrite` | Delegated | Full To Do access |
| `offline_access` | Delegated | Refresh token persistence |

---

## Tables Created

| Table | Rows |
|-------|------|
| `ms_schema_version` | Migration tracking |
| `ms_accounts` | Connected Microsoft accounts |
| `ms_token_cache` | Encrypted MSAL token caches |
| `ms_sync_targets` | Active sync targets per account |
| `ms_entity_links` | Milo ↔ Microsoft entity mapping |
| `ms_sync_state` | Delta tokens and sync windows |
| `ms_sync_runs` | Sync operation history |
| `ms_sync_errors` | Per-entity error log |
| `ms_sync_conflicts` | Conflict queue |
| `ms_subscriptions` | Webhook subscriptions |
| `ms_auth_flows` | Device code auth flow states |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/microsoft/health` | Service health |
| GET | `/api/microsoft/accounts/{id}/connection-test` | Live Graph test |
| GET | `/api/microsoft/accounts` | List accounts |
| GET | `/api/microsoft/accounts/{id}` | Get account |
| POST | `/api/microsoft/auth/device/start` | Start Device Code Flow |
| GET | `/api/microsoft/auth/device/{flow_id}/status` | Flow status |
| POST | `/api/microsoft/accounts/{id}/disconnect` | Disconnect account |
| POST | `/api/microsoft/accounts/{id}/reauthorize` | Mark for reauth |
| GET | `/api/microsoft/accounts/{id}/calendars` | List calendars |
| GET | `/api/microsoft/accounts/{id}/todo-lists` | List To Do lists |
| GET | `/api/microsoft/accounts/{id}/config` | Get config |
| PUT | `/api/microsoft/accounts/{id}/config` | Update config |
| POST | `/api/microsoft/accounts/{id}/sync` | Manual sync |
| POST | `/api/microsoft/accounts/{id}/full-resync` | Full resync |
| POST | `/api/microsoft/accounts/{id}/sync-preview` | Dry-run preview |
| GET | `/api/microsoft/accounts/{id}/sync-history` | Sync history |
| GET | `/api/microsoft/conflicts` | List conflicts |
| GET | `/api/microsoft/conflicts/{id}` | Conflict details |
| POST | `/api/microsoft/conflicts/{id}/resolve` | Resolve conflict |
| POST | `/api/microsoft/webhooks/graph` | Graph notifications |
| POST | `/api/microsoft/webhooks/lifecycle` | Lifecycle events |

---

## Files Created

See [FILES_MANIFEST.md](FILES_MANIFEST.md).

---

## Tests

All tests run without real Microsoft credentials:

```bash
cd microsoft_integration
pytest tests/ -v
```

Test coverage:
- ✅ Fernet encryption/decryption
- ✅ Wrong key detection
- ✅ GraphError hierarchy
- ✅ Retry on 429 / server errors
- ✅ No retry on auth errors
- ✅ Task field mapping (title, status, due date, recurrence, description)
- ✅ Event field mapping (subject, start/end, all-day, location, recurrence)
- ✅ Sync hash stability (idempotency basis)
- ✅ Conflict detection (both-changed vs single-changed)
- ✅ Conflict resolution state machine
- ✅ DB configuration validation
- ✅ API endpoint accessibility

---

## Live Tests

Live tests against real Microsoft accounts require:

```env
MICROSOFT_LIVE_TESTS=true
MICROSOFT_CLIENT_ID=...
MICROSOFT_TOKEN_ENCRYPTION_KEY=...
```

These were NOT run during implementation (no credentials available).
They are documented in the test suite comments with clear `MICROSOFT_LIVE_TESTS=true` guards.

The manual test plan (section 72 of the specification) is documented below:

### Manual Test Plan (requires live credentials)

1. Start service: `uvicorn microsoft_integration.main:app --port 8010`
2. Open `http://localhost:8010/microsoft`
3. Click "Conectar cuenta" → observe Device Code modal
4. Open verification URL in browser, enter code
5. Verify account appears in UI with correct display name
6. Navigate to configuration → observe calendars list
7. Navigate to To Do lists → observe lists
8. Select/create "Milo" calendar and "Milo" list
9. Create a test task in Milo (`item_type='task'`)
10. Click "Sincronizar ahora"
11. Verify task appears in Microsoft To Do
12. Edit task in Microsoft To Do
13. Sync again → verify Milo task updated
14. Create a test event in Milo (`item_type='event'`)
15. Sync → verify event in Outlook Calendar
16. Edit in Outlook → sync → verify Milo updated
17. Sync again (no changes) → verify created=0, updated=0
18. Disconnect and reconnect → verify mappings preserved

**Status:** Pending live credentials.

---

## Technical Decisions

### 1. Device Code Flow first
Milo runs locally without HTTPS. Auth Code + PKCE requires a public redirect URI. Device Code Flow is secure and works on any network.

### 2. Fernet for token encryption
AES-128-CBC with HMAC. Simple to use, well-audited via `cryptography` library. The key never appears in code or logs.

### 3. Advisory locks via MariaDB GET_LOCK
Avoids adding Redis/memcached dependency. Prevents scheduler + manual sync collisions. Falls back to in-memory threading lock for SQLite (tests).

### 4. No ORM dependency on Milo tables
`local_repository.py` uses raw SQL and introspects actual columns at runtime. This makes it resilient to Milo schema changes by the parallel development.

### 5. PATCH only (not PUT)
All Microsoft updates use PATCH to avoid overwriting fields Milo doesn't manage.

### 6. Immutable IDs for Calendar
`Prefer: IdType="ImmutableId"` header ensures Calendar event IDs don't change when events are moved between calendars.

---

## Limitations

1. **No live test evidence** — Real credentials were not available during implementation. All tests are mocked.
2. **Recurrence subtleties** — Complex recurrence patterns (e.g., "every 2nd Tuesday of the month") are preserved in Microsoft but not imported to Milo.
3. **Subtasks** — Milo subtasks remain local; they are not synced to To Do (no direct equivalent).
4. **Outlook attachments** — Not synced (out of scope).
5. **Calendar categories** — Tags mapped to categories where Microsoft supports it (≤5 per item due to Graph limits).

---

## Pasos de Integración Final con Milo

See [INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md) for detailed merge instructions.

Short summary:
- **Option A (Minimal):** Add link from Milo settings to `http://localhost:8010/microsoft`
- **Option B (Full):** Mount as sub-application in `app/server.py` + share DB engine
- **Option C (Production):** nginx reverse proxy — no code changes
