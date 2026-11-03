# Agenda

Agenda personal web con calendario, notas, tareas, eventos, recordatorios, repeticiones y captura rápida. Backend FastAPI + **MariaDB** y frontend vanilla sin paso de compilación.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![MariaDB](https://img.shields.io/badge/MariaDB-10.6-003545)
![JavaScript](https://img.shields.io/badge/JavaScript-ES%20Modules-F7DF1E)

## Funciones

- Vista de mes, semana, día y tablero Kanban.
- Notas, tareas (con estimación y progreso) y eventos (con duración).
- Etiquetas y subtareas con relaciones reales en BD.
- Repeticiones diarias, semanales, mensuales y anuales con fecha de fin opcional.
- Panel lateral con las notas del día seleccionado.
- Bandeja de notas rápidas: editar, asignar a una fecha o eliminar.
- Recordatorios de notas de hoy y vencidas.
- Búsqueda por texto con filtros de fecha, categoría, prioridad y estado.
- Ajustes aplicables en caliente: idioma, tema, tipografía, colores, calendario, campos visibles, etiquetas, atajos y backups.
- Exportación JSON/CSV e importación JSON en modo `merge` o `replace`.
- Copias de seguridad automáticas y manuales con retención configurable.
- Datos de demostración para probar la aplicación rápidamente.

## Configuración MariaDB

La aplicación se conecta a MariaDB mediante variables de entorno. Copia `.env.example` como `.env` y rellena los valores:

```env
DB_TYPE=mariadb
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=milo
DB_USER=milo_app
DB_PASSWORD=CAMBIAR_PASSWORD
```

Variables de conexión disponibles:

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `DB_TYPE` | `mariadb` | `mariadb` o `sqlite` (solo desarrollo) |
| `DB_HOST` | `127.0.0.1` | Host de MariaDB |
| `DB_PORT` | `3306` | Puerto de MariaDB |
| `DB_NAME` | `milo` | Nombre de la base de datos |
| `DB_USER` | `milo_app` | Usuario de la aplicación |
| `DB_PASSWORD` | — | Contraseña (nunca en Git) |
| `DB_POOL_SIZE` | `5` | Tamaño del pool de conexiones |
| `DB_MAX_OVERFLOW` | `10` | Conexiones extra en pico |
| `DB_POOL_RECYCLE` | `1800` | Segundos de vida de una conexión |
| `DB_CONNECT_TIMEOUT` | `10` | Timeout de conexión en segundos |

Para comprobar la conectividad desde la línea de comandos:

```bash
mariadb -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p "$DB_NAME"
```

### Preparar la base de datos

```sql
CREATE DATABASE IF NOT EXISTS milo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'milo_app'@'%' IDENTIFIED BY 'TU_PASSWORD';
GRANT ALL PRIVILEGES ON milo.* TO 'milo_app'@'%';
FLUSH PRIVILEGES;
```

El esquema se crea automáticamente al arrancar la aplicación (`Base.metadata.create_all`).

## Inicio rápido (desarrollo local)

Requiere Python 3.11 o superior y MariaDB accesible.

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copia y edita el archivo de entorno:
cp .env.example .env
# Edita .env con tu contraseña real

python main.py
```

Para desarrollo sin MariaDB (SQLite local):

```bash
DB_TYPE=sqlite python main.py
```

Abre <http://127.0.0.1:8000>. Documentación de la API en <http://127.0.0.1:8000/docs>.

Opciones de arranque:

```bash
python main.py --seed                  # carga datos de ejemplo
python main.py --reload                # recarga automática
python main.py --host 0.0.0.0 --port 8080
```

## Docker

MariaDB debe estar corriendo en una red Docker accesible. El contenedor de la aplicación se conecta a esa red:

```bash
docker compose up --build
```

El `docker-compose.yml` usa la red externa `mistica-net` donde vive el contenedor MariaDB (`mariadb_docker`). Edita `docker-compose.yml` para cambiar la red o el host si tu infraestructura es diferente.

Las credenciales se pueden pasar mediante la variable `DB_PASSWORD` del entorno del host:

```bash
export DB_PASSWORD=tu_password
docker compose up --build
```

## Migración desde SQLite

Si tienes datos en `data/agenda.db`:

```bash
python scripts/migrate_sqlite_to_mariadb.py --dry-run      # simulación
python scripts/migrate_sqlite_to_mariadb.py                 # migración real
```

El script valida los conteos origen/destino y hace rollback ante errores.

## Configuración general

Tres niveles de prioridad:

1. `config.yaml` — valores base.
2. `data/settings.json` — overrides guardados desde la interfaz.
3. Variables de entorno — tienen prioridad sobre todo.

Variables de entorno de la aplicación:

| Variable | Descripción |
| --- | --- |
| `AGENDA_HOST` | Host de escucha (por defecto `127.0.0.1`) |
| `AGENDA_PORT` | Puerto HTTP (por defecto `8000`) |
| `AGENDA_BACKUP_DIR` | Directorio de backups |
| `AGENDA_SEED` | `1` = carga datos demo al arrancar |

## API

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/health` | Estado del servicio y de la BD |
| `GET` | `/api/meta` | Fecha de hoy, idiomas y zonas horarias |
| `GET` | `/api/settings` | Ajustes efectivos |
| `PUT` | `/api/settings` | Actualización parcial de ajustes |
| `POST` | `/api/settings/reset` | Elimina overrides y vuelve a `config.yaml` |
| `GET` | `/api/notes` | Lista de notas con filtros |
| `POST` | `/api/notes` | Crea una nota/tarea/evento |
| `GET` | `/api/notes/{id}` | Obtiene una nota |
| `PUT` | `/api/notes/{id}` | Actualiza una nota |
| `DELETE` | `/api/notes/{id}` | Elimina una nota |
| `POST` | `/api/notes/{id}/move` | Mueve nota en tablero |
| `GET` | `/api/notes/{id}/tags` | Etiquetas de la nota |
| `POST` | `/api/notes/{id}/tags/{tag_id}` | Añade etiqueta a la nota |
| `DELETE` | `/api/notes/{id}/tags/{tag_id}` | Quita etiqueta de la nota |
| `GET` | `/api/notes/{id}/subtasks` | Subtareas de la nota |
| `POST` | `/api/notes/{id}/subtasks` | Crea subtarea |
| `PUT` | `/api/notes/{id}/subtasks/{sid}` | Actualiza subtarea |
| `DELETE` | `/api/notes/{id}/subtasks/{sid}` | Elimina subtarea |
| `GET` | `/api/tags` | Lista todas las etiquetas |
| `POST` | `/api/tags` | Crea etiqueta |
| `DELETE` | `/api/tags/{id}` | Elimina etiqueta |
| `GET` | `/api/calendar?start=&end=` | Calendario con repeticiones expandidas |
| `GET` | `/api/reminders` | Notas de hoy y vencidas |
| `GET` | `/api/quick-notes` | Bandeja de notas rápidas |
| `POST` | `/api/quick-notes` | Crea nota rápida |
| `PUT` | `/api/quick-notes/{id}` | Edita nota rápida |
| `DELETE` | `/api/quick-notes/{id}` | Elimina nota rápida |
| `POST` | `/api/quick-notes/{id}/assign` | Convierte en nota del día |
| `GET` | `/api/export?format=json\|csv` | Exporta datos |
| `POST` | `/api/import?mode=merge\|replace` | Importa JSON |
| `POST` | `/api/demo/seed` | Carga datos de demostración |
| `GET` | `/api/backups` | Lista backups |
| `POST` | `/api/backups` | Crea backup manual |
| `GET` | `/api/backups/{name}` | Descarga backup |
| `GET` | `/api/board/columns` | Columnas del tablero |
| `PUT` | `/api/board/columns` | Actualiza columnas del tablero |

## Pruebas

```bash
pip install -r requirements-dev.txt

# Solo con SQLite (sin MariaDB):
pytest -m "not mariadb"

# Con MariaDB real (requiere credenciales):
DB_HOST=127.0.0.1 DB_PORT=3307 DB_USER=milo_app DB_PASSWORD=... pytest -m mariadb

# Todo:
pytest
```

## Estructura

```text
.
├── main.py                     # Arranque y flags de CLI
├── config.yaml                 # Configuración base
├── .env.example                # Plantilla de variables de entorno
├── app/
│   ├── server.py               # FastAPI, estáticos y manejo de errores
│   ├── config.py               # Configuración efectiva y overrides
│   ├── database.py             # MariaDB/SQLite, pool y sesiones
│   ├── models.py               # Note, Tag, Subtask, Routine, RoutineRecord
│   ├── schemas.py              # Contratos Pydantic
│   ├── services.py             # Repeticiones, reminders, export y demo
│   ├── backup.py               # Backups y scheduler
│   └── routes/                 # Routers de la API
├── scripts/
│   └── migrate_sqlite_to_mariadb.py
├── templates/index.html        # Estructura de la SPA
├── static/
│   ├── css/styles.css
│   ├── js/                     # app, api, i18n, markdown y utilidades
│   └── i18n/                   # es.json, en.json
├── data/                       # Ajustes y backups
└── tests/                      # Pruebas de integración
```

## Notas de implementación

- MariaDB usa `utf8mb4`, pool de conexiones con `pool_pre_ping` y reciclado cada 30 min.
- El esquema se crea automáticamente al arrancar (`create_all`); nunca se borra.
- Las tablas `tags`, `note_tags` y `subtasks` usan FK con `CASCADE DELETE`.
- Al arrancar con `DB_TYPE=sqlite` se aplican migraciones idempotentes para bases legacy.
- Las escrituras de `settings.json` son atómicas mediante archivo temporal y `replace`.
- No hay dependencias de frontend ni build: los módulos ES se sirven directamente.
