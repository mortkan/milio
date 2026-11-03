# Revisión técnica de Milo

## Diagnóstico del bloqueo «Cargando agenda…»

El bloqueo no estaba provocado inicialmente por SQLite. El navegador detenía la carga antes de ejecutar la inicialización de la aplicación porque `static/js/app.js` contenía errores de sintaxis y referencias a variables inexistentes. Al no ejecutarse `init()`, el frontend no llegaba a realizar ninguna llamada a `/api/settings`, `/api/meta` o `/api/calendar`, y la capa de carga permanecía visible indefinidamente.

La base `data/agenda.db` incluida en el proyecto supera `PRAGMA integrity_check` correctamente.

## Correcciones aplicadas

- Reparado el módulo principal del frontend y eliminadas declaraciones duplicadas.
- Reparada la vista diaria incompleta y referencias JavaScript inexistentes.
- Eliminados cuatro bloques HTML duplicados de una paleta de comandos sin terminar.
- Normalizada la carga de traducciones y completadas las claves utilizadas por la interfaz.
- Alineados los modelos SQLAlchemy con el esquema real de notas, notas rápidas y rutinas.
- Inicialización automática de la base de datos durante el arranque de FastAPI.
- Reutilización segura del engine SQLite y cierre de sesiones por petición.
- Activados WAL, `busy_timeout` y claves foráneas.
- Añadida migración automática para bases creadas por el modelo antiguo, sin borrar datos.
- Corregidos calendario, recordatorios, movimiento del tablero, rutinas y reseteo de ajustes.
- Reforzadas las pruebas de integración con base temporal.

## Validaciones realizadas

- Compilación Python completa sin errores.
- Validación de sintaxis de los módulos JavaScript.
- `pytest`: 6 pruebas superadas.
- Arranque desde una base vacía y creación automática de tablas.
- Migración de una base con el esquema antiguo conservando notas y rutinas.
- Prueba real de navegador: carga de mes, semana, día y tablero.
- Apertura de ajustes sin claves de traducción visibles.
- Creación de una nota desde la interfaz, visualización en calendario y borrado posterior.
- Todas las llamadas API de la prueba respondieron sin errores 4xx/5xx.
- `PRAGMA integrity_check`: `ok`.

## Arranque local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Abrir `http://127.0.0.1:8000`.

## Arranque con Docker

```bash
docker compose down
docker compose up -d --build
```

No es necesario borrar `data/agenda.db`. El arranque aplica las migraciones necesarias de forma automática. Es recomendable conservar una copia de la carpeta `data/` antes de sustituir una instalación existente.
