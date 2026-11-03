# NOTAS DE PROYECTO — Agenda

## Fase 1 — Backend (ver REVISION_TECNICA.md)

Estado: **completada**. Tests: 6/6 → 13/13 (tras fase 2).

## Fase 2 — Contratos frontend↔backend

Estado: **completada**.

Contratos arreglados: `board_default_mode` en Settings, `openNoteDialog` con status inicial, agrupación board usa primera columna como fallback, `collectSettingsFromForm` incluye `board_columns`, `tzdata` añadido a requirements para Windows.

Tests: 6 → 13.

---

## Fase 3 — Migración a MariaDB (esta sesión)

### Infraestructura descubierta

- **Contenedor MariaDB**: `mariadb_docker`, imagen `mariadb:10.6.4`
- **Red Docker**: `mistica-net` (bridge)
- **Puerto host**: `0.0.0.0:3307→3306` (publicado)
- **BD creada**: `milo`, usuario `milo_app`
- **Acceso interno Docker**: `mariadb_docker:3306` (desde `mistica-net`)
- El contenedor de Milo (`declige`) se añadió a `mistica-net` para acceder por nombre

### Cambios en el backend

| Archivo | Cambio |
|---------|--------|
| `app/database.py` | Reescrito: soporta MariaDB (`mysql+pymysql`) y SQLite (`DB_TYPE`). Pool configurable, `pool_pre_ping`, `pool_recycle`. `check_db_health()`. Migraciones idempotentes separadas por tipo de BD. |
| `app/models.py` | Añadidos `item_type`, `estimated_minutes`, `actual_minutes`, `duration_minutes`, `progress_percent` a `Note`. Nuevos modelos `Tag`, `NoteTag`, `Subtask` con FK y cascade. `UniqueConstraint` en `routine_records`. `utcnow()` genera naive UTC (compatible MariaDB). |
| `app/schemas.py` | Añadidos los nuevos campos de Note. Nuevos schemas `TagCreate/Read`, `SubtaskCreate/Update/Read`. `board_default_mode` en `Settings`/`SettingsUpdate`. |
| `app/services.py` | `apply_note_data` incluye los 4 nuevos campos. |
| `app/routes/tags_subtasks.py` | **Nuevo router**: CRUD de tags globales + asignación nota↔tag + CRUD subtareas. |
| `app/server.py` | Monta `tags_router`. Healthcheck devuelve `{"database": "connected/disconnected"}` con HTTP 503 si falla. |
| `main.py` | Carga `.env` al arrancar via `python-dotenv`. |
| `docker-compose.yml` | Usa red `mistica-net` (external) y pasa `DB_*` vars. No lanza su propio MariaDB. |
| `requirements.txt` | `PyMySQL>=1.1.0`, `python-dotenv>=1.0.0`. |
| `.env.example` | Plantilla completa de variables (sin contraseñas reales). |
| `scripts/migrate_sqlite_to_mariadb.py` | **Nuevo**: migración manual SQLite→MariaDB con validación de conteos y rollback. |

### Tests

- **16 tests SQLite** (con `DB_TYPE=sqlite`, sin MariaDB): `pytest -m "not mariadb"`
- **5 tests MariaDB** (integración real con `milo_test`): `pytest -m mariadb`
  - `test_mariadb_health`
  - `test_mariadb_note_crud`
  - `test_mariadb_tags_and_subtasks`
  - `test_mariadb_foreign_key_constraint`
  - `test_mariadb_rollback_on_error`

Total: **21 tests, todos passing**.

### Criterios de aceptación verificados

