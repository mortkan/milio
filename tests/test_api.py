"""Pruebas de integración de la API con una base SQLite temporal."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import config


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Arranca la aplicación sobre una BD SQLite temporal vacía."""
    # Forzar SQLite para tests (no depende de MariaDB)
    monkeypatch.setenv("DB_TYPE", "sqlite")
    monkeypatch.setenv("AGENDA_DB", str(tmp_path / "agenda.db"))
    monkeypatch.setenv("AGENDA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("AGENDA_SEED", raising=False)
    monkeypatch.delenv("AGENDA_HOST", raising=False)
    monkeypatch.delenv("AGENDA_PORT", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "_settings", None)

    # Reiniciar el engine singleton para este test
    import app.database as db_module
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionLocal", None)

    from app.server import app as _app
    with TestClient(_app) as test_client:
        yield test_client


def test_startup_index_settings_meta_and_empty_database(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"

    settings = client.get("/api/settings")
    assert settings.status_code == 200
    assert settings.json()["server"]["database_path"]

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    languages = {item["code"]: item["name"] for item in meta.json()["languages"]}
    assert languages == {"en": "English", "es": "Español"}

    assert client.get("/api/notes").json() == []
    assert client.get("/api/quick-notes").json() == []


def test_note_crud_calendar_and_reminders(client):
    today = date.today()
    payload = {
        "title": "Prueba de integración",
        "content": "Contenido de la nota",
        "note_date": today.isoformat(),
        "time": "09:30",
        "category": "work",
        "priority": "high",
        "color": "#4f46e5",
        "completed": False,
        "recurrence": "none",
    }

    created = client.post("/api/notes", json=payload)
    assert created.status_code == 201
    note = created.json()
    note_id = note["id"]
    assert note["title"] == payload["title"]

    calendar = client.get(
        "/api/calendar",
        params={
            "start": (today - timedelta(days=1)).isoformat(),
            "end": (today + timedelta(days=1)).isoformat(),
        },
    )
    assert calendar.status_code == 200
    assert calendar.json()["days"][today.isoformat()][0]["id"] == note_id

    reminders = client.get("/api/reminders")
    assert reminders.status_code == 200
    assert any(item["id"] == note_id for item in reminders.json()["today"])

    updated = client.put(
        f"/api/notes/{note_id}",
        json={"completed": True, "title": "Prueba actualizada"},
    )
    assert updated.status_code == 200
    assert updated.json()["completed"] is True
    assert updated.json()["title"] == "Prueba actualizada"

    deleted = client.delete(f"/api/notes/{note_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/notes/{note_id}").status_code == 404


def test_quick_note_assignment_board_move_export_and_backup(client):
    today = date.today().isoformat()

    quick = client.post("/api/quick-notes", json={"content": "Llamar a soporte"})
    assert quick.status_code == 201
    quick_id = quick.json()["id"]

    assigned = client.post(
        f"/api/quick-notes/{quick_id}/assign",
        json={"note_date": today, "category": "work", "priority": "medium"},
    )
    assert assigned.status_code == 201
    note_id = assigned.json()["id"]
    assert client.get("/api/quick-notes").json() == []

    moved = client.post(
        f"/api/notes/{note_id}/move",
        json={"column": "en-curso", "position": 2},
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "en-curso"
    assert moved.json()["position"] == 2

    json_export = client.get("/api/export", params={"format": "json"})
    assert json_export.status_code == 200
    assert any(item["id"] == note_id for item in json_export.json()["notes"])

    csv_export = client.get("/api/export", params={"format": "csv"})
    assert csv_export.status_code == 200
    assert "Llamar a soporte" in csv_export.text

    backup = client.post("/api/backups")
    assert backup.status_code == 201
    assert backup.json()["name"].endswith(".db")
    assert client.get("/api/backups").json()


def test_settings_update_and_reset(client):
    updated = client.put(
        "/api/settings",
        json={"app_name": "Milo", "theme": "light"},
    )
    assert updated.status_code == 200
    assert updated.json()["app_name"] == "Milo"
    assert updated.json()["theme"] == "light"

    reset = client.post("/api/settings/reset")
    assert reset.status_code == 200
    assert reset.json()["app_name"] == "Agenda"


def test_validation_errors_are_serializable(client):
    response = client.post(
        "/api/notes",
        json={"title": "", "content": "", "note_date": date.today().isoformat()},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"] == "Datos inválidos"
    assert isinstance(payload["errors"], list)


def test_legacy_database_is_migrated_without_losing_data(tmp_path, monkeypatch):
    import sqlite3

    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE notes (
            id INTEGER NOT NULL PRIMARY KEY,
            title VARCHAR(100) NOT NULL,
            content TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            type VARCHAR(30),
            status VARCHAR(20) NOT NULL,
            position INTEGER NOT NULL,
            note_date DATE
        );
        INSERT INTO notes VALUES (
            1, 'Nota antigua', NULL, '2026-11-01 08:00:00',
            '2026-11-01 08:00:00', NULL, 'none', 0, NULL
        );
        CREATE TABLE quick_notes (
            id INTEGER NOT NULL PRIMARY KEY,
            content VARCHAR(200) NOT NULL,
            created_at DATETIME NOT NULL
        );
        CREATE TABLE routines (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            created_at DATETIME NOT NULL
        );
        CREATE TABLE routine_records (
            id INTEGER NOT NULL PRIMARY KEY,
            routine_id INTEGER NOT NULL,
            record_date DATE NOT NULL,
            completed BOOLEAN NOT NULL
        );
        INSERT INTO routines VALUES (
            1, 'Rutina antigua', 'Descripción', '2026-11-01 08:00:00'
        );
        INSERT INTO routine_records VALUES (1, 1, '2026-11-01', 1);
        """
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("DB_TYPE", "sqlite")
    monkeypatch.setenv("AGENDA_DB", str(database))
    monkeypatch.setenv("AGENDA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "_settings", None)

    import app.database as db_module
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionLocal", None)

    from app.database import get_db_session, init_db
    from app.models import Note, Routine, RoutineRecord
    from app.services import mark_routine_complete

    init_db()
    with get_db_session() as session:
        note = session.get(Note, 1)
        assert note is not None
        assert note.content == ""
        assert note.note_date.isoformat() == "2026-11-01"

        routine = session.get(Routine, 1)
        assert routine is not None
        assert routine.title == "Rutina antigua"

        old_record = session.get(RoutineRecord, 1)
        assert old_record is not None
        assert old_record.date.isoformat() == "2026-11-01"

        today_record = mark_routine_complete(1, session)
        assert today_record.completed is True

    connection = sqlite3.connect(database)
    routine_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(routines)")
    }
    record_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(routine_records)")
    }
    assert "name" not in routine_columns
    assert "record_date" not in record_columns
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()


def test_board_columns_and_default_mode(client):
    """board_columns y board_default_mode se guardan y devuelven."""
    settings = client.get("/api/settings").json()
    assert "board_columns" in settings
    assert "board_default_mode" in settings
    assert settings["board_default_mode"] == "status"

    new_columns = [
        {"id": "todo", "label": "Por hacer", "color": "#8b5cf6"},
        {"id": "done", "label": "Hecho", "color": "#10b981"},
    ]
    updated = client.put(
        "/api/settings",
        json={"board_columns": new_columns, "board_default_mode": "week"},
    )
    assert updated.status_code == 200
    assert updated.json()["board_default_mode"] == "week"
    assert len(updated.json()["board_columns"]) == 2
    assert updated.json()["board_columns"][0]["id"] == "todo"


def test_note_with_status_is_preserved(client):
    """El campo status de una nota se guarda y se recupera correctamente."""
    today = date.today().isoformat()
    note = client.post(
        "/api/notes",
        json={"title": "Nota con status", "note_date": today, "status": "en-curso"},
    )
    assert note.status_code == 201
    assert note.json()["status"] == "en-curso"

    retrieved = client.get(f"/api/notes/{note.json()['id']}").json()
    assert retrieved["status"] == "en-curso"

    moved = client.post(
        f"/api/notes/{note.json()['id']}/move",
        json={"column": "hecho"},
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "hecho"


def test_note_status_none_default(client):
    """Una nota sin status explícito tiene status 'none'."""
    today = date.today().isoformat()
    note = client.post(
        "/api/notes",
        json={"title": "Sin status", "note_date": today},
    )
    assert note.status_code == 201
    assert note.json()["status"] == "none"


def test_search_with_completed_filter(client):
    """Búsqueda filtrando por estado completado funciona sin 422."""
    today = date.today().isoformat()
    client.post("/api/notes", json={"title": "Pendiente", "note_date": today, "completed": False})
    client.post("/api/notes", json={"title": "Completada", "note_date": today, "completed": True})

    pending = client.get("/api/notes", params={"completed": "false"})
    assert pending.status_code == 200
    assert all(not n["completed"] for n in pending.json())

    done = client.get("/api/notes", params={"completed": "true"})
    assert done.status_code == 200
    assert all(n["completed"] for n in done.json())

    all_notes = client.get("/api/notes")
    assert all_notes.status_code == 200
    assert len(all_notes.json()) == 2


def test_routines_endpoints(client):
    """Los endpoints de rutinas devuelven 200 sin datos de ejemplo."""
    assert client.get("/api/routines/today").status_code == 200
    assert client.get("/api/routines/today-records").status_code == 200
    assert client.get("/api/templates").status_code == 200
    assert client.get("/api/checklist/morning_journal").status_code == 200

    streak = client.get("/api/routines/99/streak")
    assert streak.status_code == 404


def test_export_import_roundtrip(client):
    """Export JSON → Import merge → misma cantidad de notas."""
    today = date.today().isoformat()
    client.post("/api/notes", json={"title": "Nota export", "note_date": today})
    client.post("/api/quick-notes", json={"content": "Nota rápida export"})

    payload = client.get("/api/export", params={"format": "json"}).json()
    assert len(payload["notes"]) == 1
    assert len(payload["quick_notes"]) == 1

    import_result = client.post(
        "/api/import",
        json={"notes": payload["notes"], "quick_notes": payload["quick_notes"]},
        params={"mode": "merge"},
    )
    assert import_result.status_code == 200
    assert import_result.json()["notes_imported"] == 1

    all_notes = client.get("/api/notes").json()
    assert len(all_notes) == 2


def test_demo_seed_and_board_columns_api(client):
    """demo/seed crea datos; /api/board/columns devuelve columnas."""
    seed = client.post("/api/demo/seed")
    assert seed.status_code == 200
    assert seed.json()["skipped"] is False

    columns = client.get("/api/board/columns")
    assert columns.status_code == 200
    assert isinstance(columns.json(), list)
    assert len(columns.json()) > 0

    new_cols = [
        {"id": "a", "label": "A", "color": "#ffffff"},
        {"id": "b", "label": "B", "color": "#000000"},
    ]
    put_cols = client.put("/api/board/columns", json={"columns": new_cols})
    assert put_cols.status_code == 200
    assert len(put_cols.json()) == 2


def test_tags_and_subtasks(client):
    """Tags y subtareas se crean, listan y eliminan correctamente."""
    today = date.today().isoformat()

    # Crear nota tipo tarea
    note = client.post("/api/notes", json={
        "title": "Tarea con tags",
        "note_date": today,
        "item_type": "task",
        "estimated_minutes": 90,
        "progress_percent": 25,
    })
    assert note.status_code == 201
    note_id = note.json()["id"]
    assert note.json()["item_type"] == "task"
    assert note.json()["estimated_minutes"] == 90
    assert note.json()["progress_percent"] == 25

    # Crear etiqueta
    tag = client.post("/api/tags", json={"name": "urgente", "color": "#ef4444"})
    assert tag.status_code == 201
    tag_id = tag.json()["id"]

    # Listar etiquetas
    tags = client.get("/api/tags")
    assert tags.status_code == 200
    assert any(t["name"] == "urgente" for t in tags.json())

    # Añadir etiqueta a nota
    added = client.post(f"/api/notes/{note_id}/tags/{tag_id}")
    assert added.status_code == 201
    assert any(t["id"] == tag_id for t in added.json())

    # Ver etiquetas de la nota
    note_tags = client.get(f"/api/notes/{note_id}/tags")
    assert note_tags.status_code == 200
    assert len(note_tags.json()) == 1

    # Crear subtarea
    sub = client.post(f"/api/notes/{note_id}/subtasks", json={"title": "Primer paso"})
    assert sub.status_code == 201
    sub_id = sub.json()["id"]
    assert sub.json()["completed"] is False

    # Completar subtarea
    updated_sub = client.put(
        f"/api/notes/{note_id}/subtasks/{sub_id}",
        json={"completed": True},
    )
    assert updated_sub.status_code == 200
    assert updated_sub.json()["completed"] is True

    # Listar subtareas
    subs = client.get(f"/api/notes/{note_id}/subtasks")
    assert subs.status_code == 200
    assert len(subs.json()) == 1

    # Eliminar subtarea
    assert client.delete(f"/api/notes/{note_id}/subtasks/{sub_id}").status_code == 204
    assert client.get(f"/api/notes/{note_id}/subtasks").json() == []

    # Eliminar etiqueta de nota
    assert client.delete(f"/api/notes/{note_id}/tags/{tag_id}").status_code == 204
    assert client.get(f"/api/notes/{note_id}/tags").json() == []

    # Eliminar etiqueta global
    assert client.delete(f"/api/tags/{tag_id}").status_code == 204


def test_item_types_note_task_event(client):
    """Notas, tareas y eventos con sus campos específicos."""
    today = date.today().isoformat()

    note = client.post("/api/notes", json={"title": "Nota simple", "note_date": today, "item_type": "note"})
    assert note.status_code == 201
    assert note.json()["item_type"] == "note"

    task = client.post("/api/notes", json={
        "title": "Tarea estimada",
        "note_date": today,
        "item_type": "task",
        "estimated_minutes": 60,
        "actual_minutes": 30,
        "progress_percent": 50,
    })
    assert task.status_code == 201
    t = task.json()
    assert t["item_type"] == "task"
    assert t["estimated_minutes"] == 60
    assert t["actual_minutes"] == 30
    assert t["progress_percent"] == 50

    event = client.post("/api/notes", json={
        "title": "Evento reunión",
        "note_date": today,
        "time": "10:00",
        "item_type": "event",
        "duration_minutes": 45,
    })
    assert event.status_code == 201
    e = event.json()
    assert e["item_type"] == "event"
    assert e["duration_minutes"] == 45

    # Actualizar progress
    updated = client.put(task.json()["id"] and f"/api/notes/{task.json()['id']}", json={"progress_percent": 100, "actual_minutes": 65})
    updated = client.put(f"/api/notes/{task.json()['id']}", json={"progress_percent": 100, "actual_minutes": 65})
    assert updated.status_code == 200
    assert updated.json()["progress_percent"] == 100


def test_health_endpoint_reports_database_status(client):
    """GET /api/health devuelve status y database."""
    health = client.get("/api/health")
    assert health.status_code == 200
    data = health.json()
    assert "status" in data
    assert "database" in data
    assert data["status"] == "ok"
    assert data["database"] == "connected"


# ---------------------------------------------------------------------------
# Tests de integración con MariaDB real
# Requieren DB_TYPE=mariadb y credenciales válidas.
# Se saltan automáticamente si no están disponibles.
# ---------------------------------------------------------------------------


@pytest.fixture()
def mariadb_client(tmp_path, monkeypatch):
    """Cliente con MariaDB real. Se salta si no hay conexión disponible."""
    import os
    os.environ.setdefault("DB_TYPE", "mariadb")
    os.environ.setdefault("DB_HOST", "127.0.0.1")
    os.environ.setdefault("DB_PORT", "3307")
    os.environ.setdefault("DB_NAME", "milo_test")
    os.environ.setdefault("DB_USER", "milo_app")
    os.environ.setdefault("DB_PASSWORD", "MiloApp2026!")

    # Crear la BD de tests si no existe
    try:
        import pymysql
        conn = pymysql.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            user="root",
            password="root",
            connect_timeout=5,
        )
        with conn.cursor() as cur:
            cur.execute(
                "CREATE DATABASE IF NOT EXISTS milo_test "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(
                "GRANT ALL PRIVILEGES ON milo_test.* TO 'milo_app'@'%'"
            )
            cur.execute("FLUSH PRIVILEGES")
        conn.close()
    except Exception as exc:
        pytest.skip(f"MariaDB no disponible: {exc}")

    monkeypatch.setenv("DB_TYPE", "mariadb")
    monkeypatch.setenv("DB_HOST", os.environ["DB_HOST"])
    monkeypatch.setenv("DB_PORT", os.environ["DB_PORT"])
    monkeypatch.setenv("DB_NAME", "milo_test")
    monkeypatch.setenv("DB_USER", os.environ["DB_USER"])
    monkeypatch.setenv("DB_PASSWORD", os.environ["DB_PASSWORD"])
    monkeypatch.setenv("AGENDA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("AGENDA_SEED", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "_settings", None)

    import app.database as db_module
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionLocal", None)

    from app.server import app as _app

    # Limpiar tablas antes del test
    try:
        from app.database import get_engine, init_db
        init_db()
        from sqlalchemy import text
        with get_engine().begin() as conn_:
            for tbl in ("note_tags", "subtasks", "routine_records", "routines", "quick_notes", "notes", "tags"):
                try:
                    conn_.execute(text(f"DELETE FROM `{tbl}`"))
                except Exception:
                    pass
    except Exception as exc:
        pytest.skip(f"No se pudo inicializar MariaDB de tests: {exc}")

    with TestClient(_app) as test_client:
        yield test_client

    # Cleanup: resetear engine
    import app.database as db_mod
    if db_mod._engine:
        db_mod._engine.dispose()
    db_mod._engine = None
    db_mod._SessionLocal = None


@pytest.mark.mariadb
def test_mariadb_health(mariadb_client):
    """El healthcheck reporta conexión MariaDB OK."""
    r = mariadb_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["database"] == "connected"


@pytest.mark.mariadb
def test_mariadb_note_crud(mariadb_client):
    """CRUD completo de notas sobre MariaDB."""
    today = date.today().isoformat()

    created = mariadb_client.post("/api/notes", json={
        "title": "Nota MariaDB",
        "note_date": today,
        "item_type": "task",
        "estimated_minutes": 30,
        "progress_percent": 0,
    })
    assert created.status_code == 201
    nid = created.json()["id"]

    read = mariadb_client.get(f"/api/notes/{nid}")
    assert read.status_code == 200
    assert read.json()["title"] == "Nota MariaDB"
    assert read.json()["item_type"] == "task"

    updated = mariadb_client.put(f"/api/notes/{nid}", json={"progress_percent": 50, "actual_minutes": 15})
    assert updated.status_code == 200
    assert updated.json()["progress_percent"] == 50

    deleted = mariadb_client.delete(f"/api/notes/{nid}")
    assert deleted.status_code == 204
    assert mariadb_client.get(f"/api/notes/{nid}").status_code == 404


@pytest.mark.mariadb
def test_mariadb_tags_and_subtasks(mariadb_client):
    """Tags y subtareas persisten en MariaDB con transacciones."""
    today = date.today().isoformat()

    note = mariadb_client.post("/api/notes", json={"title": "Tarea con relaciones", "note_date": today})
    nid = note.json()["id"]

    tag = mariadb_client.post("/api/tags", json={"name": "test-tag", "color": "#0ea5e9"})
    assert tag.status_code == 201
    tid = tag.json()["id"]

    mariadb_client.post(f"/api/notes/{nid}/tags/{tid}")
    assert len(mariadb_client.get(f"/api/notes/{nid}/tags").json()) == 1

    sub = mariadb_client.post(f"/api/notes/{nid}/subtasks", json={"title": "Subtarea MariaDB"})
    assert sub.status_code == 201
    sid = sub.json()["id"]

    # Al borrar la nota deben cascadearse tags y subtareas
    assert mariadb_client.delete(f"/api/notes/{nid}").status_code == 204
    assert mariadb_client.get(f"/api/notes/{nid}/subtasks").status_code == 404


@pytest.mark.mariadb
def test_mariadb_foreign_key_constraint(mariadb_client):
    """Una subtarea no puede existir sin su nota (FK)."""
    import app.database as db_module
    from app.models import Subtask

    with pytest.raises(Exception):
        from app.database import get_db_session
        with get_db_session() as session:
            orphan = Subtask(note_id=999999, title="Huérfana", completed=False, position=0)
            session.add(orphan)
            session.commit()


@pytest.mark.mariadb
def test_mariadb_rollback_on_error(mariadb_client):
    """Un error en una transacción hace rollback completo."""
    from app.database import get_db_session
    from app.models import Note
    from app.services import utcnow

    before_count = int(mariadb_client.get("/api/notes").json().__len__())

    try:
        with get_db_session() as session:
            n = Note(title="Rollback test", note_date=date.today(), item_type="note",
                     recurrence="none", completed=False, progress_percent=0)
            session.add(n)
            session.flush()
            raise RuntimeError("Error forzado para rollback")
    except RuntimeError:
        pass

    after_count = int(mariadb_client.get("/api/notes").json().__len__())
    assert after_count == before_count


def test_routine_crud(client):
    """CRUD completo de rutinas."""
    # Listar (vacío)
    assert client.get("/api/routines").status_code == 200
    assert client.get("/api/routines").json() == []

    # Crear
    r = client.post("/api/routines", json={
        "title": "Rutina de prueba",
        "schedule": "daily",
        "checklist_template": "Paso 1\nPaso 2",
    })
    assert r.status_code == 201
    rid = r.json()["id"]
    assert r.json()["title"] == "Rutina de prueba"
    assert r.json()["schedule"] == "daily"

    # Leer
    got = client.get(f"/api/routines/{rid}")
    assert got.status_code == 200
    assert got.json()["id"] == rid

    # Actualizar
    upd = client.put(f"/api/routines/{rid}", json={"title": "Rutina modificada", "schedule": "weekly"})
    assert upd.status_code == 200
    assert upd.json()["title"] == "Rutina modificada"
    assert upd.json()["schedule"] == "weekly"

    # Completar hoy
    done = client.post(f"/api/routines/{rid}/complete")
    assert done.status_code == 200
    assert done.json()["completed"] is True

    # Descompletar
    undone = client.post(f"/api/routines/{rid}/uncomplete")
    assert undone.status_code == 200
    assert undone.json()["completed"] is False

    # Racha
    streak = client.get(f"/api/routines/{rid}/streak")
    assert streak.status_code == 200
    assert "streak" in streak.json()

    # Hoy (deberia aparecer)
    today_list = client.get("/api/routines/today")
    assert any(r2["id"] == rid for r2 in today_list.json())

    # Eliminar
    assert client.delete(f"/api/routines/{rid}").status_code == 204
    assert client.get(f"/api/routines/{rid}").status_code == 404
    assert client.get("/api/routines").json() == []


def test_routine_not_found(client):
    """Rutina inexistente devuelve 404."""
    assert client.get("/api/routines/999").status_code == 404
    assert client.put("/api/routines/999", json={"title": "X"}).status_code == 404
    assert client.delete("/api/routines/999").status_code == 404
    assert client.post("/api/routines/999/complete").status_code == 404


def test_backup_creates_file(client, tmp_path, monkeypatch):
    """El backup crea un archivo en el directorio configurado."""
    # Crear una nota para tener datos
    today = date.today().isoformat()
    client.post("/api/notes", json={"title": "Nota backup", "note_date": today})

    r = client.post("/api/backups")
    assert r.status_code == 201
    data = r.json()
    assert "name" in data
    assert data["size"] > 0

    backups = client.get("/api/backups").json()
    assert any(b["name"] == data["name"] for b in backups)


def test_search_with_item_type_and_recurring_filters(client):
    """Filtros item_type y recurring funcionan sin 422."""
    today = date.today().isoformat()
    client.post("/api/notes", json={"title": "Nota", "note_date": today, "item_type": "note"})
    client.post("/api/notes", json={"title": "Tarea", "note_date": today, "item_type": "task"})
    client.post("/api/notes", json={
        "title": "Recurrente", "note_date": today,
        "item_type": "event", "recurrence": "weekly",
    })

    tasks = client.get("/api/notes", params={"item_type": "task"})
    assert tasks.status_code == 200
    assert all(n["item_type"] == "task" for n in tasks.json())
    assert len(tasks.json()) == 1

    events = client.get("/api/notes", params={"item_type": "event"})
    assert events.status_code == 200
    assert len(events.json()) == 1

    recurring = client.get("/api/notes", params={"recurring": "true"})
    assert recurring.status_code == 200
    assert all(n["recurrence"] != "none" for n in recurring.json())

    one_time = client.get("/api/notes", params={"recurring": "false"})
    assert one_time.status_code == 200
    assert all(n["recurrence"] == "none" for n in one_time.json())


def test_import_atomic_transaction(client):
    """Si los ajustes importados son inválidos, los datos no se importan."""
    today = date.today().isoformat()
    before = len(client.get("/api/notes").json())

    r = client.post(
        "/api/import",
        json={
            "notes": [{"title": "Nota importada", "note_date": today}],
            "quick_notes": [],
            "settings": {"timezone": "INVALID_TZ_THAT_DOES_NOT_EXIST"},
        },
        params={"import_settings": "true", "mode": "merge"},
    )
    assert r.status_code == 422

    # Los datos NO se importaron porque los ajustes fallaron
    after = len(client.get("/api/notes").json())
    assert after == before


def test_backup_restore_sqlite(client, tmp_path, monkeypatch):
    """Crear backup y restaurarlo no produce errores (SQLite)."""
    today = date.today().isoformat()
    client.post("/api/notes", json={"title": "Nota para restaurar", "note_date": today})

    # Crear backup
    bk = client.post("/api/backups")
    assert bk.status_code == 201
    backup_name = bk.json()["name"]

    # Restaurar
    restore = client.post(f"/api/backups/{backup_name}/restore")
    assert restore.status_code == 200
    assert restore.json()["restored"] == backup_name

    # La nota sigue existiendo tras la restauración
    notes = client.get("/api/notes").json()
    assert any(n["title"] == "Nota para restaurar" for n in notes)


def test_import_export_routines(client):
    """Rutinas se exportan e importan correctamente."""
    # Crear rutinas
    r1 = client.post("/api/routines", json={"title": "Rutina A", "schedule": "daily"})
    r2 = client.post("/api/routines", json={"title": "Rutina B", "schedule": "weekly"})
    assert r1.status_code == 201
    assert r2.status_code == 201

    # Exportar
    payload = client.get("/api/export", params={"format": "json"}).json()
    assert "routines" in payload
    assert any(r["title"] == "Rutina A" for r in payload["routines"])
    assert any(r["title"] == "Rutina B" for r in payload["routines"])

    # Importar en modo merge
    import_result = client.post(
        "/api/import",
        json={"routines": payload["routines"], "notes": [], "quick_notes": []},
        params={"mode": "merge"},
    )
    assert import_result.status_code == 200
    assert import_result.json()["routines_imported"] == 2

    # Hay el doble de rutinas (merge no elimina)
    all_routines = client.get("/api/routines").json()
    assert len(all_routines) == 4


def test_task_progress_fields(client):
    """Los campos de progreso de tareas se crean y actualizan."""
    today = date.today().isoformat()

    note = client.post("/api/notes", json={
        "title": "Tarea con progreso",
        "note_date": today,
        "item_type": "task",
        "estimated_minutes": 120,
        "actual_minutes": 45,
        "progress_percent": 37,
    })
    assert note.status_code == 201
    n = note.json()
    assert n["item_type"] == "task"
    assert n["estimated_minutes"] == 120
    assert n["actual_minutes"] == 45
    assert n["progress_percent"] == 37

    # Actualizar progreso al 100%
    done = client.put(note.json()["id"] and f"/api/notes/{n['id']}", json={
        "progress_percent": 100,
        "actual_minutes": 110,
        "completed": True,
    })
    assert done.status_code == 200
    assert done.json()["progress_percent"] == 100
    assert done.json()["actual_minutes"] == 110
    assert done.json()["completed"] is True

    # Verificar que aparece en calendario con los campos
    cal = client.get("/api/calendar", params={"start": today, "end": today})
    assert cal.status_code == 200
    day_items = cal.json()["days"].get(today, [])
    task_items = [item for item in day_items if item["id"] == n["id"]]
    assert len(task_items) == 1
    assert task_items[0]["item_type"] == "task"


@pytest.mark.mariadb
def test_mariadb_backup_restore(mariadb_client):
    """Crear backup MariaDB (.sql.gz) y restaurarlo."""
    today = date.today().isoformat()

    # Crear nota
    n = mariadb_client.post("/api/notes", json={"title": "Nota backup MariaDB", "note_date": today})
    assert n.status_code == 201

    # Crear backup
    bk = mariadb_client.post("/api/backups")
    assert bk.status_code == 201
    name = bk.json()["name"]
    assert name.endswith(".sql.gz")

    # Listar y verificar
    backups = mariadb_client.get("/api/backups").json()
    assert any(b["name"] == name for b in backups)

    # Restaurar
    restore = mariadb_client.post(f"/api/backups/{name}/restore")
    assert restore.status_code == 200
    assert restore.json()["database"] == "mariadb"
    assert restore.json()["restored"] == name

    # Los datos siguen ahí
    notes_after = mariadb_client.get("/api/notes").json()
    assert any(nn["title"] == "Nota backup MariaDB" for nn in notes_after)
