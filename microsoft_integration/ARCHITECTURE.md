# Microsoft Integration — Architecture

## Service Topology

```
┌──────────────────────────────────────────────────────────┐
│                       Milo User                          │
│                                                          │
│   Browser → http://localhost:8000   (Milo main)          │
│   Browser → http://localhost:8010   (MS integration)     │
└──────────────────────────────────────────────────────────┘
             │                              │
             ▼                              ▼
    ┌─────────────────┐         ┌─────────────────────────┐
    │  Milo FastAPI   │         │  Microsoft Integration  │
    │  (port 8000)    │         │  FastAPI (port 8010)    │
    │                 │         │                         │
    │  notes/tasks/   │         │  Auth, Graph, Sync,     │
    │  events tables  │         │  Scheduler, Webhooks    │
    └────────┬────────┘         └───────────┬─────────────┘
             │                              │
             └──────────┐   ┌──────────────┘
                        ▼   ▼
                   ┌──────────────┐
                   │   MariaDB    │
                   │  Database    │
                   │              │
                   │  notes       │ ← Milo tables
                   │  tags        │
                   │  ...         │
                   │              │
                   │  ms_accounts │ ← Microsoft tables
                   │  ms_entity_  │
                   │    links     │
                   │  ms_sync_    │
                   │    runs      │
                   │  ...         │
                   └──────────────┘
```

## Authentication Flow (Device Code)

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant MiloMS as Milo MS Service
    participant MSAL
    participant Entra as Microsoft Entra ID

    User->>Browser: Open /microsoft, click Connect
    Browser->>MiloMS: POST /api/microsoft/auth/device/start
    MiloMS->>MSAL: initiate_device_flow()
    MSAL->>Entra: Request device code
    Entra-->>MSAL: {user_code, verification_uri, device_code}
    MSAL-->>MiloMS: flow data
    MiloMS-->>Browser: {user_code, verification_uri, flow_id}
    Browser-->>User: Show code + URL

    Note over MiloMS: Background thread polls MSAL
    User->>Browser: Open verification_uri
    User->>Entra: Enter user_code, sign in, authorize
    Entra-->>MSAL: Authorization complete

    MiloMS->>MSAL: acquire_token_by_device_flow()
    MSAL-->>MiloMS: {access_token, refresh_token, id_token}
    MiloMS->>MiloMS: Encrypt token cache with Fernet
    MiloMS->>MariaDB: Save encrypted cache in ms_token_cache

    Browser->>MiloMS: GET /api/microsoft/auth/device/{flow_id}/status
    MiloMS-->>Browser: {status: "completed", account: {...}}
```

## Calendar Sync Flow

```mermaid
flowchart TD
    A[Scheduler triggers / Manual sync] --> B{Delta link exists?}
    B -- Yes --> C[Graph delta query with deltaLink]
    B -- No --> D[Graph delta query with time window]
    C --> E{Delta expired?}
    E -- Yes --> D
    D --> F[Fetch changed events]
    F --> G{Direction?}

    G -- milo_to_microsoft --> H[For each Milo event]
    H --> I{ms_entity_links exists?}
    I -- No --> J[Create remote event + extension + link]
    I -- Yes --> K{Hash changed?}
    K -- No --> L[Skip - no change]
    K -- Yes --> M{Conflict?}
    M -- Yes --> N[Record conflict in ms_sync_conflicts]
    M -- No --> O[PATCH remote event]

    G -- microsoft_to_milo --> P[For each remote changed event]
    P --> Q{Link exists?}
    Q -- No --> R{Has Milo extension?}
    R -- Yes --> S[Restore link retroactively]
    R -- No --> T[Create local event + link]
    Q -- Yes --> U{Remote deleted?}
    U -- Yes --> V[Soft-delete local event]
    U -- No --> W[Update local event fields]

    O & J & T & W & V --> X[Save delta link in ms_sync_state]
    X --> Y[Update ms_sync_runs counters]
```

## To Do Sync Flow

```mermaid
flowchart TD
    A[Sync triggered] --> B{Delta link?}
    B -- Yes --> C[Todo delta query]
    B -- No --> D[Full list tasks]
    C & D --> E[Process changes]

    E --> F{For each Milo task}
    F --> G{Has remote link?}
    G -- No --> H[Create To Do task + extension + link]
    G -- Yes --> I{Hash changed?}
    I -- No --> J[Skip]
    I -- Yes --> K{Both sides changed?}
    K -- Yes --> L[Record conflict]
    K -- No --> M[PATCH To Do task]

    E --> N{For each remote changed task}
    N --> O{Link exists?}
    O -- Yes --> P[Update Milo task]
    O -- No --> Q[Create Milo task]