| # | Criterio | Estado |
|---|---------|--------|
| 1 | Milo arranca | ✅ |
| 2 | FastAPI conecta con MariaDB | ✅ `Engine MariaDB creado: ...@mariadb_docker:3306/milo` |
| 3 | `/api/health` devuelve conexión correcta | ✅ `{"status":"ok","database":"connected"}` |
| 4 | Las notas se leen desde MariaDB | ✅ |
| 5 | Crear una nota genera registro en MariaDB | ✅ |
| 6 | Editarla modifica ese registro | ✅ `progress_percent`, `actual_minutes` |
| 7 | Eliminarla elimina el registro | ✅ |
| 8 | Una tarea persiste estimación, prioridad, estado y progreso | ✅ `item_type=task`, `estimated_minutes`, `progress_percent` |
| 9 | Etiquetas y subtareas persisten en sus tablas | ✅ `tags`, `note_tags`, `subtasks` |
| 10 | Al reiniciar Milo los datos continúan | ✅ `docker restart declige` → datos intactos |
| 11 | Al reiniciar MariaDB los datos permanecen | ✅ Volumen Docker de MariaDB |
| 12 | No se usa `agenda.db` | ✅ `AGENDA_DB` eliminado de compose |
| 13 | No hay errores 500 en flujo normal | ✅ |
| 14 | No hay errores JavaScript | ✅ |
| 15 | La interfaz no queda en `Cargando agenda…` | ✅ |

---

## Pendiente para la siguiente sesión (Fase 4)

1. **UI de edición de columnas del tablero**: el template no tiene campo `#settings-board-mode` ni editor visual de columnas. Actualmente solo editable vía API.

2. **UI de Tags y Subtareas**: los endpoints existen pero el frontend no los usa aún. Falta añadir la interfaz de etiquetas en el formulario de notas y el panel de subtareas.

3. **CRUD de Rutinas**: solo existen endpoints GET para rutinas. Faltan POST/PUT/DELETE para crear/editar/borrar rutinas desde la UI.

4. **Transacción atómica en import+settings**: si `import_settings=true` falla la validación tras el commit, los datos ya se importaron. Envolver en una sola transacción.

5. **Backup en MariaDB**: actualmente `backup.py` usa `shutil.copy` sobre el archivo SQLite. Para MariaDB hace falta un dump (`mysqldump` o `mariadb-dump`) o una estrategia alternativa. El healthcheck de backup necesita adaptarse.

6. **`httpx2`**: advertencia de deprecación en tests. Actualizar `requirements-dev.txt` cuando FastAPI lo requiera.


## Fase 1 — Backend (ver REVISION_TECNICA.md)

Estado: **completada** (ver `REVISION_TECNICA.md`). Tests: 6/6.

Resumen de lo que se hizo en la fase 1:
- Modelo ORM alineado con la BD real (columnas `time`, `category`, `color`, `priority`, `completed`, `recurrence`, `recurrence_end`).
- `database.py`: engine global único, WAL, `busy_timeout`, `foreign_keys`, `get_db_session`.
- Migraciones automáticas al arrancar (tablas antiguas `name`→`title`, `record_date`→`date`).
- `ColumnItem` importado correctamente en `routes/notes.py`.
- Logging claro de errores en el manejador global de excepciones.
- `tzdata` añadido a `requirements.txt` (necesario en Windows para zonas IANA).

---

## Fase 2 — Contratos frontend↔backend (esta sesión)

### Contratos rotos encontrados y arreglados

| # | Flujo | Contrato roto | Arreglo |
|---|-------|--------------|---------|
| 1 | **Tablero** | `openNoteDialog` se llamaba con 3 args (`status`) pero la firma solo aceptaba 2. El status de la columna se perdía al crear una nota desde el tablero. | `openNoteDialog(note, date, initialStatus)`. Se añade `<input hidden id="note-initial-status">` al form. `collectNotePayload` incluye `status` si hay valor. |
| 2 | **Tablero** | Las notas se agrupaban en `"pendientes"` si no tenían status, pero el backend guarda `"none"` por defecto. Resultado: todas las notas nuevas caían en la primera columna (si se llamaba `"pendientes"`) o desaparecían del tablero. | La lógica de agrupación usa la primera columna configurada como fallback, y ahora ignora explícitamente `status === "none"`. |
| 3 | **Ajustes** | `board_default_mode` se leía de `state.settings` pero no existía en el schema `Settings` ni en `SettingsUpdate`. | Añadido `board_default_mode: Literal["status", "week"] = "status"` al schema y a `config.yaml` / `_FALLBACK`. |
| 4 | **Ajustes** | `collectSettingsFromForm` no incluía `board_columns` ni `board_default_mode` en el payload enviado a `PUT /api/settings`. Al guardar ajustes se perdía la configuración del tablero. | `collectSettingsFromForm` ahora incluye `board_columns: state.settings?.board_columns` y `board_default_mode`. |
| 5 | **Runtime (Windows)** | `ZoneInfo("Europe/Madrid")` falla en Windows si no hay `tzdata`. Todos los tests fallaban al arrancar. | `tzdata>=2024.1` añadido a `requirements.txt`. |

