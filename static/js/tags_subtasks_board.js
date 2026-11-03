
// ---------------------------------------------------------------------------
// Tags en notas
// ---------------------------------------------------------------------------

let _noteTagsCache = [];

async function loadNoteTagsUI(noteId) {
  try {
    const tags = await api.get(`/api/notes/${noteId}/tags`);
    _noteTagsCache = tags;
    renderNoteTagsUI(tags);
  } catch (_) {
    renderNoteTagsUI([]);
  }
}

function renderNoteTagsUI(tags) {
  const container = $("note-tags-list");
  if (!container) return;
  if (!tags.length) {
    container.innerHTML = `<span class="hint">${escapeHtml(t("note.no_tags"))}</span>`;
    return;
  }
  container.innerHTML = tags.map((tag) => `
    <span class="note-tag-chip" style="--tag-color:${escapeHtml(tag.color || "#64748b")}" data-tag-id="${tag.id}">
      ${escapeHtml(tag.name)}
      <button type="button" class="note-tag-remove" data-action="remove-note-tag" data-tag-id="${tag.id}" aria-label="Eliminar">&times;</button>
    </span>
  `).join("");
}

async function addTagToCurrentNote(name) {
  const note = state.editingNote;
  if (!note) return;
  try {
    const allTags = await api.get("/api/tags");
    let tag = allTags.find((tg) => tg.name.toLowerCase() === name.toLowerCase());
    if (!tag) {
      tag = await api.post("/api/tags", { name, color: "#64748b" });
    }
    const updated = await api.post(`/api/notes/${note.id}/tags/${tag.id}`);
    _noteTagsCache = updated;
    renderNoteTagsUI(updated);
  } catch (error) {
    reportError(error);
  }
}

async function removeTagFromCurrentNote(tagId) {
  const note = state.editingNote;
  if (!note) return;
  try {
    await api.delete(`/api/notes/${note.id}/tags/${tagId}`);
    _noteTagsCache = _noteTagsCache.filter((tg) => tg.id !== tagId);
    renderNoteTagsUI(_noteTagsCache);
  } catch (error) {
    reportError(error);
  }
}

// ---------------------------------------------------------------------------
// Subtareas en notas
// ---------------------------------------------------------------------------

let _noteSubtasksCache = [];

async function loadNoteSubtasksUI(noteId) {
  try {
    const subs = await api.get(`/api/notes/${noteId}/subtasks`);
    _noteSubtasksCache = subs;
    renderNoteSubtasksUI(subs);
  } catch (_) {
    renderNoteSubtasksUI([]);
  }
}

function renderNoteSubtasksUI(subs) {
  const container = $("note-subtasks-list");
  if (!container) return;
  if (!subs.length) {
    container.innerHTML = `<span class="hint">${escapeHtml(t("note.no_subtasks"))}</span>`;
    return;
  }
  container.innerHTML = subs.map((sub) => `
    <div class="subtask-row${sub.completed ? " is-done" : ""}" data-sub-id="${sub.id}">
      <button type="button" class="subtask-check" data-action="toggle-subtask" data-sub-id="${sub.id}">${sub.completed ? "✓" : "○"}</button>
      <span class="subtask-title">${escapeHtml(sub.title)}</span>
      <button type="button" class="subtask-remove" data-action="remove-subtask" data-sub-id="${sub.id}" aria-label="Eliminar">&times;</button>
    </div>
  `).join("");
}

async function addSubtaskToCurrentNote() {
  const note = state.editingNote;
  if (!note) return;
  const title = window.prompt(t("note.subtask_add_prompt") || "Título de la subtarea:");
  if (!title || !title.trim()) return;
  try {
    const sub = await api.post(`/api/notes/${note.id}/subtasks`, {
      title: title.trim(),
      position: _noteSubtasksCache.length,
    });
    _noteSubtasksCache = [..._noteSubtasksCache, sub];
    renderNoteSubtasksUI(_noteSubtasksCache);
  } catch (error) {
    reportError(error);
  }
}

async function toggleSubtask(subId) {
  const note = state.editingNote;
  if (!note) return;
  const sub = _noteSubtasksCache.find((s) => s.id === subId);
  if (!sub) return;
  try {
    const updated = await api.put(`/api/notes/${note.id}/subtasks/${subId}`, {
      completed: !sub.completed,
    });
    _noteSubtasksCache = _noteSubtasksCache.map((s) => s.id === subId ? updated : s);
    renderNoteSubtasksUI(_noteSubtasksCache);
  } catch (error) {
    reportError(error);
  }
}

async function removeSubtask(subId) {
  const note = state.editingNote;
  if (!note) return;
  try {
    await api.delete(`/api/notes/${note.id}/subtasks/${subId}`);
    _noteSubtasksCache = _noteSubtasksCache.filter((s) => s.id !== subId);
    renderNoteSubtasksUI(_noteSubtasksCache);
  } catch (error) {
    reportError(error);
  }
}

// ---------------------------------------------------------------------------
// Editor de columnas del tablero en ajustes
// ---------------------------------------------------------------------------

function renderBoardColumnsEditor(columns) {
  const container = $("settings-board-columns");
  if (!container) return;
  container.innerHTML = "";
  columns.forEach((col) => addBoardColumnRow(col));
}

function addBoardColumnRow(col) {
  const container = $("settings-board-columns");
  if (!container) return;
  const row = document.createElement("div");
  row.className = "board-col-row";
  row.innerHTML = `
    <input type="text" class="board-col-id" value="${escapeHtml(col.id)}" placeholder="id" maxlength="50" />
    <input type="text" class="board-col-label" value="${escapeHtml(col.label)}" placeholder="Etiqueta" maxlength="50" />
    <input type="color" class="board-col-color" value="${escapeHtml(col.color || "#64748b")}" />
    <button type="button" class="btn btn-ghost btn-small" data-action="remove-board-col" aria-label="Eliminar">\u2715</button>
  `;
  container.append(row);
}

function collectBoardColumnsFromEditor() {
  const container = $("settings-board-columns");
  if (!container) return state.settings ? state.settings.board_columns : [];
  const rows = container.querySelectorAll(".board-col-row");
  const cols = [];
  rows.forEach((row) => {
    const id = row.querySelector(".board-col-id") ? row.querySelector(".board-col-id").value.trim() : "";
    const label = row.querySelector(".board-col-label") ? row.querySelector(".board-col-label").value.trim() : "";
    const color = row.querySelector(".board-col-color") ? row.querySelector(".board-col-color").value : "#64748b";
    if (id && label) cols.push({ id, label, color });
  });
  return cols.length ? cols : (state.settings ? state.settings.board_columns : []);
}
