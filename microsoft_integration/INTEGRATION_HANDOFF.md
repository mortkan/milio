# Integration Handoff — How to Incorporate Microsoft into Main Milo

This document describes the MINIMAL changes required to integrate the Microsoft 365 UI
into the main Milo application (e.g., as an "Integraciones" section in Settings).

**⚠️ DO NOT APPLY THESE CHANGES NOW.**

These are instructions for a future developer or AI agent to merge the integration.
The Microsoft integration works perfectly as a standalone service without these changes.

---

## Current State

- **Milo:** runs on port 8000
- **Microsoft Integration:** runs on port 8010 (independent service)
- The Microsoft UI is available at: `http://localhost:8010/microsoft`

---

## Option A: Link from Milo Settings (Minimal — Recommended First Step)

No code changes to Milo needed. Simply add a link in the Milo settings page.

### In `templates/index.html`

Find the settings/ajustes section and add:

```html
<a href="http://localhost:8010/microsoft" target="_blank" class="settings-link">
  <svg><!-- Microsoft logo SVG --></svg>
  Microsoft 365
</a>
```

---

## Option B: Embed the Microsoft Service as a Router (Full Integration)

This requires mounting the Microsoft FastAPI app as a sub-application inside Milo.

### Step 1: Install Microsoft dependencies

Add to `requirements.txt`:
```
msal>=1.28.0,<2.0.0
APScheduler>=3.10.0,<4.0.0
cryptography>=42.0.0,<45.0.0
```

### Step 2: Mount the Microsoft app in `app/server.py`

```python
# In app/server.py, after creating the main FastAPI app:

from microsoft_integration.main import create_app as create_ms_app
ms_app = create_ms_app()
app.mount("/microsoft", ms_app)
```

### Step 3: Update static/CSS path

The Microsoft integration serves its static files at `/static/microsoft/*`.
After mounting, update `microsoft_integration/main.py`:

```python
app.mount("/static/microsoft", StaticFiles(directory=str(static_dir)), name="ms_static")
```

This works as-is — no change needed.

### Step 4: Update navigation links

In `templates/index.html`, add a link to `/microsoft`:

```html
<a href="/microsoft">Microsoft 365</a>
```

### Step 5: Share the database session (optional optimization)

The Microsoft integration uses its own database engine by default (same MariaDB, separate pool).
Optionally, you can share the engine by overriding `microsoft_integration.database.get_engine`
to return the main Milo engine after Milo starts.

---

## Option C: Reverse Proxy (Docker Production)

For production deployment, use nginx to serve both on the same domain:

```nginx
# nginx.conf
location / {
    proxy_pass http://milo:8000;
}

location /microsoft {
    proxy_pass http://ms-integration:8010/microsoft;
}

location /api/microsoft {
    proxy_pass http://ms-integration:8010/api/microsoft;
}

location /static/microsoft {
    proxy_pass http://ms-integration:8010/static/microsoft;
}
```

This requires no code changes to either service.

---

## Database Considerations

- The Microsoft schema must be applied BEFORE Milo starts (if mounting):
  ```bash
  python microsoft_integration/scripts/apply_microsoft_schema.py
  ```
- The `ms_*` tables will coexist safely with Milo tables in the same database.
- The Microsoft integration will never touch Milo tables.

---

## Files Created by Microsoft Integration

See [FILES_MANIFEST.md](FILES_MANIFEST.md) for the complete list.
All files are new — no existing Milo file was modified.

---

## Rollback

To remove the Microsoft integration completely:

1. Stop the Microsoft service
2. Run: `DROP TABLE ms_sync_conflicts, ms_subscriptions, ms_auth_flows, ms_sync_errors, ms_sync_runs, ms_sync_state, ms_entity_links, ms_sync_targets, ms_token_cache, ms_accounts, ms_schema_version;`
3. Remove the `microsoft_integration/` directory

No Milo data will be affected.