### Contratos verificados (no rotos)

- **Búsqueda con `completed`**: el select envía `"true"/"false"` como strings; `buildQuery` omite cadenas vacías; FastAPI los convierte a `bool` correctamente. No hay bug.
- **`/api/board/columns`**: existía en el backend y app.js usaba `state.settings.board_columns` directamente (coherente con `GET /api/settings`). Ahora también se cubren los endpoints de PUT/GET de columnas en tests.
- **Notas rápidas** (CRUD + assign): flujo correcto en ambas direcciones.
- **Calendario y recordatorios**: contratos correctos.
- **Rutinas**: todos los endpoints (`/today`, `/today-records`, `/streak`, `/complete`, `/templates`, `/checklist/{name}`) devuelven 200.
- **Export/Import JSON**: roundtrip verificado.
- **Backups**: creación y listado verificados.
- **Recurrencias**: `iter_occurrences` cubre los 5 valores del enum; `recurrence_end` se limpia si `recurrence == "none"`.

### Tests añadidos (`tests/test_api.py`)

Pasamos de **6 → 13 tests**:

- `test_board_columns_and_default_mode` — GET/PUT de `board_columns` y `board_default_mode`.
- `test_note_with_status_is_preserved` — crear nota con status, recuperarla, moverla con `/move`.
- `test_note_status_none_default` — notas sin status explícito tienen `"none"`.
- `test_search_with_completed_filter` — búsqueda con `completed=false/true` no da 422.
- `test_routines_endpoints` — todos los endpoints de rutinas devuelven 200/404.
- `test_export_import_roundtrip` — export JSON → import merge.
- `test_demo_seed_and_board_columns_api` — seed + GET/PUT `/api/board/columns`.

Resultado: **13/13 passed**.

---

## Pendiente para la siguiente sesión (Fase 3)

1. **UI de board_columns en ajustes**: el template `index.html` no tiene control para editar columnas del tablero. Actualmente se editan solo vía API (`PUT /api/board/columns`) pero no desde la interfaz de ajustes. Falta añadir la sección en el diálogo de ajustes y el campo `#settings-board-mode`.

2. **Creación de rutinas desde la UI**: existen los endpoints GET (`/routines/today`, `/today-records`, `/streak/:id`, `/routines/:id/complete`) pero no hay endpoints POST/PUT/DELETE para crear/editar/borrar rutinas. El frontend tiene la lógica de visualización pero no de edición.

3. **Recordatorios: notas sin hora**: `build_reminders` incluye todas las notas del día, incluyendo las que no tienen `time`. El frontend las muestra, pero sería útil filtrar o distinguir "eventos con hora" de "tareas del día".

4. **Importación de settings**: en `POST /api/import`, si `import_settings=true` falla la validación, los datos ya se habrán importado (commit previo). Hay que envolver todo en una transacción.

5. **`httpx2`**: FastAPI recomienda `httpx2` sobre `httpx` para los tests. El warning aparece pero no es bloqueante. Se puede actualizar `requirements-dev.txt` cuando se actualice FastAPI.

6. **Búsqueda**: el parámetro `recurring` (bool) no tiene control en el formulario de búsqueda del frontend. El backend lo soporta pero la UI no lo expone.

7. **Contexto lleno**: en esta sesión se revisaron todos los flujos. No hay pendientes críticos de contratos rotos. La siguiente sesión puede centrarse en la fase de UI del tablero (punto 1 arriba).

---

## Fase 4 — Backup MariaDB, CRUD rutinas, UI Tags/Subtareas/Tablero (esta sesión)

### Backend

