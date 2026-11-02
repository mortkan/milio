# Agenda

Agenda personal web con calendario, notas, recordatorios, repeticiones y captura rápida. Backend FastAPI + SQLite y frontend vanilla sin paso de compilación.

![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57)
![JavaScript](https://img.shields.io/badge/JavaScript-ES%20Modules-F7DF1E)

## Funciones

- Vista de mes, semana y día con navegación y selector de fecha.
- Notas con título, contenido Markdown, hora, categoría, prioridad, color y estado completado.
- Repeticiones diarias, semanales, mensuales y anuales con fecha de fin opcional.
- Panel lateral con las notas del día seleccionado.
- Bandeja de notas rápidas: editar, asignar a una fecha o eliminar.
- Recordatorios de notas de hoy y vencidas.
- Búsqueda por texto con filtros de fecha, categoría, prioridad y estado.
- Ajustes aplicables en caliente: idioma, tema, tipografía, colores, calendario, campos visibles, etiquetas, atajos y backups.
- Exportación JSON/CSV e importación JSON en modo `merge` o `replace`.
- Copias de seguridad automáticas y manuales de SQLite, con retención configurable.
- Datos de demostración para probar la aplicación rápidamente.
- Interfaz responsive, navegación por teclado y etiquetas ARIA.

## Inicio rápido

Requiere Python 3.12 o superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Abre <http://127.0.0.1:8000>. La documentación interactiva de la API está en <http://127.0.0.1:8000/docs>.

Opciones de arranque:

```bash
python main.py --seed                 # carga datos de ejemplo si la base está vacía
python main.py --reload               # recarga automática en desarrollo
python main.py --host 0.0.0.0 --port 8080
```

La base de datos y los backups se crean automáticamente en `data/`.

## Docker

```bash
docker compose up --build
```

La aplicación queda en <http://localhost:8000>. El volumen `./data:/app/data` conserva la base de datos, los ajustes y los backups entre reinicios y reconstrucciones.

## Configuración

La configuración tiene tres niveles, de menor a mayor prioridad:

1. Valores por defecto de `config.yaml`.
2. Overrides guardados desde la interfaz en `data/settings.json`.
3. Variables de entorno de infraestructura: `AGENDA_HOST`, `AGENDA_PORT`, `AGENDA_DB`, `AGENDA_BACKUP_DIR`.

Los cambios hechos en Ajustes se aplican en caliente, excepto el host, el puerto y las rutas de base de datos/backups, que requieren reiniciar el proceso.

Variables de entorno disponibles:

| Variable | Ejemplo | Descripción |
| --- | --- | --- |
| `AGENDA_HOST` | `0.0.0.0` | Host de escucha |
| `AGENDA_PORT` | `8080` | Puerto HTTP |
| `AGENDA_DB` | `/app/data/agenda.db` | Ruta del archivo SQLite |
| `AGENDA_BACKUP_DIR` | `/app/data/backups` | Directorio de copias |
| `AGENDA_SEED` | `1` | Carga datos demo si la base está vacía |

## Atajos por defecto

| Acción | Atajo |
| --- | --- |
| Nueva nota | `A` |
| Ir a nota rápida | `N` |
| Ir a hoy | `T` |
| Buscar | `/` |
| Ajustes | `,` |

Los atajos se pueden cambiar en Ajustes → Atajos. No se disparan mientras se escribe en un campo o hay un diálogo abierto.

## Repeticiones

Las repeticiones se expanden en el servidor al consultar el calendario y los recordatorios. Una nota recurrente mantiene una única fila en la base de datos:

- Editar o eliminar una ocurrencia afecta a toda la serie.
- `recurrence_end` es inclusivo y opcional.
- Los recordatorios solo incluyen ocurrencias de hoy o anteriores, sin duplicar series.

## API

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/health` | Estado del servicio |
| `GET` | `/api/meta` | Fecha de hoy, idiomas y zonas horarias |
| `GET` | `/api/settings` | Ajustes efectivos |
| `PUT` | `/api/settings` | Actualización parcial de ajustes |
| `POST` | `/api/settings/reset` | Elimina overrides y vuelve a `config.yaml` |
| `GET` | `/api/notes` | Lista de notas con filtros |
| `POST` | `/api/notes` | Crea una nota |
| `GET` | `/api/notes/{id}` | Obtiene una nota |
| `PUT` | `/api/notes/{id}` | Actualiza una nota |
| `PATCH` | `/api/notes/{id}/toggle` | Alterna completado |
| `DELETE` | `/api/notes/{id}` | Elimina una nota |
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

Las respuestas de error usan el formato `{"detail": "..."}`; los errores de validación de FastAPI devuelven `422` con el detalle de los campos.

## Estructura

```text
.
├── main.py                 # Arranque y flags de CLI
├── config.yaml             # Configuración base
├── app/
│   ├── server.py           # FastAPI, estáticos y manejo de errores
│   ├── config.py           # Configuración efectiva y overrides
│   ├── database.py         # SQLite, WAL y sesiones
│   ├── models.py           # Note y QuickNote
│   ├── schemas.py          # Contratos Pydantic
│   ├── services.py         # Repeticiones, reminders, export y demo
│   ├── backup.py           # Backups y scheduler
│   └── routes/             # Routers de la API
├── templates/index.html    # Estructura de la SPA
├── static/
│   ├── css/styles.css
│   ├── js/                 # app, api, i18n, markdown y utilidades
│   └── i18n/               # es.json, en.json
├── data/                   # Base de datos, ajustes y backups
└── tests/                  # Pruebas de integración de la API
```

## Pruebas

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Las pruebas usan una base de datos temporal y no tocan los datos reales de `data/`.

## Notas de implementación

- SQLite se configura con WAL, `busy_timeout` y foreign keys activadas.
- Las escrituras de `settings.json` son atómicas mediante archivo temporal y `replace`.
- La importación valida el payload antes de modificar la base de datos; `replace` elimina las notas existentes.
- Los backups se guardan con nombre `agenda-YYYYMMDD-HHMMSS.db` y se limpian según `backups.keep`.
- El frontend escapa HTML antes de renderizar Markdown y solo permite enlaces `http(s)` o `mailto`.
- No hay dependencias de frontend ni build: los módulos se sirven directamente desde `/static/js/`.
