# FILES_MANIFEST.md — Microsoft Integration

All files created by the Microsoft integration agent.

## CREATED

```
microsoft_integration/__init__.py
microsoft_integration/main.py
microsoft_integration/config.py
microsoft_integration/database.py
microsoft_integration/models.py
microsoft_integration/schemas.py
microsoft_integration/logging_config.py

microsoft_integration/auth/__init__.py
microsoft_integration/auth/encryption.py
microsoft_integration/auth/token_cache.py
microsoft_integration/auth/msal_client.py
microsoft_integration/auth/device_flow.py

microsoft_integration/graph/__init__.py
microsoft_integration/graph/client.py
microsoft_integration/graph/errors.py
microsoft_integration/graph/retry.py
microsoft_integration/graph/pagination.py
microsoft_integration/graph/calendar.py
microsoft_integration/graph/todo.py
microsoft_integration/graph/profile.py
microsoft_integration/graph/extensions.py

microsoft_integration/sync/__init__.py
microsoft_integration/sync/engine.py
microsoft_integration/sync/calendar_sync.py
microsoft_integration/sync/todo_sync.py
microsoft_integration/sync/conflict_resolver.py
microsoft_integration/sync/mapping.py
microsoft_integration/sync/local_repository.py
microsoft_integration/sync/remote_repository.py
microsoft_integration/sync/scheduler.py
microsoft_integration/sync/locks.py

microsoft_integration/api/__init__.py
microsoft_integration/api/auth_routes.py
microsoft_integration/api/account_routes.py
microsoft_integration/api/sync_routes.py
microsoft_integration/api/config_routes.py
microsoft_integration/api/conflict_routes.py
microsoft_integration/api/webhook_routes.py
microsoft_integration/api/health_routes.py

microsoft_integration/ui/templates/microsoft.html
microsoft_integration/ui/templates/accounts.html
microsoft_integration/ui/templates/sync.html
microsoft_integration/ui/templates/conflicts.html

microsoft_integration/ui/static/microsoft.css
microsoft_integration/ui/static/microsoft.js
microsoft_integration/ui/static/microsoft_api.js

microsoft_integration/sql/001_microsoft_schema.sql
microsoft_integration/sql/README.md

microsoft_integration/scripts/apply_microsoft_schema.py
microsoft_integration/scripts/verify_connection.py
microsoft_integration/scripts/sync_once.py
microsoft_integration/scripts/reset_microsoft_sync_state.py

microsoft_integration/tests/__init__.py
microsoft_integration/tests/test_auth.py
microsoft_integration/tests/test_graph_client.py
microsoft_integration/tests/test_calendar_sync.py
microsoft_integration/tests/test_todo_sync.py
microsoft_integration/tests/test_conflicts.py
microsoft_integration/tests/test_database.py
microsoft_integration/tests/test_api.py

microsoft_integration/.env.microsoft.example
microsoft_integration/requirements.txt
microsoft_integration/Dockerfile
microsoft_integration/compose.microsoft.yml
microsoft_integration/README.md
microsoft_integration/ARCHITECTURE.md
microsoft_integration/DATABASE.md
microsoft_integration/MICROSOFT_SETUP.md
microsoft_integration/INTEGRATION_HANDOFF.md
microsoft_integration/IMPLEMENTATION_REPORT.md
microsoft_integration/FILES_MANIFEST.md
```

## MODIFIED EXISTING FILES

```
NONE
```

All changes are exclusively new files under `microsoft_integration/`.
No Milo files were modified, renamed, or deleted.