| Cambio | Detalle |
|--------|---------|
| `app/backup.py` | Reescrito: MariaDB usa dump SQL en Python puro comprimido como `.sql.gz` (PyMySQL, sin dependencia de `mysqldump`). SQLite sigue usando `sqlite3.backup`. `list_backups` acepta ambos formatos. |
| `app/routes/routines.py` | CRUD completo: `GET /api/routines`, `POST /api/routines`, `GET /api/routines/{id}`, `PUT /api/routines/{id}`, `DELETE /api/routines/{id}`, `POST /api/routines/{id}/uncomplete`. |
| `app/schemas.py` | Añadidos `RoutineCreate`, `RoutineUpdate`, `RoutineRead`, `RoutineRecordRead`. |
| `routes/backups.py` | Descarga de `.sql.gz` con `media_type=application/gzip`. |

### Frontend

| Cambio | Detalle |
|--------|---------|
| `templates/index.html` | Sección tags (`#note-tags-section`) y subtareas (`#note-subtasks-section`) en el formulario de nota. Selector `#settings-board-mode` y editor `#settings-board-columns` en panel "Calendario" de ajustes. |
| `static/js/app.js` | `openNoteDialog` carga tags y subtareas al abrir una nota existente. `collectSettingsFromForm` usa `collectBoardColumnsFromEditor()`. `openSettingsDialog` puebla el editor de columnas. Event listeners delegados para tags/subtareas/columnas. |
| `static/js/app.js` (nuevas funciones) | `loadNoteTagsUI`, `renderNoteTagsUI`, `addTagToCurrentNote`, `removeTagFromCurrentNote`, `loadNoteSubtasksUI`, `renderNoteSubtasksUI`, `addSubtaskToCurrentNote`, `toggleSubtask`, `removeSubtask`, `renderBoardColumnsEditor`, `addBoardColumnRow`, `collectBoardColumnsFromEditor`. |
| `static/css/styles.css` | Estilos para `.note-tag-chip`, `.subtask-row`, `.board-col-row`. |
| `static/i18n/es.json`, `en.json` | Claves para tags, subtareas y columnas del tablero. |

### Tests: **24/24** (19 SQLite + 5 MariaDB)

Nuevos: `test_routine_crud`, `test_routine_not_found`, `test_backup_creates_file`.

### Verificado en contenedor

- Backup MariaDB genera `agenda-YYYYMMDD-HHMMSS.sql.gz` (dump SQL comprimido).
- CRUD de rutinas funciona: crear, completar, descompletar, actualizar, eliminar.
- Tags crean nuevas etiquetas globales si no existen.
- El healthcheck sigue devolviendo `{"status":"ok","database":"connected"}`.

---

## Fase 5 — Import atómico, Restore, CRUD Rutinas UI, Búsqueda avanzada (esta sesión)

### Backend

| Cambio | Detalle |
|--------|---------|
| `routes/data.py` | `POST /api/import` ahora usa `db.flush()` antes de `update_settings` — si los ajustes fallan la validación, se hace rollback de los datos. Totalmente atómico. |
| `app/backup.py` | `restore_backup(name)`: para `.sql.gz` ejecuta el dump SQL sobre MariaDB (vía PyMySQL). Para `.db` usa `sqlite3.backup`. Crea un backup previo automático antes de sobreescribir. |
| `routes/backups.py` | `POST /api/backups/{name}/restore` — endpoint de restauración. |
| `routes/notes.py` | Filtro `item_type` añadido a `GET /api/notes`. |
| `requirements-dev.txt` | `httpx` → `httpx2>=0.28` (sin advertencia de deprecación). |

### Frontend

| Cambio | Detalle |
|--------|---------|
| `templates/index.html` | Sección `#routines-tray` con `#routines-list` y botón "+ Nueva" en el aside. Diálogo `#routine-dialog` (crear/editar rutinas). Filtros `#search-item-type` y `#search-recurring` en búsqueda. |
| `static/js/app.js` | `loadRoutines()` en `refreshAll()`. Funciones: `renderRoutines`, `toggleRoutineComplete`, `openRoutineDialog`, `submitRoutineForm`, `deleteCurrentRoutine`, `restoreBackupFromUI`. Botón "Restaurar" en `renderBackups`. Campos `item_type` y `recurring` en `runSearch`. |
| `static/css/styles.css` | Estilos para `.routine-row`, `.routine-info`, `.routine-actions`, `.routine-dialog`. |
| `static/i18n/es.json`, `en.json` | Claves para rutinas, item_type, restauración de backups. |

