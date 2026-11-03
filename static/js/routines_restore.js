
// ---------------------------------------------------------------------------
// Rutinas
// ---------------------------------------------------------------------------

let _routinesCache = [];
let _editingRoutine = null;

async function loadRoutines() {
  try {
    const routines = await api.get("/api/routines");
    const records = await api.get("/api/routines/today-records");
    _routinesCache = routines;
    renderRoutines(routines, records);
  } catch (_) {
    renderRoutines([], {});
  }
}

function renderRoutines(routines, records) {
  const container = document.getElementById("routines-list");
  if (!container) return;
  if (!routines.length) {
    container.innerHTML = `<p class="hint">${escapeHtml(t("routine.empty"))}</p>`;
    return;
  }
  container.innerHTML = routines.map((r) => {
    const rec = records[r.id];
    const done = rec && rec.completed;
    return `<div class="routine-row${done ? " is-done" : ""}" data-routine-id="${r.id}">
      <div class="routine-info">
        <span class="routine-icon">${r.icon || "🔄"}</span>
        <span class="routine-title">${escapeHtml(r.title)}</span>
        <span class="routine-schedule hint">${escapeHtml(t("routine." + r.schedule))}</span>
      </div>
      <div class="routine-actions">
        <button type="button" class="btn btn-ghost btn-small" onclick="toggleRoutineComplete(${r.id}, ${done})">${done ? escapeHtml(t("routine.uncomplete")) : escapeHtml(t("routine.complete"))}</button>
        <button type="button" class="btn btn-ghost btn-small" onclick="openRoutineDialog(${r.id})">${escapeHtml(t("common.edit") || "✎")}</button>
      </div>
    </div>`;
  }).join("");
}

async function toggleRoutineComplete(routineId, currentlyDone) {
  try {
    if (currentlyDone) {
      await api.post(`/api/routines/${routineId}/uncomplete`);
    } else {
      await api.post(`/api/routines/${routineId}/complete`);
      showToast(t("messages.routine_completed"), "success");
    }
    await loadRoutines();
  } catch (error) {
    reportError(error);
  }
}

function openRoutineDialog(routineId = null) {
  _editingRoutine = routineId ? _routinesCache.find((r) => r.id === routineId) : null;
  const editing = Boolean(_editingRoutine);

  const titleEl = document.getElementById("routine-dialog-title");
  if (titleEl) titleEl.textContent = t(editing ? "routine.edit" : "routine.new");

  document.getElementById("routine-id").value = editing ? String(_editingRoutine.id) : "";
  document.getElementById("routine-title").value = _editingRoutine?.title || "";
  document.getElementById("routine-schedule").value = _editingRoutine?.schedule || "daily";
  document.getElementById("routine-description").value = _editingRoutine?.description || "";
  document.getElementById("routine-checklist").value = _editingRoutine?.checklist_template || "";
  document.getElementById("routine-color").value =
    _editingRoutine?.color && /^#[0-9a-fA-F]{6}$/.test(_editingRoutine.color)
      ? _editingRoutine.color
      : "#8b5cf6";

  const deleteBtn = document.getElementById("routine-delete");
  if (deleteBtn) deleteBtn.hidden = !editing;

  const dialog = document.getElementById("routine-dialog");
  if (dialog && !dialog.open) dialog.showModal();
  setTimeout(() => document.getElementById("routine-title")?.focus(), 40);
}

async function submitRoutineForm(event) {
  event.preventDefault();
  const title = document.getElementById("routine-title")?.value.trim();
  if (!title) {
    showToast(t("error.validation"), "error");
    return;
  }
  const payload = {
    title,
    schedule: document.getElementById("routine-schedule")?.value || "daily",
    description: document.getElementById("routine-description")?.value.trim() || null,
    checklist_template: document.getElementById("routine-checklist")?.value.trim() || "",
    color: document.getElementById("routine-color")?.value || "#8b5cf6",
  };

  try {
    if (_editingRoutine) {
      await api.put(`/api/routines/${_editingRoutine.id}`, payload);
    } else {
      await api.post("/api/routines", payload);
    }
    document.getElementById("routine-dialog")?.close();
    showToast(t("messages.routine_saved"), "success");
    await loadRoutines();
  } catch (error) {
    reportError(error);
  }
}

async function deleteCurrentRoutine() {
  if (!_editingRoutine) return;
  if (!window.confirm(t("messages.confirm_delete_routine"))) return;
  try {
    await api.delete(`/api/routines/${_editingRoutine.id}`);
    document.getElementById("routine-dialog")?.close();
    showToast(t("messages.routine_deleted"), "success");
    await loadRoutines();
  } catch (error) {
    reportError(error);
  }
}

// ---------------------------------------------------------------------------
// Restauración de backups desde la UI
// ---------------------------------------------------------------------------

async function restoreBackupFromUI(name) {
  if (!window.confirm(t("backups.restore_confirm"))) return;
  try {
    await api.post(`/api/backups/${encodeURIComponent(name)}/restore`);
    showToast(t("backups.restore_ok"), "success");
  } catch (error) {
    reportError(error);
  }
}