```

## Conflict Resolution Flow

```mermaid
stateDiagram-v2
    [*] --> pending : Both sides changed since last_synced_at
    pending --> resolved : User picks keep_local / keep_microsoft / merge
    pending --> ignored : User dismisses
    resolved --> [*]
    ignored --> [*]
```

## Database Schema

```mermaid
erDiagram
    ms_accounts ||--o{ ms_token_cache : has
    ms_accounts ||--o{ ms_sync_targets : configures
    ms_accounts ||--o{ ms_entity_links : owns
    ms_accounts ||--o{ ms_sync_state : tracks
    ms_accounts ||--o{ ms_sync_runs : history
    ms_accounts ||--o{ ms_sync_errors : errors
    ms_accounts ||--o{ ms_sync_conflicts : conflicts
    ms_accounts ||--o{ ms_subscriptions : webhooks
    ms_accounts ||--o{ ms_auth_flows : auth
    ms_entity_links ||--o{ ms_sync_conflicts : triggers
    ms_sync_runs ||--o{ ms_sync_errors : logs
```

## Directory Structure

```
microsoft_integration/
├── main.py              ← FastAPI app factory + startup/shutdown
├── config.py            ← Pydantic settings from env
├── database.py          ← SQLAlchemy engine + session factory
├── models.py            ← SQLAlchemy ORM for all ms_* tables
├── schemas.py           ← Pydantic DTOs for API and sync engine
├── logging_config.py    ← Structured logging setup
│
├── auth/                ← Authentication layer
│   ├── encryption.py    ← Fernet encryption/decryption
│   ├── token_cache.py   ← Persisted MSAL token cache
│   ├── msal_client.py   ← MSAL PublicClientApplication factory
│   └── device_flow.py   ← Device Code Flow manager + background poll
│
├── graph/               ← Microsoft Graph API v1.0 client
│   ├── client.py        ← Core HTTP client (retry, headers, delta)
│   ├── errors.py        ← GraphError hierarchy
│   ├── retry.py         ← 429/5xx retry with exponential backoff
│   ├── pagination.py    ← @odata.nextLink pagination helpers
│   ├── calendar.py      ← Calendar and event operations
│   ├── todo.py          ← To Do list and task operations
│   ├── profile.py       ← User profile
│   └── extensions.py    ← Open Extensions (com.milo.sync)
│
├── sync/                ← Bidirectional sync engine
│   ├── engine.py        ← Orchestrator: runs sync for account(s)
│   ├── calendar_sync.py ← Calendar ↔ Milo event sync
│   ├── todo_sync.py     ← To Do ↔ Milo task sync
│   ├── conflict_resolver.py ← Conflict detection and recording
│   ├── mapping.py       ← DTO ↔ Graph payload field mapping
│   ├── local_repository.py  ← Milo DB adapter (raw SQL, no ORM dependency)
│   ├── remote_repository.py ← Graph responses → DTOs
│   ├── scheduler.py     ← APScheduler async job
│   └── locks.py         ← MariaDB advisory locks
│
├── api/                 ← FastAPI routes
│   ├── auth_routes.py
│   ├── account_routes.py
│   ├── sync_routes.py
│   ├── config_routes.py
│   ├── conflict_routes.py
│   ├── webhook_routes.py
│   └── health_routes.py
│
├── ui/                  ← Independent UI (no Milo CSS/JS)
│   ├── templates/       ← Jinja2 HTML templates
│   └── static/          ← CSS, JavaScript
│
├── sql/                 ← SQL migration files
│   └── 001_microsoft_schema.sql
│
├── scripts/             ← Operational scripts
├── tests/               ← All Microsoft tests (never modify Milo tests)
└── docs/                ← Documentation
```

## Key Design Decisions

### 1. No modification of Milo files
The integration lives entirely under `microsoft_integration/`. The only shared resource is the MariaDB database (via `ms_*` tables).

### 2. Milo as source of truth
Milo's data model is authoritative. Microsoft is an integration target. Microsoft-specific fields that don't map to Milo (e.g., Graph-only metadata) are not stored in Milo.

### 3. Adapter pattern for Milo data access
`sync/local_repository.py` is the single point of contact with Milo tables. It uses raw SQL (never Milo's ORM) and returns DTOs, decoupling the sync engine from Milo schema changes.

### 4. Idempotency via sync hashes
A SHA-256 hash of syncable fields is stored in `ms_entity_links.sync_hash`. Sync only writes to Microsoft if the local hash has changed since last sync.

### 5. Delta-first approach
After the first full sync, subsequent syncs use `@odata.deltaLink` to fetch only changed items. Delta tokens expire after ~30 days of inactivity; the service handles this gracefully with automatic full-sync fallback.

### 6. Conflict safety
When both sides change since the last `last_synced_at`, a conflict is recorded and surfaced in the UI. The default policy is `manual` — no data is overwritten without user intervention.