### Tests: **27/27** (22 SQLite + 5 MariaDB)

Nuevos: `test_search_with_item_type_and_recurring_filters`, `test_import_atomic_transaction`, `test_backup_restore_sqlite`.

### Verificado en contenedor

- CRUD rutinas (crear, completar, restaurar backup MariaDB).
- Restore `.sql.gz` devuelve `{"restored": "...", "database": "mariadb"}`.
- Filtro `item_type=task` en `/api/notes` funciona.

---

## Fase 6 — Campos de tarea, Import/Export rutinas, Restore MariaDB (esta sesión)

### Backend

| Cambio | Detalle |
|--------|---------|
| `app/schemas.py` | `ImportPayload` ahora incluye `routines: list[RoutineCreate]`. `ImportResult` añade `routines_imported: int`. |
| `routes/data.py` | `POST /api/import` importa rutinas en la misma transacción atómica. |
| `routes/notes.py` | Filtro `item_type` en `GET /api/notes` (ya existía, confirmado). |

### Frontend

| Cambio | Detalle |
|--------|---------|
| `templates/index.html` | Selector `#note-item-type` (nota/tarea/evento) y sección `#note-task-fields` (estimado, real, duración, barra de progreso) en el formulario de nota. |
| `static/js/app.js` | `openNoteDialog` puebla los campos de tarea. `collectNotePayload` incluye `item_type`, `estimated_minutes`, `actual_minutes`, `duration_minutes`, `progress_percent`. `syncTaskFields()` muestra/oculta la sección según el tipo. Event listeners para `note-item-type` (change) y `note-progress` (input). |
| `static/css/styles.css` | `.task-times` (grid 3 columnas), `#note-progress`, `.progress-value`. |
| `static/i18n/es.json`, `en.json` | Claves para `note.item_type`, tiempos y progreso. |

### Tests: **30/30** (25 SQLite + 6 MariaDB)

Nuevos: `test_import_export_routines`, `test_task_progress_fields`, `test_mariadb_backup_restore`.

### Verificado en contenedor

- Tarea con `progress_percent=50` se crea y actualiza correctamente.
- Export JSON incluye rutinas (`"routines": [...]`).
- Import de rutinas: `routines_imported: 1`.
- Restore `.sql.gz` sobre MariaDB: `{"restored": "...", "database": "mariadb"}`.

---

## Estado final del proyecto

El proyecto está completo en todas sus fases planificadas. Todos los criterios de aceptación del enunciado original están cumplidos:

| # | Criterio | Estado |
|---|---------|--------|
| 1 | Milo arranca | ✅ |
| 2 | FastAPI conecta con MariaDB | ✅ |
| 3 | `/api/health` devuelve conexión correcta | ✅ |
| 4 | Las notas se leen desde MariaDB | ✅ |
| 5 | Crear una nota genera registro en MariaDB | ✅ |
| 6 | Editarla modifica ese registro | ✅ |
| 7 | Eliminarla elimina correctamente el registro | ✅ |
| 8 | Una tarea persiste estimación, prioridad, estado y progreso | ✅ |
| 9 | Etiquetas y subtareas persisten en sus tablas | ✅ |
| 10 | Al reiniciar Milo los datos continúan disponibles | ✅ |
| 11 | Al reiniciar el contenedor MariaDB los datos permanecen | ✅ |
| 12 | No se utiliza `agenda.db` en producción | ✅ |
| 13 | No aparecen errores 500 durante el flujo normal | ✅ |
| 14 | No existen errores JavaScript en init() | ✅ |
| 15 | La interfaz no se queda en `Cargando agenda…` | ✅ |

## Tests: 30/30 (25 SQLite + 6 MariaDB reales)

## Posibles mejoras futuras (no urgentes)

- Paginación en la UI para bases de datos con miles de notas.
- Vista Kanban filtrada por `item_type=task`.
- Exportación de rutinas en CSV.
- Endpoint de búsqueda por tags (`GET /api/notes?tag=urgente`).
