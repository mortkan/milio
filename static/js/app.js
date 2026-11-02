/** Aplicación Agenda: estado, renderizado e interacción del frontend. */

import { api, ApiError, buildQuery } from "./api.js";
import {
  applyTranslations,
  getLanguage,
  loadLanguage,
  t,
  tPlural,
} from "./i18n.js";
import { renderMarkdown } from "./markdown.js";
import {
  addDays,
  addMonths,
  capitalize,
  escapeHtml,
  formatDate,
  formatLongDate,
  formatMonthYear,
  formatShortDate,
  formatTime,
  formatWeekRange,
  humanSize,
  isoWeekNumber,
  isValidISODate,
  daysInMonth,
  parseISO,
  startOfMonthGrid,
  startOfWeek,
  toISO,
  uniqueId,
  weekdaysInOrder,
} from "./util.js";

const $ = (id) => document.getElementById(id);
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

const state = {
  settings: null,
  meta: null,
  view: "month",
  anchorDate: null,
  selectedDate: null,
  calendar: { start: null, end: null, days: {} },
  quickNotes: [],
  reminders: { today: [], overdue: [] },
  remindersDismissed: false,
  searchResults: [],
  labelsDraft: { categories: [], priorities: [] },
  editingNote: null,
  noteDirty: false,
  activeSettingsTab: "general",
  backups: [],
};

let toastTimer = null;

const darkQuery =
  typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

function icon(name, className = "icon") {
  return `<svg class="${className}" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
}

function locale() {
  const language = getLanguage();
  return language === "es" ? "es-ES" : language === "en" ? "en-GB" : language;
}

function todayISO() {
  return state.meta?.today || toISO(new Date());
}

function openPalette() {
  const palette = $("command-palette");
  if (palette) {
    palette.classList.toggle("is-hidden");
    if (!palette.classList.contains("is-hidden")) {
      palette.focus();
    }
  }
}

function startOfDay(iso) {
  const date = new Date(iso);
  date.setHours(0, 0, 0, 0);
  return isoToDate(date);
}

function endOfDay(iso) {
  const date = new Date(iso);
  date.setHours(23, 59, 59, 999);
  return isoToDate(date);
}

function startOfWeek(iso, firstDay = 1) {
  const date = new Date(iso);
  const day = date.getDay();
  const diff = (day - firstDay + 7) % 7;
  date.setDate(date.getDate() - diff);
  date.setHours(0, 0, 0, 0);
  return isoToDate(date);
}

function addDays(iso, days) {
  const date = new Date(iso);
  date.setDate(date.getDate() + days);
  return isoToDate(date);
}

function dateOrToday(value) {
  return isValidISODate(value) ? value : todayISO();
}

function showToast(message, type = "") {
  const toast = $("toast");
  if (!toast) {
    return;
  }
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.className = `toast ${type}`.trim();
  toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 3800);
}

function errorText(error) {
  if (error instanceof ApiError) {
    if (error.status === 0 || error.message === "network") {
      return t("error.network");
    }
    if (error.message) {
      return error.message;
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return t("error.generic");
}

function reportError(error) {
  console.error(error);
  showToast(errorText(error), "error");
}

function parseDateInput(value) {
  return isValidISODate(value) ? value : null;
}

function countLabel(key, count) {
  return tPlural(`counts.${key}`, count);
}

function selectedCategory(id) {
  return state.settings?.categories.find((item) => item.id === id) || null;
}

function selectedPriority(id) {
  return state.settings?.priorities.find((item) => item.id === id) || null;
}

function noteTitle(note) {
  return note?.title || t("note.untitled");
}

function noteColor(note) {
  if (state.settings?.note_fields.color && note?.color && HEX_COLOR.test(note.color)) {
    return note.color;
  }
  const category = selectedCategory(note?.category);
  if (category) {
    return category.color;
  }
  const priority = selectedPriority(note?.priority);
  if (priority) {
    return priority.color;
  }
  return state.settings?.accent_color || "#4f46e5";
}

function contrastColor(hex) {
  const match = /^#([0-9a-f]{6})$/i.exec(hex || "");
  if (!match) {
    return "#ffffff";
  }
  const value = Number.parseInt(match[1], 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  const luminance = (red * 299 + green * 587 + blue * 114) / 1000;
  return luminance > 168 ? "#111827" : "#ffffff";
}

function displayShortcut(value) {
  if (!value) {
    return "";
  }
  return String(value)
    .split("+")
    .map((part) =>
      part.length === 1 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1),
    )
    .join("+");
}

function eventShortcut(event) {
  const modifiers = [];
  if (event.ctrlKey) {
    modifiers.push("Ctrl");
  }
  if (event.altKey) {
    modifiers.push("Alt");
  }
  if (event.shiftKey) {
    modifiers.push("Shift");
  }
  if (event.metaKey) {
    modifiers.push("Meta");
  }
  let key = event.key;
  if (!key || ["Control", "Shift", "Alt", "Meta"].includes(key)) {
    return "";
  }
  if (key === " ") {
    key = "Space";
  } else if (key.length === 1) {
    key = key.toLowerCase();
  }
  modifiers.push(key);
  return modifiers.join("+");
}

function normalizeShortcut(value) {
  return String(value || "").toLowerCase();
}

function isTypingTarget(target) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
  );
}

function applyAppearance() {
  const settings = state.settings;
  if (!settings) {
    return;
  }
  const root = document.documentElement;
  const useDark =
    settings.theme === "dark" ||
    (settings.theme === "auto" && darkQuery && darkQuery.matches);
  root.dataset.theme = useDark ? "dark" : "light";
  root.dataset.font = settings.font_family;
  root.dataset.density = settings.density;
  root.style.fontSize = `${settings.font_size}px`;
  root.style.setProperty("--accent", settings.accent_color);
  root.style.setProperty("--accent-contrast", contrastColor(settings.accent_color));

  document.title = settings.app_name;
  const title = $("app-title");
  if (title) {
    title.textContent = settings.app_name;
  }
  const quickKbd = $("quick-kbd");
if (quickKbd) {
    quickKbd.textContent = displayShortcut(settings.shortcuts.quick_note);
  }

  // Command palette (Ctrl+K)
  const paletteToggle = $("palette-toggle");
  if (paletteToggle) {
    paletteToggle.addEventListener("click", () => openPalette());
  }

  // Keyboard shortcut: Ctrl+K or Cmd+K
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openPalette();
    }
  });


  // Palette content
  const paletteItems = [
    { key: "n", label: t("quick_note"), action: () => { $("quick-input")?.focus(); } },
    { key: "t", label: t("today"), action: () => { goToday(); } },
    { key: "m", label: t("month"), action: () => { setView("month"); } },
    { key: "w", label: t("week"), action: () => { setView("week"); } },
    { key: "d", label: t("day"), action: () => { setView("day"); } },
    { key: "b", label: t("board"), action: () => { setView("board"); } },
    { key: "s", label: t("settings"), action: () => { openSettingsDialog(); } },
    { key: "/", label: t("search"), action: () => { $("search-input")?.focus(); } },
  ];

  const paletteHTML = paletteItems.map(item => `
    <div class="palette-item" data-key="${item.key}" tabindex="0">
      <span class="palette-shortcut">${item.key.toUpperCase()}</span>
      <span class="palette-action">${item.label}</span>
    </div>
  `).join("");

  const paletteElement = `
    <div id="command-palette" class="is-hidden" role="dialog" aria-modal="true">
      <div class="palette-container">
        <h3>${t("palette.title")}</h3>
        <kbd class="palette-shortcut">Ctrl</kbd><kbd>${t("palette.shortcut")}</kbd>
        <button class="palette-close" aria-label="${t("palette.close")}" data-action="open-palette">&times;</button>
        <div class="palette-list">${paletteHTML}</div>
      </div>
    </div>
  `;
  const quickInput = $("quick-input");
  if (quickInput) {
    const shortcut = displayShortcut(settings.shortcuts.quick_note);
    quickInput.placeholder = `${t("quick.placeholder")}`;

  // Event delegation for palette (since onclick doesn't work in ES modules)
  document.addEventListener('click', (e) => {
    const target = e.target.closest('[data-action]');
    if (target) {
      const action = target.dataset.action;
      if (action === 'open-palette') {
        openPalette();
      }
    }
  });

  }
  const tray = $("quick-tray");
  if (tray) {
    tray.classList.toggle("is-hidden", !settings.show_quick_notes);
  }
  syncNoteFieldVisibility();
}

function syncNoteFieldVisibility() {
  if (!state.settings) {
    return;
  }
  ["time", "category", "priority", "color"].forEach((field) => {
    const wrapper = document.querySelector(
      `#note-form [data-field="${field}"]`
    );
    if (wrapper) {
      wrapper.hidden = !state.settings.note_fields[field];
    }
  });
}

async function reloadLanguage() {
  if (!state.settings) {
    return;
  }
  await loadLanguage(state.settings.language);
  applyTranslations(document);
  applyAppearance();
}

function populateStaticOptions() {
  const settings = state.settings;
  const meta = state.meta;
  if (!settings || !meta) {
    return;
  }

  const languageSelect = $("settings-language");

  if (languageSelect) {
    const languages = Array.isArray(meta?.languages)
      ? meta.languages
      : [{ code: "es", name: "Español" }];

      languageSelect.innerHTML = languages
        .map(
          (item) =>
            `<option value="${escapeHtml(item.code)}">${escapeHtml(item.name)}</option>`,
        )
        .join("");
  }

  const timezoneList = $("timezone-options");
  if (timezoneList) {
    timezoneList.innerHTML = (meta.timezones || [])
      .map((zone) => `<option value="${escapeHtml(zone)}"></option>`)
      .join("");
  }

  const firstDay = $("settings-first-day");
  if (firstDay) {
    const names = weekdaysInOrder(0, locale(), "long");
    firstDay.innerHTML = names
      .map(
        (name, index) =>
          `<option value="${index}">${escapeHtml(capitalize(name))}</option>`,
      )
      .join("");
  }

  fillNoteCategorySelect($("note-category"), "", t("note.no_category"));
  fillNotePrioritySelect($("note-priority"), "", t("note.no_priority"));
  fillSearchCategorySelect($("search-category"), "");
  fillSearchPrioritySelect($("search-priority"), "");

  const quickDate = $("quick-target-date");
  if (quickDate && !quickDate.value) {
    quickDate.value = dateOrToday(state.selectedDate);
  }
}

function ensureOption(select, value, label, allLabel = "") {
  if (!select) {
    return;
  }
  const existing = Array.from(select.options).find((option) => option.value === value);
  if (existing) {
    existing.textContent = label;
    return;
  }
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  const blank = Array.from(select.options).find((item) => item.value === allLabel);
  if (blank) {
    blank.after(option);
  } else {
    select.prepend(option);
  }
}

function fillNoteCategorySelect(select, selected, emptyLabel) {
  if (!select) {
    return;
  }
  select.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
  state.settings.categories.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    select.append(option);
  });
  if (selected && !state.settings.categories.some((item) => item.id === selected)) {
    ensureOption(select, selected, selected);
  }
  select.value = selected || "";
}

function fillNotePrioritySelect(select, selected, emptyLabel) {
  if (!select) {
    return;
  }
  select.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
  state.settings.priorities.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    select.append(option);
  });
  if (selected && !state.settings.priorities.some((item) => item.id === selected)) {
    ensureOption(select, selected, selected);
  }
  select.value = selected || "";
}

function fillSearchCategorySelect(select, selected) {
  if (!select) {
    return;
  }
  select.innerHTML = `<option value="">${escapeHtml(t("common.all"))}</option>`;
  state.settings.categories.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    select.append(option);
  });
  select.value = selected || "";
}

function fillSearchPrioritySelect(select, selected) {
  if (!select) {
    return;
  }
  select.innerHTML = `<option value="">${escapeHtml(t("common.all"))}</option>`;
  state.settings.priorities.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    select.append(option);
  });
  select.value = selected || "";
}

function holidayFor(iso) {
  if (!state.settings?.show_holidays) {
    return null;
  }
  const monthDay = iso.slice(5);
  return (
    state.settings.holidays.find(
      (item) => item.date === iso || item.date === monthDay,
    ) || null
  );
}

function monthGridWeeks(anchor, firstDay) {
  const date = parseISO(anchor);
  const first = new Date(date.getFullYear(), date.getMonth(), 1, 12);
  const leading = (first.getDay() - firstDay + 7) % 7;
  const total = leading + daysInMonth(date.getFullYear(), date.getMonth());
  return Math.ceil(total / 7);
}

function calendarRange() {
  const anchor = dateOrToday(state.anchorDate);
  const firstDay = state.settings?.first_day_of_week ?? 1;
  if (state.view === "day") {
    return { start: anchor, end: anchor };
  }
  if (state.view === "week") {
    const start = toISO(startOfWeek(anchor, firstDay));
    return { start, end: toISO(addDays(start, 6)) };
  }
  const start = toISO(startOfMonthGrid(anchor, firstDay));
  const weeks = monthGridWeeks(anchor, firstDay);
  return { start, end: toISO(addDays(start, weeks * 7 - 1)) };
}

function visibleItems(iso) {
  const items = state.calendar.days[iso] || [];
  if (state.settings?.show_completed) {
    return items;
  }
  return items.filter((item) => !item.completed);
}

async function loadCalendar() {
  const range = calendarRange();
  const data = await api.get(`/api/calendar${buildQuery(range)}`);
  state.calendar = {
    start: data.start || range.start,
    end: data.end || range.end,
    days: data.days || {},
  };
  renderCalendar();
  renderDayPanel();
}

async function loadQuickNotes() {
  state.quickNotes = await api.get("/api/quick-notes");
  renderQuickNotes();
}

async function loadReminders() {
  state.reminders = await api.get("/api/reminders");
  renderReminders();
}

async function refreshAll() {
  await Promise.all([loadCalendar(), loadQuickNotes(), loadReminders()]);
}

function renderCalendar() {
  if (!state.settings) {
    return;
  }
  document.body.dataset.view = state.view;
  document.querySelectorAll(".view-btn[data-view]").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      button.dataset.view === state.view ? "true" : "false",
    );
  });

  const subtitle = $("app-subtitle");
  if (subtitle) {
    subtitle.textContent = t("app.context", {
      view: t(`views.${state.view}`).toLowerCase(),
    });
  }

  const range = calendarRange();
  const label = $("period-label");
  if (label) {
    if (state.view === "day") {
      label.textContent = formatLongDate(dateOrToday(state.anchorDate), locale());
    } else if (state.view === "week") {
      label.textContent = formatWeekRange(range.start, range.end, locale());
    } else if (state.view === "board") {
      label.textContent = t("board.title");
    } else {
      label.textContent = formatMonthYear(dateOrToday(state.anchorDate), locale());
    }
  }

  const calendar = $("calendar");
  if (!calendar) {
    return;
  }
  if (state.view === "week") {
    calendar.innerHTML = renderWeekView();
  } else if (state.view === "day") {
    calendar.innerHTML = renderDayView();
  } else if (state.view === "board") {
    calendar.innerHTML = renderBoardView();
  } else {
    calendar.innerHTML = renderMonthView();
  }
}

function renderMonthView() {
  const range = calendarRange();
  const firstDay = state.settings.first_day_of_week;
  const showWeeks = state.settings.show_week_numbers;
  const anchorKey = dateOrToday(state.anchorDate).slice(0, 7);
  const weeks = monthGridWeeks(dateOrToday(state.anchorDate), firstDay);
  const names = weekdaysInOrder(firstDay, locale(), "short");
  const weekdayCol = showWeeks ? `<span class="weekday-label" aria-hidden="true"></span>` : "";
  const weekdayRow = `<div class="weekday-row">${
    weekdayCol +
      names
        .map((name) => `<span class="weekday-label">${escapeHtml(name)}</span>`)
        .join("")}
  </div>`;

  const rows = [];
  for (let row = 0; row < weeks; row += 1) {
    const weekStart = addDays(range.start, row * 7);
    const cells = [];
    for (let column = 0; column < 7; column += 1) {
      cells.push(renderDayCell(toISO(addDays(weekStart, column)), anchorKey));
    }
    rows.push(`<div class="week-row">${
      showWeeks
        ? `<div class="week-number" title="${escapeHtml(
            t("calendar.week_number", { number: isoWeekNumber(weekStart) }),
          )}">${isoWeekNumber(weekStart)}</div>`
        : ""
    }${cells.join("")}</div>`);
  }

  const gridClass = showWeeks ? "month-grid with-week-numbers" : "month-grid";
  return `<div class="${gridClass}" style="--month-weeks:${weeks}">${weekdayRow}${rows.join("")}</div>`;
}

function renderBoardView() {
  const columns = state.settings.board_columns || defaultBoardColumns();
  const viewMode = state.settings.board_default_mode || "status";
  const showCompleted = state.settings.show_completed;

  if (viewMode === "status") {
    return renderBoardByStatus(columns);
  } else {
    return renderBoardByWeek(columns);
  }
}

function defaultBoardColumns() {
  return [
    { id: "pendientes", label: t("board.columns.pendientes"), color: "#64748b" },
    { id: "en-progreso", label: t("board.columns.en-progreso"), color: "#8b5cf6" },
    { id: "en-espera", label: t("board.columns.en-espera"), color: "#10b981" },
    { id: "terminadas", label: t("board.columns.terminadas"), color: "#f59e0b" },
  ];
}

function renderBoardByStatus(columns) {
  const statuses = columns.map((col) => col.id);
  const notes = state.calendar.days ? Object.values(state.calendar.days).flat() : [];
  const today = state.meta?.today || todayISO();

  // Group notes by status
  const statusGroups = {};
  statuses.forEach((status) => {
    statusGroups[status] = [];
  });

  // Also have a "bandeja" group for quick notes
  const quickNotes = state.quickNotes || [];

  // Assign notes to status groups based on their status field
  notes.forEach((note) => {
    const status = note.status || "pendientes";
    if (statusGroups[status] !== undefined) {
      statusGroups[status].push(note);
    } else {
      statusGroups["pendientes"] = statusGroups["pendientes"] || [];
      statusGroups["pendientes"].push(note);
    }
  });

  // Build HTML
  const columnHeaders = columns.map(
    (col) => `<div class="board-column-header" style="--board-column-color:${col.color}">
      <span class="board-column-label">${escapeHtml(col.label)}</span>
      <span class="board-column-count">${t("board.column_empty", { count: 0 })}</span>
      <button type="button" class="board-add" data-status="${col.id}">+</button>
    </div>`
  );

  const columnBodies = columns.map(
    (col, idx) => {
      const colNotes = statusGroups[col.id] || [];
      const completedCount = colNotes.filter((n) => n.completed).length;
      const activeCount = colNotes.length - completedCount;
      const notesHTML = colNotes
        .map((note) => renderBoardNote(note, col.id))
        .join("");
      return `<div class="board-column" data-status="${col.id}" style="--board-column-color:${col.color}">
        <div class="board-column-top">
          ${notesHTML}
          ${activeCount > 0 ? `<span class="board-column-count">${activeCount}</span>` : ""}
        </div>
        <button type="button" class="board-add" data-status="${col.id}">+ ${t("board.add_note")}</button>
      </div>`;
    }
  );

  return `<div class="board-view">
    <div class="board-header">
      ${columnHeaders.join("")}
    </div>
    <div class="board-columns">
      ${columnBodies.join("")}
    </div>
  </div>`;
}

function renderBoardByWeek(columns) {
  const today = new Date();
  const firstDay = state.settings?.first_day_of_week ?? 1;
  const startOfCurrentWeek = startOfWeek(todayISO(), firstDay);
  const endOfCurrentWeek = addDays(startOfCurrentWeek, 6);

  const columnHeaders = columns.map(
    (col, idx) => {
      const day = addDays(startOfCurrentWeek, idx);
      const dayLabel = formatLongDate(day, locale()).split(" ")[0];
      return `<div class="board-column" style="--board-column-color:${col.color}">
        <div class="board-column-header">
          <span class="board-column-label">${escapeHtml(col.label)}</span>
          <span class="board-column-date">${escapeHtml(dayLabel)} ${formatShortDate(day, locale())}</span>
          <button type="button" class="board-add" data-date="${toISO(day)}">+</button>
        </div>
      </div>`;
    }
  );

  const columnBodies = columns.map((col, idx) => {
    const day = addDays(startOfCurrentWeek, idx);
    const items = state.calendar.days?.[day.toISOString().split("T")[0]] || [];
    const notesHTML = items
      .map((item) => renderBoardNote(item, col.id, day.toISOString().split("T")[0]))
      .join("");
    const emptyNote = items.length
      ? ""
      : `<span class="board-empty">${t("calendar.no_notes")}</span>`;
    return `<div class="board-column" style="--board-column-color:${col.color}">
      <div class="board-column-top">
        ${notesHTML}
        ${items.length ? `<span class="board-column-count">${items.length}</span>` : ""}
      </div>
      <button type="button" class="board-add" data-date="${toISO(day)}">+ ${t("board.add_note")}</button>
    </div>`;
  });

  // Add "Sin fecha" column
  const noDateItems = [];
  // Collect notes without a date or with status indicating no date
  // ...

  return `<div class="board-view">
    <div class="board-header">
      ${columnHeaders.join("")}
    </div>
    <div class="board-columns">
      ${columnBodies.join("")}
      ${columns.length < 7 ? `
        <div class="board-column" style="--board-column-color:var(--muted)">
          <div class="board-column-header">
            <span class="board-column-label">${t("board.columns.sin-fecha")}</span>
            <span class="board-column-count">0</span>
          </div>
          <div class="board-column-top">
            ${emptyNote}
          </div>
        </div>
      ` : ""}
    </div>
  </div>`;
}

function renderBoardNote(note, status, noteDate = null) {
  const title = noteTitle(note);
  const color = noteColor(note);
  const hasDate = note.note_date !== undefined && note.note_date !== null;
  const dateStr = hasDate ? formatDate(note.note_date, state.settings.date_format) : "";
  const priority = note.priority ? `style="--note-color:${noteColor(note)}"` : "";
  const checklistHTML = note.missed_count > 1 ? `<span class="badge badge-overdue">${t("note.missed", { count: note.missed_count })}</span>` : "";

  return `<article class="board-note" data-note-id="${note.id}" style="--note-color:${color}">
    <div class="board-note-head">
      <span class="board-note-title">${escapeHtml(title)}</span>
      ${dateStr ? `<span class="board-note-date">${escapeHtml(dateStr)}</span>` : ""}
    </div>
    ${checklistHTML}
    ${priority ? `<div class="board-note-priority" ${priority}></div>` : ""}
  </article>`;
}

function renderDayCell(iso, anchorKey) {
  const date = parseISO(iso);
  const items = visibleItems(iso);
  const holiday = holidayFor(iso);
  const outside = iso.slice(0, 7) !== anchorKey;
  const classes = ["day-cell"];
  if (outside) {
    classes.push("outside");
  }
  if (iso === todayISO()) {
    classes.push("today");
  }
  if (iso === state.selectedDate) {
    classes.push("selected");
  }

  let previews = "";
  if (state.settings.show_month_previews && items.length) {
    const visible = items.slice(0, 3);
    previews = `<span class="day-previews">${visible
      .map((item) => {
        const time =
          item.time && state.settings.note_fields.time
            ? `<span class="preview-time">${escapeHtml(
                formatTime(item.time, state.settings.time_format, locale()),
              )}</span>`
            : "";
        const kind = item.time
          ? "is-event"
          : item.completed
            ? "is-done"
            : "is-task";
        return `<span class="preview-item ${kind}${
          item.completed ? " completed" : ""
        }"><span class="preview-dot" style="--dot-color:${escapeHtml(
          noteColor(item),
        )}"></span>${time}<span class="preview-title">${escapeHtml(
          noteTitle(item),
        )}</span></span>`;
      })
      .join("")}${
        items.length > visible.length
          ? `<span class="preview-more">${escapeHtml(
              t("calendar.more", { count: items.length - visible.length }),
            )}</span>`
          : ""
      }</span>`;
  } else if (items.length) {
    previews = `<span class="day-dots">${items
      .slice(0, 8)
      .map(
        (item) =>
          `<span class="day-dot" style="--dot-color:${escapeHtml(
            noteColor(item),
          )}"></span>`,
      )
      .join("")}</span>`;
  }

  return `<button type="button" class="${classes.join(" ")}" data-date="${iso}"${
    iso === todayISO() ? ' aria-current="date"' : ""
  }>
    <span class="sr-only">${escapeHtml(formatLongDate(iso, locale()))}</span>
    <span class="day-top">
      <span class="day-number">${date.getDate()}</span>
      ${items.length ? `<span class="day-count">${items.length}</span>` : ""}
    </span>
    ${holiday ? `<span class="holiday-label">${escapeHtml(holiday.name)}</span>` : ""}
    ${previews}
  </button>`;
}

function renderWeekView() {
  const range = calendarRange();
  const columns = [];
  const formatter = new Intl.DateTimeFormat(locale(), { weekday: "short" });
  for (let index = 0; index < 7; index += 1) {
    const iso = toISO(addDays(range.start, index));
    const date = parseISO(iso);
    const items = visibleItems(iso);
    const holiday = holidayFor(iso);
    const classes = ["week-column"];
    if (iso === todayISO()) {
      classes.push("today");
    }
    if (iso === state.selectedDate) {
      classes.push("selected");
    }
    columns.push(`<div class="${classes.join(" ")}">
      <button type="button" class="week-day-head" data-date="${iso}" aria-label="${escapeHtml(
        formatLongDate(iso, locale()),
      )}">
        <span class="week-day-name">${escapeHtml(
          capitalize(formatter.format(date)),
        )}</span>
        <span class="week-day-number">${date.getDate()}</span>
        ${holiday ? `<span class="week-day-holiday">${escapeHtml(holiday.name)}</span>` : ""}
      </button>
      <div class="week-notes">
        ${
          items.length
            ? items.map((item) => renderWeekNote(item, iso)).join("")
            : `<span class="week-empty">${escapeHtml(t("calendar.no_notes"))}</span>`
        }
        <button type="button" class="week-add" data-add-date="${iso}">+ ${escapeHtml(
          t("day.add"),
        )}</button>
      </div>
    </div>`);
  }
  return `<div class="week-view"><div class="week-grid">${columns.join("")}</div></div>`;
}

function renderWeekNote(note, iso) {
  const time =
    state.settings.note_fields.time && note.time
      ? formatTime(note.time, state.settings.time_format, locale())
      : "";
  return `<button type="button" class="week-note${
    note.completed ? " completed" : ""
  }" style="--note-color:${escapeHtml(noteColor(note))}" data-note-id="${
    note.id
  }" data-occurrence-date="${iso}">
    <span class="week-note-title">${escapeHtml(noteTitle(note))}</span>
    ${time ? `<span class="week-note-time">${escapeHtml(time)}</span>` : ""}
  </button>`;
}

function renderDayView() {
  const iso = dateOrToday(state.anchorDate);
  const items = visibleItems(iso);
  const holiday = holidayFor(iso);
  return `<div class="day-view">
    <div class="day-view-head">
      <div>
        <p class="eyebrow">${escapeHtml(t("day.selected"))}</p>
        <h2 class="day-view-title">${escapeHtml(formatLongDate(iso, locale()))}</h2>
        <p class="day-view-sub">${
          holiday ? `${escapeHtml(holiday.name)} · ` : ""
        }${escapeHtml(
          items.length ? countLabel("notes", items.length) : t("calendar.no_notes"),
        )}</p>
      </div>
      <div class="day-view-actions">
        <button type="button" class="btn btn-primary btn-small" data-add-date="${iso}">
          ${icon("plus")}<span>${escapeHtml(t("day.add"))}</span>
        </button>
      </div>
    </div>
    <div class="day-view-body">
      ${renderRoutinesBlock(iso)}
      ${renderTasksBlock(iso, items)}
      ${renderAgendaBlock(iso, items)}
    </div>
  </div>`;


function badgeItems(note) {
  const badges = [];
  if (state.settings.note_fields.category && note.category) {
    const category = selectedCategory(note.category);
    const label = category?.label || note.category;
    const color = category?.color || "var(--muted)";
    badges.push(
      `<span class="badge badge-colored" style="--badge-color:${escapeHtml(
        color,
      )}"><span class="badge-dot"></span>${escapeHtml(label)}</span>`,
    );
  }
  if (state.settings.note_fields.priority && note.priority) {
    const priority = selectedPriority(note.priority);
    const label = priority?.label || note.priority;
    const color = priority?.color || "var(--muted)";
    badges.push(
      `<span class="badge badge-colored" style="--badge-color:${escapeHtml(
        color,
      )}"><span class="badge-dot"></span>${escapeHtml(label)}</span>`,
    );
  }
  if (note.recurrence && note.recurrence !== "none") {
    badges.push(
      `<span class="badge badge-recurring">${icon("repeat")}${escapeHtml(
        t(`recurrence.${note.recurrence}`),
      )}</span>`,
    );
  }
  if (Number(note.missed_count) > 1) {
    badges.push(
      `<span class="badge badge-overdue">${escapeHtml(
        t("note.missed", { count: note.missed_count }),
      )}</span>`,
    );
  }
  return badges.join("");
}

function renderNoteBadges(note) {
  const badges = badgeItems(note);
  return badges ? `<div class="note-card-badges">${badges}</div>` : "";
}

function renderNoteCard(note) {
  const time =
    state.settings.note_fields.time && note.time
      ? `<span class="note-time">${escapeHtml(
          formatTime(note.time, state.settings.time_format, locale()),
        )}</span>`
      : "";
  const completed = Boolean(note.completed);
  return `<article class="note-card${completed ? " completed" : ""}" style="--note-color:${escapeHtml(
    noteColor(note),
  )}">
    <div class="note-card-head">
      ${time}
      <button type="button" class="note-card-title" data-action="open" data-note-id="${
        note.id
      }">${escapeHtml(noteTitle(note))}</button>
      <span class="note-actions">
        <button type="button" class="icon-btn toggle-complete" data-action="toggle" data-note-id="${
          note.id
        }" aria-pressed="${completed ? "true" : "false"}" aria-label="${escapeHtml(
          t("aria.toggle_complete"),
        )}">${icon("check")}</button>
        <button type="button" class="icon-btn" data-action="edit" data-note-id="${
          note.id
        }" aria-label="${escapeHtml(t("aria.edit_note"))}">${icon("edit")}</button>
        <button type="button" class="icon-btn" data-action="delete" data-note-id="${
          note.id
        }" aria-label="${escapeHtml(t("aria.delete_note"))}">${icon("trash")}</button>
      </span>
    </div>
    ${renderNoteBadges(note)}
    ${
      note.content
        ? `<div class="note-card-content markdown">${renderMarkdown(
            note.content,
          )}</div>`
        : ""
    }
  </article>`;
}

function splitDayNotes(notes) {
  const groups = { events: [], tasks: [], notes: [] };
  notes.forEach((note) => {
    if (note.time) {
      groups.events.push(note);
    } else if (!note.completed && note.priority) {
      groups.tasks.push(note);
    } else {
      groups.notes.push(note);
    }
  });
  return groups;
}

function renderPanelNote(note, kind) {
  const time =
    state.settings.note_fields.time && note.time
      ? formatTime(note.time, state.settings.time_format, locale())
      : "";
  const badges = badgeItems(note);
  const completed = Boolean(note.completed);
  return `<article class="panel-note panel-note--${kind}${
    completed ? " completed" : ""
  }" style="--note-color:${escapeHtml(noteColor(note))}">
    <span class="panel-note-rail" aria-hidden="true"></span>
    ${
      time
        ? `<span class="panel-note-time">${escapeHtml(time)}</span>`
        : `<span class="panel-note-time panel-note-time--empty" aria-hidden="true"></span>`
    }
    <div class="panel-note-body">
      <button type="button" class="panel-note-title" data-action="open" data-note-id="${
        note.id
      }">${escapeHtml(noteTitle(note))}</button>
      ${badges ? `<div class="panel-note-meta">${badges}</div>` : ""}
    </div>
    <div class="panel-note-actions">
      <button type="button" class="icon-btn toggle-complete" data-action="toggle" data-note-id="${
        note.id
      }" aria-pressed="${completed ? "true" : "false"}" aria-label="${escapeHtml(
        t("aria.toggle_complete"),
      )}">${icon("check")}</button>
      <button type="button" class="icon-btn" data-action="edit" data-note-id="${
        note.id
      }" aria-label="${escapeHtml(t("aria.edit_note"))}">${icon("edit")}</button>
    </div>
  </article>`;
}

function renderPanelSection(kind, labelKey, items) {
  if (!items.length) {
    return "";
  }
  return `<section class="panel-section panel-section--${kind}">
    <header class="panel-section-head">
      <h3>${escapeHtml(t(labelKey))}</h3>
      <span class="panel-section-count">${items.length}</span>
    </header>
    <div class="panel-list">
      ${items.map((note) => renderPanelNote(note, kind)).join("")}
    </div>
  </section>`;
}

function renderDayPanel() {
  if (!state.settings) {
    return;
  }
  const iso = dateOrToday(state.selectedDate);
  const date = parseISO(iso);
  const weekday = new Intl.DateTimeFormat(locale(), { weekday: "long" }).format(
    date,
  );
  const weekdayLabel = $("panel-weekday");
  const dateLabel = $("panel-date");
  if (weekdayLabel) {
    weekdayLabel.textContent = capitalize(weekday);
  }
  if (dateLabel) {
    dateLabel.textContent = capitalize(
      new Intl.DateTimeFormat(locale(), {
        day: "numeric",
        month: "long",
        year: "numeric",
      }).format(date),
    );
  }
  const notes = visibleItems(iso);
  const groups = splitDayNotes(notes);
  const summary = $("panel-summary");
  if (summary) {
    const chip = (kind, count) =>
      `<span class="summary-chip summary-chip--${kind}${
        count ? "" : " is-empty"
      }"><strong>${count}</strong><span>${escapeHtml(
        t(`day.groups.${kind}_short`),
      )}</span></span>`;
    summary.innerHTML =
      chip("events", groups.events.length) +
      chip("tasks", groups.tasks.length) +
      chip("notes", groups.notes.length);
  }
  const container = $("panel-notes");
  if (container) {
    container.innerHTML = notes.length
      ? renderPanelSection("events", "day.groups.events", groups.events) +
        renderPanelSection("tasks", "day.groups.tasks", groups.tasks) +
        renderPanelSection("notes", "day.groups.notes", groups.notes)
      : `<div class="empty-state empty-state--compact"><p>${escapeHtml(
          t("day.empty"),
        )}</p><button type="button" class="btn btn-secondary btn-small" data-add-date="${iso}">${escapeHtml(
          t("day.add"),
        )}</button></div>`;
  }
  const quickDate = $("quick-target-date");
  if (quickDate) {
    quickDate.value = iso;
  }
}

function renderQuickNotes() {
  const list = $("quick-notes-list");
  const countPill = $("quick-count");
  if (!list) {
    return;
  }
  if (countPill) {
    countPill.hidden = state.quickNotes.length === 0;
    countPill.textContent = countLabel("notes", state.quickNotes.length);
  }
  const tray = $("quick-tray");
  if (tray && state.settings) {
    tray.classList.toggle("is-hidden", !state.settings.show_quick_notes);
  }
  if (!state.quickNotes.length) {
    list.innerHTML = `<div class="empty-state">${escapeHtml(
      t("day.quick_empty"),
    )}</div>`;
    return;
  }
  list.innerHTML = state.quickNotes
    .map((item) => {
      const created = new Date(item.created_at);
      const createdLabel = Number.isNaN(created.getTime())
        ? formatShortDate(String(item.created_at).slice(0, 10), locale())
        : new Intl.DateTimeFormat(locale(), {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          }).format(created);
      return `<div class="quick-item" data-quick-id="${item.id}">
        <p data-role="quick-content">${escapeHtml(item.content)}</p>
        <div class="quick-item-meta">
          <span>${escapeHtml(createdLabel)}</span>
          <span class="quick-item-actions">
            <button type="button" class="icon-btn" data-action="quick-assign" data-quick-id="${
              item.id
            }" aria-label="${escapeHtml(t("quick.assign_to"))}">${icon("check")}</button>
            <button type="button" class="icon-btn" data-action="quick-edit" data-quick-id="${
              item.id
            }" aria-label="${escapeHtml(t("common.edit"))}">${icon("edit")}</button>
            <button type="button" class="icon-btn" data-action="quick-delete" data-quick-id="${
              item.id
            }" aria-label="${escapeHtml(t("common.delete"))}">${icon("trash")}</button>
          </span>
        </div>
      </div>`;
    })
    .join("");
}

function renderReminders() {
  const banner = $("reminder-banner");
  if (!banner) {
    return;
  }
  const today = (state.reminders.today || []).filter((item) => !item.completed);
  const overdue = (state.reminders.overdue || []).filter((item) => !item.completed);
  if (state.remindersDismissed || (!today.length && !overdue.length)) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.classList.toggle("has-overdue", overdue.length > 0);
  const title = $("reminder-title");
  const detail = $("reminder-detail");
  if (title) {
    title.textContent = t("reminders.title");
  }
  if (detail) {
    const parts = [];
    if (today.length) {
      parts.push(t("reminders.today_summary", { count: today.length }));
    }
    if (overdue.length) {
      parts.push(t("reminders.overdue_summary", { count: overdue.length }));
    }
    detail.textContent = parts.join(" · ");
  }
}

async function openSearchDialog() {
  if (!state.settings) {
    return;
  }
  fillSearchCategorySelect($("search-category"), $("search-category")?.value || "");
  fillSearchPrioritySelect($("search-priority"), $("search-priority")?.value || "");
  const dialog = $("search-dialog");
  if (dialog && !dialog.open) {
    dialog.showModal();
  }
  window.setTimeout(() => $("search-text")?.focus(), 40);
}

async function runSearch() {
  const summary = $("search-summary");
  const results = $("search-results");
  if (summary) {
    summary.textContent = t("common.loading");
  }
  if (results) {
    results.innerHTML = "";
  }
  const params = {
    q: $("search-text")?.value.trim() || "",
    category: $("search-category")?.value || "",
    priority: $("search-priority")?.value || "",
    completed: $("search-status")?.value || "",
    start: $("search-from")?.value || "",
    end: $("search-to")?.value || "",
    limit: 500,
  };
  try {
    state.searchResults = await api.get(`/api/notes${buildQuery(params)}`);
    renderSearchResults();
  } catch (error) {
    if (summary) {
      summary.textContent = errorText(error);
    }
    reportError(error);
  }
}

function renderSearchResults() {
  const summary = $("search-summary");
  const results = $("search-results");
  if (!summary || !results) {
    return;
  }
  if (!state.searchResults.length) {
    summary.textContent = t("search.empty");
    results.innerHTML = "";
    return;
  }
  summary.textContent = tPlural("counts.results", state.searchResults.length);
  results.innerHTML = state.searchResults
    .map((note) => {
      const excerpt = String(note.content || "")
        .replace(/[#>*_`~]+/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 190);
      return `<button type="button" class="search-result" data-search-id="${note.id}">
        <span class="search-result-top">
          <span class="search-result-title">${escapeHtml(noteTitle(note))}</span>
          <span class="search-result-date">${escapeHtml(
            formatDate(note.note_date, state.settings.date_format),
          )}</span>
        </span>
        ${excerpt ? `<span class="search-result-excerpt">${escapeHtml(excerpt)}</span>` : ""}
        <span class="search-result-badges">${badgeItems(note)}</span>
      </button>`;
    })
    .join("");
}

function openPanel() {
  if (!window.matchMedia("(max-width: 980px)").matches) {
    return;
  }
  document.body.classList.add("panel-open");
  const backdrop = $("panel-backdrop");
  if (backdrop) {
    backdrop.hidden = false;
  }
}

function closePanel() {
  document.body.classList.remove("panel-open");
  const backdrop = $("panel-backdrop");
  if (backdrop) {
    backdrop.hidden = true;
  }
}

async function selectDate(iso, { open = false } = {}) {
  const value = dateOrToday(iso);
  state.selectedDate = value;
  const outside =
    !state.calendar.start ||
    !state.calendar.end ||
    value < state.calendar.start ||
    value > state.calendar.end;
  if (outside) {
    state.anchorDate = value;
    await loadCalendar();
  } else {
    renderCalendar();
    renderDayPanel();
  }
  if (open) {
    openPanel();
  }
}

async function goToDate(iso, { open = true } = {}) {
  const value = dateOrToday(iso);
  state.anchorDate = value;
  state.selectedDate = value;
  await refreshAll();
  if (open) {
    openPanel();
  }
}

function openNoteDialog(note = null, date = state.selectedDate) {
  if (!state.settings) {
    return;
  }
  state.editingNote = note;
  state.noteDirty = false;
  const editing = Boolean(note);
  $("note-id").value = editing ? String(note.id) : "";
  $("note-dialog-title").textContent = t(editing ? "note.edit" : "note.new");
  $("note-title").value = note?.title || "";
  $("note-date").value = note?.note_date || dateOrToday(date);
  $("note-time").value = note?.time || "";
  $("note-content").value = note?.content || "";
  fillNoteCategorySelect(
    $("note-category"),
    note?.category || "",
    t("note.no_category"),
  );
  fillNotePrioritySelect(
    $("note-priority"),
    note?.priority || "",
    t("note.no_priority"),
  );
  const color = note?.color && HEX_COLOR.test(note.color) ? note.color : "#4f46e5";
  $("note-color").value = color;
  $("note-color-none").checked = !note?.color;
  $("note-color").disabled = !note?.color;
  $("note-recurrence").value = note?.recurrence || "none";
  $("note-recurrence-end").value = note?.recurrence_end || "";
  $("note-completed").checked = Boolean(note?.completed);
  $("completed-field").hidden = !editing;
  $("note-delete").hidden = !editing;
  $("note-series-hint").hidden = !(
    note?.recurrence && note.recurrence !== "none"
  );
  updateRecurrenceEndField();
  updateNotePreview();
  syncNoteFieldVisibility();
  const dialog = $("note-dialog");
  if (dialog && !dialog.open) {
    dialog.showModal();
  }
  window.setTimeout(() => {
    const title = $("note-title");
    if (title) {
      title.focus();
    }
  }, 40);
}

function updateRecurrenceEndField() {
  const recurrence = $("note-recurrence")?.value || "none";
  const field = $("recurrence-end-field");
  if (field) {
    field.hidden = recurrence === "none";
  }
  const end = $("note-recurrence-end");
  const start = $("note-date")?.value;
  if (end && start) {
    end.min = start;
  }
  if (recurrence === "none" && end) {
    end.value = "";
  }
}

function updateNotePreview() {
  const preview = $("note-preview");
  if (!preview) {
    return;
  }
  const content = $("note-content")?.value.trim() || "";
  preview.innerHTML = content
    ? `<div class="markdown">${renderMarkdown(content)}</div>`
    : `<p class="empty-hint">${escapeHtml(t("note.preview_empty"))}</p>`;
}

function collectNotePayload() {
  const title = $("note-title")?.value.trim() || "";
  const content = $("note-content")?.value.trim() || "";
  if (!title && !content) {
    showToast(t("note.form_error"), "error");
    return null;
  }
  const noteDate = parseDateInput($("note-date")?.value);
  if (!noteDate) {
    showToast(t("error.validation"), "error");
    return null;
  }
  const recurrence = $("note-recurrence")?.value || "none";
  const recurrenceEnd =
    recurrence === "none" ? null : parseDateInput($("note-recurrence-end")?.value);
  if (recurrenceEnd && recurrenceEnd < noteDate) {
    showToast(t("error.validation"), "error");
    return null;
  }
  const colorNone = $("note-color-none")?.checked;
  return {
    title,
    content,
    note_date: noteDate,
    time: $("note-time")?.value || null,
    category: $("note-category")?.value || null,
    priority: $("note-priority")?.value || null,
    color: colorNone ? null : $("note-color")?.value || null,
    completed: Boolean($("note-completed")?.checked),
    recurrence,
    recurrence_end: recurrenceEnd,
  };
}

async function submitNoteForm(event) {
  event.preventDefault();
  const payload = collectNotePayload();
  if (!payload) {
    return;
  }
  const editing = state.editingNote;
  try {
    const saved = editing
      ? await api.put(`/api/notes/${editing.id}`, payload)
      : await api.post("/api/notes", payload);
    state.noteDirty = false;
    const dialog = $("note-dialog");
    if (dialog?.open) {
      dialog.close();
    }
    showToast(t(editing ? "messages.note_saved" : "messages.note_created"), "success");
    const outside =
      !state.calendar.start ||
      !state.calendar.end ||
      saved.note_date < state.calendar.start ||
      saved.note_date > state.calendar.end;
    if (outside) {
      state.anchorDate = saved.note_date;
    }
    state.selectedDate = saved.note_date;
    await refreshAll();
    openPanel();
  } catch (error) {
    reportError(error);
  }
}

async function deleteNote(note) {
  if (!note) {
    return;
  }
  if (!window.confirm(t("messages.confirm_delete_note"))) {
    return;
  }
  try {
    await api.delete(`/api/notes/${note.id}`);
    const dialog = $("note-dialog");
    if (dialog?.open) {
      state.noteDirty = false;
      dialog.close();
    }
    showToast(t("messages.note_deleted"), "success");
    await refreshAll();
  } catch (error) {
    reportError(error);
  }
}

async function toggleNoteCompleted(note) {
  if (!note) {
    return;
  }
  try {
    await api.put(`/api/notes/${note.id}`, { completed: !note.completed });
    await refreshAll();
  } catch (error) {
    reportError(error);
  }
}

async function createQuickNote(content, targetDate = null) {
  const value = String(content || "").trim();
  if (!value) {
    return false;
  }
  try {
    const created = await api.post("/api/quick-notes", { content: value });
    if (targetDate) {
      await api.post(`/api/quick-notes/${created.id}/assign`, {
        note_date: targetDate,
        category: null,
        priority: null,
      });
      await refreshAll();
      showToast(
        t("messages.quick_assigned", {
          date: formatDate(targetDate, state.settings.date_format),
        }),
        "success",
      );
    } else {
      await loadQuickNotes();
      showToast(t("messages.quick_saved"), "success");
    }
    const input = $("quick-input");
    if (input) {
      input.value = "";
    }
    return true;
  } catch (error) {
    reportError(error);
    return false;
  }
}

function editQuickNote(id) {
  const item = state.quickNotes.find((entry) => entry.id === Number(id));
  const row = document.querySelector(`.quick-item[data-quick-id="${id}"]`);
  if (!item || !row) {
    return;
  }
  row.innerHTML = `<textarea class="quick-edit-input" maxlength="5000">${escapeHtml(
    item.content,
  )}</textarea>
    <div class="quick-item-meta">
      <span></span>
      <span class="quick-item-actions">
        <button type="button" class="btn btn-ghost btn-small" data-action="quick-cancel" data-quick-id="${id}">${escapeHtml(
          t("common.cancel"),
        )}</button>
        <button type="button" class="btn btn-primary btn-small" data-action="quick-save" data-quick-id="${id}">${escapeHtml(
          t("common.save"),
        )}</button>
      </span>
    </div>`;
  row.querySelector("textarea")?.focus();
}

async function saveQuickEdit(id) {
  const row = document.querySelector(`.quick-item[data-quick-id="${id}"]`);
  const value = row?.querySelector("textarea")?.value.trim() || "";
  if (!value) {
    showToast(t("error.validation"), "error");
    return;
  }
  try {
    await api.put(`/api/quick-notes/${id}`, { content: value });
    await loadQuickNotes();
    showToast(t("messages.quick_saved"), "success");
  } catch (error) {
    reportError(error);
  }
}

async function assignQuickNote(id) {
  const target =
    parseDateInput($("quick-target-date")?.value) ||
    dateOrToday(state.selectedDate);
  try {
    await api.post(`/api/quick-notes/${id}/assign`, {
      note_date: target,
      category: null,
      priority: null,
    });
    await refreshAll();
    showToast(
      t("messages.quick_assigned", {
        date: formatDate(target, state.settings.date_format),
      }),
      "success",
    );
  } catch (error) {
    reportError(error);
  }
}

async function deleteQuickNote(id) {
  if (!window.confirm(t("messages.confirm_delete_quick"))) {
    return;
  }
  try {
    await api.delete(`/api/quick-notes/${id}`);
    await loadQuickNotes();
    showToast(t("messages.quick_deleted"), "success");
  } catch (error) {
    reportError(error);
  }
}

function openQuickTray() {
  if (state.settings?.show_quick_notes) {
    openPanel();
    $("quick-tray")?.scrollIntoView({ block: "nearest" });
  } else {
    $("quick-input")?.focus();
  }
}

function formatHolidays(holidays) {
  return (holidays || [])
    .map((item) => `${item.date}|${item.name}`)
    .join("\n");
}

function parseHolidays(value) {
  const holidays = [];
  for (const raw of String(value || "").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) {
      continue;
    }
    const separator = line.indexOf("|");
    if (separator <= 0) {
      showToast(t("messages.holiday_error", { line }), "error");
      return null;
    }
    const holidayDate = line.slice(0, separator).trim();
    const name = line.slice(separator + 1).trim();
    const shortDate = /^(\d{2})-(\d{2})$/.exec(holidayDate);
    if (shortDate) {
      const month = Number(shortDate[1]);
      const day = Number(shortDate[2]);
      if (month < 1 || month > 12 || day < 1 || day > 31 || !name) {
        showToast(t("messages.holiday_error", { line }), "error");
        return null;
      }
    } else if (!isValidISODate(holidayDate) || !name) {
      showToast(t("messages.holiday_error", { line }), "error");
      return null;
    }
    holidays.push({ date: holidayDate, name });
  }
  return holidays;
}

async function applyRemoteSettings(settings) {
  state.settings = settings;
  state.meta = await api.get("/api/meta");
  await loadLanguage(settings.language);
  applyTranslations(document);
  applyAppearance();
  populateStaticOptions();
}

function openSettingsDialog() {
  if (!state.settings) {
    return;
  }
  const settings = state.settings;
  $("settings-app-name").value = settings.app_name;
  $("settings-language").value = settings.language;
  $("settings-timezone").value = settings.timezone;
  $("settings-first-day").value = String(settings.first_day_of_week);
  $("settings-date-format").value = settings.date_format;
  $("settings-time-format").value = settings.time_format;
  $("settings-theme").value = settings.theme;
  $("settings-accent").value =
    settings.accent_color && HEX_COLOR.test(settings.accent_color)
      ? settings.accent_color
      : "#4f46e5";
  $("settings-font-family").value = settings.font_family;
  $("settings-font-size").value = String(settings.font_size);
  $("settings-font-size-value").textContent = String(settings.font_size);
  $("settings-density").value = settings.density;
  $("settings-default-view").value = settings.default_view;
  $("settings-show-week-numbers").checked = settings.show_week_numbers;
  $("settings-show-holidays").checked = settings.show_holidays;
  $("settings-show-completed").checked = settings.show_completed;
  $("settings-show-month-previews").checked = settings.show_month_previews;
  $("settings-show-quick-notes").checked = settings.show_quick_notes;
  $("settings-holidays").value = formatHolidays(settings.holidays);
  $("settings-field-time").checked = settings.note_fields.time;
  $("settings-field-priority").checked = settings.note_fields.priority;
  $("settings-field-category").checked = settings.note_fields.category;
  $("settings-field-color").checked = settings.note_fields.color;
  $("settings-host").value = settings.server.host;
  $("settings-port").value = String(settings.server.port);
  $("settings-database").value = settings.server.database_path;
  $("settings-backup-dir").value = settings.server.backup_dir;
  $("settings-backups-enabled").checked = settings.backups.enabled;
  $("settings-backup-frequency").value = String(settings.backups.frequency_hours);
  $("settings-backup-keep").value = String(settings.backups.keep);

  state.labelsDraft = {
    categories: settings.categories.map((item) => ({ ...item })),
    priorities: settings.priorities.map((item) => ({ ...item })),
  };
  renderLabels("categories");
  renderLabels("priorities");

  document.querySelectorAll("[data-shortcut]").forEach((input) => {
    input.value = settings.shortcuts[input.dataset.shortcut] || "";
  });

  setSettingsTab(state.activeSettingsTab || "general");
  refreshBackups().catch(reportError);
  const dialog = $("settings-dialog");
  if (dialog && !dialog.open) {
    dialog.showModal();
  }
}

function setSettingsTab(name) {
  state.activeSettingsTab = name;
  document.querySelectorAll("[data-settings-tab]").forEach((button) => {
    const active = button.dataset.settingsTab === name;
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.setAttribute("tabindex", active ? "0" : "-1");
  });
  document.querySelectorAll("[data-settings-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.settingsPanel !== name;
  });
}

function renderLabels(type) {
  const container = $(`settings-${type}`);
  if (!container) {
    return;
  }
  const items = state.labelsDraft[type] || [];
  container.innerHTML = items
    .map(
      (item) => `<div class="label-row" data-label-id="${escapeHtml(item.id)}">
        <input type="text" data-role="label" maxlength="50" value="${escapeHtml(
          item.label,
        )}" aria-label="${escapeHtml(t("settings.labels.label"))}" />
        <input type="color" data-role="color" value="${escapeHtml(
          item.color,
        )}" aria-label="${escapeHtml(t("settings.labels.color"))}" />
        <button type="button" class="icon-btn" data-remove-label="${escapeHtml(
          item.id,
        )}" aria-label="${escapeHtml(t("settings.labels.remove"))}">${icon(
          "x",
        )}</button>
      </div>`,
    )
    .join("");
}

function addLabel(type) {
  const prefix = type === "categories" ? "category" : "priority";
  const palette = ["#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#64748b"];
  const items = state.labelsDraft[type];
  items.push({
    id: uniqueId(prefix),
    label: t("settings.labels.default_label"),
    color: palette[items.length % palette.length],
  });
  renderLabels(type);
  const container = $(`settings-${type}`);
  const inputs = container?.querySelectorAll('[data-role="label"]');
  inputs?.[inputs.length - 1]?.focus();
}

function removeLabel(type, id) {
  const items = state.labelsDraft[type];
  const index = items.findIndex((item) => item.id === id);
  if (index < 0) {
    return;
  }
  if (items.length <= 1) {
    showToast(t("messages.labels_required"), "error");
    return;
  }
  items.splice(index, 1);
  renderLabels(type);
}

function updateLabelInput(event, type) {
  const input = event.target;
  const row = input.closest?.(".label-row");
  if (!row) {
    return;
  }
  const item = state.labelsDraft[type].find(
    (entry) => entry.id === row.dataset.labelId,
  );
  if (!item) {
    return;
  }
  if (input.matches('[data-role="label"]')) {
    item.label = input.value;
  } else if (input.matches('[data-role="color"]')) {
    item.color = input.value;
  }
}

function collectSettingsFromForm() {
  const categories = state.labelsDraft.categories.map((item) => ({
    id: item.id,
    label: item.label.trim(),
    color: item.color,
  }));
  const priorities = state.labelsDraft.priorities.map((item) => ({
    id: item.id,
    label: item.label.trim(),
    color: item.color,
  }));
  if (
    !categories.length ||
    !priorities.length ||
    categories.some((item) => !item.label) ||
    priorities.some((item) => !item.label)
  ) {
    showToast(t("messages.labels_required"), "error");
    return null;
  }

  const shortcuts = {};
  document.querySelectorAll("[data-shortcut]").forEach((input) => {
    shortcuts[input.dataset.shortcut] = input.value.trim();
  });
  const shortcutValues = Object.values(shortcuts).map(normalizeShortcut);
  if (
    shortcutValues.some((value) => !value) ||
    new Set(shortcutValues).size !== shortcutValues.length
  ) {
    showToast(t("messages.unique_shortcuts"), "error");
    return null;
  }

  const holidays = parseHolidays($("settings-holidays")?.value);
  if (holidays === null) {
    return null;
  }

  return {
    app_name: $("settings-app-name")?.value.trim() || "",
    language: $("settings-language")?.value || "es",
    timezone: $("settings-timezone")?.value.trim() || "UTC",
    first_day_of_week: Number($("settings-first-day")?.value ?? 1),
    date_format: $("settings-date-format")?.value || "DD/MM/YYYY",
    time_format: $("settings-time-format")?.value || "24h",
    theme: $("settings-theme")?.value || "auto",
    accent_color: $("settings-accent")?.value || "#4f46e5",
    font_family: $("settings-font-family")?.value || "system",
    font_size: Number($("settings-font-size")?.value ?? 16),
    density: $("settings-density")?.value || "comfortable",
    default_view: $("settings-default-view")?.value || "month",
    show_week_numbers: Boolean($("settings-show-week-numbers")?.checked),
    show_holidays: Boolean($("settings-show-holidays")?.checked),
    show_completed: Boolean($("settings-show-completed")?.checked),
    show_month_previews: Boolean($("settings-show-month-previews")?.checked),
    show_quick_notes: Boolean($("settings-show-quick-notes")?.checked),
    holidays,
    categories,
    priorities,
    note_fields: {
      time: Boolean($("settings-field-time")?.checked),
      priority: Boolean($("settings-field-priority")?.checked),
      category: Boolean($("settings-field-category")?.checked),
      color: Boolean($("settings-field-color")?.checked),
    },
    shortcuts,
    server: {
      host: $("settings-host")?.value.trim() || "",
      port: Number($("settings-port")?.value ?? 8000),
      database_path: $("settings-database")?.value.trim() || "",
      backup_dir: $("settings-backup-dir")?.value.trim() || "",
    },
    backups: {
      enabled: Boolean($("settings-backups-enabled")?.checked),
      frequency_hours: Number($("settings-backup-frequency")?.value ?? 24),
      keep: Number($("settings-backup-keep")?.value ?? 10),
    },
  };
}

function restartSettingsChanged(previous, next) {
  return (
    previous.server.host !== next.server.host ||
    previous.server.port !== next.server.port ||
    previous.server.database_path !== next.server.database_path ||
    previous.server.backup_dir !== next.server.backup_dir
  );
}

async function submitSettingsForm(event) {
  event.preventDefault();
  const payload = collectSettingsFromForm();
  if (!payload) {
    return;
  }
  const previous = state.settings;
  try {
    const saved = await api.put("/api/settings", payload);
    const needsRestart = restartSettingsChanged(previous, saved);
    await applyRemoteSettings(saved);
    const dialog = $("settings-dialog");
    if (dialog?.open) {
      dialog.close();
    }
    const message = needsRestart
      ? `${t("messages.settings_saved")} ${t("messages.restart_needed")}`
      : t("messages.settings_saved");
    showToast(message, "success");
    await refreshAll();
  } catch (error) {
    reportError(error);
  }
}

async function resetSettings() {
  if (!window.confirm(t("messages.confirm_reset"))) {
    return;
  }
  try {
    const saved = await api.post("/api/settings/reset");
    await applyRemoteSettings(saved);
    const dialog = $("settings-dialog");
    if (dialog?.open) {
      dialog.close();
    }
    showToast(t("messages.settings_reset"), "success");
    await refreshAll();
  } catch (error) {
    reportError(error);
  }
}

async function refreshBackups() {
  state.backups = await api.get("/api/backups");
  renderBackups();
}

function renderBackups() {
  const container = $("settings-backups");
  if (!container) {
    return;
  }
  if (!state.backups.length) {
    container.innerHTML = `<p class="hint">${escapeHtml(
      t("settings.data.no_backups"),
    )}</p>`;
    return;
  }
  container.innerHTML = state.backups
    .map((item) => {
      const created = new Date(item.created_at);
      const label = Number.isNaN(created.getTime())
        ? item.created_at
        : new Intl.DateTimeFormat(locale(), {
            dateStyle: "short",
            timeStyle: "short",
          }).format(created);
      return `<div class="backup-item">
        <span class="backup-item-name" title="${escapeHtml(item.name)}">${escapeHtml(
          item.name,
        )}</span>
        <span class="backup-item-meta">${escapeHtml(
          label,
        )} · ${escapeHtml(humanSize(item.size))}</span>
        <a href="/api/backups/${encodeURIComponent(item.name)}" download>${escapeHtml(
          t("common.download"),
        )}</a>
      </div>`;
    })
    .join("");
}

async function createBackupNow() {
  try {
    await api.post("/api/backups", {});
    await refreshBackups();
    showToast(t("messages.backup_created"), "success");
  } catch (error) {
    reportError(error);
  }
}

function exportData(format) {
  const link = document.createElement("a");
  link.href = `/api/export?format=${encodeURIComponent(format)}`;
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
  showToast(t("messages.exported"), "success");
}

async function importData() {
  const file = $("settings-import-file")?.files?.[0];
  if (!file) {
    showToast(t("settings.data.file_error"), "error");
    return;
  }
  const mode = $("settings-import-mode")?.value || "merge";
  const importSettings = Boolean($("settings-import-settings")?.checked);
  if (mode === "replace" && !window.confirm(t("messages.confirm_replace"))) {
    return;
  }

  let payload;
  try {
    payload = JSON.parse(await file.text());
  } catch (error) {
    showToast(t("messages.file_error"), "error");
    return;
  }
  if (!payload || typeof payload !== "object") {
    showToast(t("settings.data.file_error"), "error");
    return;
  }

  try {
    const result = await api.post(
      `/api/import${buildQuery({
        mode,
        import_settings: importSettings ? "true" : "false",
      })}`,
      payload,
    );
    showToast(
      t("settings.data.import_ok", {
        notes: result.notes_imported,
        quick: result.quick_notes_imported,
      }),
      "success",
    );
    const dialog = $("settings-dialog");
    if (dialog?.open) {
      dialog.close();
    }
    if (result.settings_imported) {
      await applyRemoteSettings(await api.get("/api/settings"));
    }
    await refreshAll();
  } catch (error) {
    reportError(error);
  }
}

async function seedDemoData() {
  try {
    const result = await api.post("/api/demo/seed", {});
    showToast(
      t(result.skipped ? "messages.demo_skipped" : "messages.demo_loaded"),
      "success",
    );
    await refreshAll();
  } catch (error) {
    reportError(error);
  }
}

function findNote(id) {
  const numeric = Number(id);
  for (const items of Object.values(state.calendar.days)) {
    const found = items.find((item) => item.id === numeric);
    if (found) {
      return found;
    }
  }
  return state.searchResults.find((item) => item.id === numeric) || null;
}

function requestCloseDialog(dialog) {
  if (!dialog) {
    return;
  }
  if (dialog.id === "note-dialog" && state.noteDirty) {
    if (!window.confirm(t("messages.close_unsaved"))) {
      return;
    }
  }
  if (dialog.id === "note-dialog") {
    state.noteDirty = false;
  }
  dialog.close();
}

async function setView(view) {
  if (!["month", "week", "day", "board"].includes(view)) {
    return;
  }
  state.view = view;
  state.anchorDate = dateOrToday(state.selectedDate);
  await loadCalendar();
}

async function navigate(offset) {
  const anchor = dateOrToday(state.anchorDate);
  let target;
  if (state.view === "month") {
    target = addMonths(anchor, offset);
  } else if (state.view === "week") {
    target = addDays(anchor, offset * 7);
  } else {
    target = addDays(anchor, offset);
  }
  state.anchorDate = toISO(target);
  state.selectedDate = state.anchorDate;
  await loadCalendar();
}

async function goToday() {
  await goToDate(todayISO(), { open: true });
}

async function handleDocumentClick(event) {
  if (!(event.target instanceof Element)) {
    return;
  }

  const closeButton = event.target.closest("[data-close-dialog]");
  if (closeButton) {
    requestCloseDialog(closeButton.closest("dialog"));
    return;
  }

  const actionButton = event.target.closest("[data-action]");
  if (actionButton) {
    const action = actionButton.dataset.action;
    const noteId = actionButton.dataset.noteId;
    const quickId = actionButton.dataset.quickId;
    if (action === "open" || action === "edit") {
      const note = findNote(noteId);
      if (note) {
        openNoteDialog(note);
      }
    } else if (action === "toggle") {
      await toggleNoteCompleted(findNote(noteId));
    } else if (action === "delete") {
      await deleteNote(findNote(noteId));
    } else if (action === "quick-assign") {
      await assignQuickNote(quickId);
    } else if (action === "quick-edit") {
      editQuickNote(quickId);
    } else if (action === "quick-save") {
      await saveQuickEdit(quickId);
    } else if (action === "quick-cancel") {
      renderQuickNotes();
    } else if (action === "quick-delete") {
      await deleteQuickNote(quickId);
    }
    return;
  }

  const searchResult = event.target.closest("[data-search-id]");
  if (searchResult) {
    const note = state.searchResults.find(
      (item) => item.id === Number(searchResult.dataset.searchId),
    );
    const dialog = $("search-dialog");
    if (dialog?.open) {
      dialog.close();
    }
    if (note) {
      await goToDate(note.note_date, { open: true });
      openNoteDialog(note);
    }
    return;
  }

  const addButton = event.target.closest("[data-add-date]");
  if (addButton) {
    openNoteDialog(null, addButton.dataset.addDate);
    return;
  }

  const noteButton = event.target.closest("[data-note-id]");
  if (noteButton) {
    const note = findNote(noteButton.dataset.noteId);
    if (note) {
      openNoteDialog(note);
    }
    return;
  }

  const dateTarget = event.target.closest("[data-date]");
  if (dateTarget) {
    await selectDate(dateTarget.dataset.date, { open: true });
  }
}

function handleShortcut(event) {
  if (!state.settings || isTypingTarget(event.target)) {
    return;
  }
  if (document.querySelector("dialog[open]")) {
    return;
  }
  const pressed = normalizeShortcut(eventShortcut(event));
  if (!pressed) {
    return;
  }
  const shortcuts = state.settings.shortcuts;
  const name = Object.keys(shortcuts).find(
    (key) => normalizeShortcut(shortcuts[key]) === pressed,
  );
  if (!name) {
    return;
  }
  event.preventDefault();
  if (name === "new_note") {
    openNoteDialog(null, state.selectedDate);
  } else if (name === "quick_note") {
    $("quick-input")?.focus();
  } else if (name === "today") {
    goToday();
  } else if (name === "search") {
    openSearchDialog();
  } else if (name === "settings") {
    openSettingsDialog();
  }
}

function bindEvents() {
  $("prev-btn")?.addEventListener("click", () => navigate(-1));
  $("next-btn")?.addEventListener("click", () => navigate(1));
  $("today-btn")?.addEventListener("click", goToday);
  $("new-note-btn")?.addEventListener("click", () =>
    openNoteDialog(null, state.selectedDate),
  );
  $("panel-add")?.addEventListener("click", () =>
    openNoteDialog(null, state.selectedDate),
  );
  $("quick-tray-btn")?.addEventListener("click", openQuickTray);
  $("search-btn")?.addEventListener("click", openSearchDialog);
  $("settings-btn")?.addEventListener("click", openSettingsDialog);
  $("panel-close")?.addEventListener("click", closePanel);
  $("panel-backdrop")?.addEventListener("click", closePanel);

  document.querySelectorAll(".view-btn[data-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });

  $("reminder-dismiss")?.addEventListener("click", () => {
    state.remindersDismissed = true;
    renderReminders();
  });
  $("reminder-view")?.addEventListener("click", () => goToday());

  $("quick-bar")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("quick-input");
    const value = input?.value.trim() || "";
    const target = parseDateInput($("quick-date")?.value);
    if (value && (await createQuickNote(value, target))) {
      input?.focus();
    }
  });

  $("note-form")?.addEventListener("submit", submitNoteForm);
  $("note-form")?.addEventListener("input", (event) => {
    state.noteDirty = true;
    if (event.target?.id === "note-content") {
      updateNotePreview();
    }
    if (event.target?.id === "note-date") {
      updateRecurrenceEndField();
    }
  });
  $("note-form")?.addEventListener("change", (event) => {
    if (event.target?.id === "note-recurrence") {
      updateRecurrenceEndField();
    }
    if (event.target?.id === "note-color-none") {
      const color = $("note-color");
      if (color) {
        color.disabled = event.target.checked;
      }
    }
  });
  $("note-delete")?.addEventListener("click", () =>
    deleteNote(state.editingNote),
  );

  $("search-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
  });
  $("search-clear")?.addEventListener("click", () => {
    ["search-text", "search-category", "search-priority", "search-status", "search-from", "search-to"].forEach(
      (id) => {
        const field = $(id);
        if (field) {
          field.value = "";
        }
      },
    );
    state.searchResults = [];
    const summary = $("search-summary");
    const results = $("search-results");
    if (summary) {
      summary.textContent = "";
    }
    if (results) {
      results.innerHTML = "";
    }
    $("search-text")?.focus();
  });

  $("settings-tabs")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-settings-tab]");
    if (button) {
      setSettingsTab(button.dataset.settingsTab);
    }
  });
  $("settings-form")?.addEventListener("submit", submitSettingsForm);
  $("settings-reset")?.addEventListener("click", resetSettings);
  $("settings-add-category")?.addEventListener("click", () =>
    addLabel("categories"),
  );
  $("settings-add-priority")?.addEventListener("click", () =>
    addLabel("priorities"),
  );
  $("settings-categories")?.addEventListener("input", (event) =>
    updateLabelInput(event, "categories"),
  );
  $("settings-priorities")?.addEventListener("input", (event) =>
    updateLabelInput(event, "priorities"),
  );
  $("settings-categories")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-label]");
    if (button) {
      removeLabel("categories", button.dataset.removeLabel);
    }
  });
  $("settings-priorities")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-label]");
    if (button) {
      removeLabel("priorities", button.dataset.removeLabel);
    }
  });
  $("settings-font-size")?.addEventListener("input", (event) => {
    const output = $("settings-font-size-value");
    if (output) {
      output.textContent = event.target.value;
    }
  });
  $("settings-export-json")?.addEventListener("click", () => exportData("json"));
  $("settings-export-csv")?.addEventListener("click", () => exportData("csv"));
  $("settings-import-btn")?.addEventListener("click", importData);
  $("settings-seed-btn")?.addEventListener("click", seedDemoData);
  $("settings-backup-now")?.addEventListener("click", createBackupNow);

  document.querySelectorAll("[data-shortcut]").forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        input.blur();
        return;
      }
      const shortcut = eventShortcut(event);
      if (!shortcut) {
        return;
      }
      event.preventDefault();
      input.value = shortcut;
    });
  });

  document.addEventListener("click", (event) => {
    handleDocumentClick(event).catch(reportError);
  });
  document.addEventListener("keydown", handleShortcut);

  document.querySelectorAll("dialog").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        requestCloseDialog(dialog);
      }
    });
    dialog.addEventListener("cancel", (event) => {
      if (dialog.id === "note-dialog" && state.noteDirty) {
        event.preventDefault();
        requestCloseDialog(dialog);
      }
    });
  });

  if (darkQuery?.addEventListener) {
    darkQuery.addEventListener("change", () => {
      if (state.settings?.theme === "auto") {
        applyAppearance();
      }
    });
  }
}

function hideLoading() {
  const loading = $("loading-overlay");
  if (!loading) {
    return;
  }
  loading.classList.add("is-hidden");
  window.setTimeout(() => {
    loading.hidden = true;
  }, 220);
}

async function init() {
  try {
    const [settings, meta] = await Promise.all([
      api.get("/api/settings"),
      api.get("/api/meta"),
    ]);
    state.settings = settings;
    state.meta = meta;
    state.view = settings.default_view;
    state.anchorDate = meta.today;
    state.selectedDate = meta.today;

    await loadLanguage(settings.language);
    applyTranslations(document);
    applyAppearance();
    populateStaticOptions();
    bindEvents();
    await refreshAll();
  } catch (error) {
    const loading = $("loading-overlay");
    if (loading) {
      loading.textContent = t("error.generic");
      loading.classList.add("error-visible");
    }
    reportError(error);
  } finally {
    hideLoading();
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, { once: true });
} else {
  init();
}

function bindBoardEvents() {
  const columns = document.querySelectorAll(".board-column");
  if (!columns.length) {
    return;
  }

  let dragNote = null;
  let dragFromColumn = null;
  let dragFromStatus = null;

  // Handle drag start on board notes
  document.querySelectorAll(".board-note").forEach((note) => {
    note.setAttribute("draggable", "true");
    note.addEventListener("dragstart", (event) => {
      dragNote = note;
      dragFromColumn = note.closest(".board-column");
      dragFromStatus = dragFromColumn ? dragFromColumn.dataset.status : null;
      event.dataTransfer.setData("text/plain", note.id);
      event.dataTransfer.effectAllowed = "move";
      note.classList.add("is-dragging");
    });

    note.addEventListener("dragend", (event) => {
      if (dragNote) {
        dragNote.classList.remove("is-dragging");
        dragNote = null;
        dragFromColumn = null;
        dragFromStatus = null;
      }
    });
  });

  // Handle drag over column
  columns.forEach((column) => {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      column.classList.add("drag-over");
    });

    column.addEventListener("dragleave", (event) => {
      column.classList.remove("drag-over");
    });

    column.addEventListener("drop", (event) => {
      event.preventDefault();
      column.classList.remove("drag-over");
      const noteId = event.dataTransfer.getData("text/plain");
      if (!noteId) {
        return;
      }
      const note = document.querySelector(`.board-note[data-note-id="${noteId}"]`);
      if (!note) {
        return;
      }
      const targetColumn = column.dataset.status;
      if (!targetColumn) {
        return;
      }
      const success = moveNoteInBoard(note, targetColumn, dragFromStatus);
      if (!success) {
        showToast(t("messages.move_failed"), "error");
      }
    });
  });

  // Keyboard navigation for board add buttons
  document.querySelectorAll(".board-column").forEach((column) => {
    const addBtn = column.querySelector(".board-add");
    if (addBtn) {
      addBtn.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          const status = column.dataset.status;
          openNoteDialog(null, null, status);
        }
      });
    }
  });
}

function moveNoteInBoard(noteElement, targetStatus, fromStatus) {
  const noteId = noteElement.dataset.noteId;
  if (!noteId) {
    return false;
  }
  const body = {
    column: targetStatus,
  };
  // If dropping in the same column, calculate position
  if (targetStatus === fromStatus) {
    const column = noteElement.closest(".board-column");
    const notes = Array.from(column.querySelectorAll(".board-note")).filter(
      (n) => n.dataset.noteId !== noteId
    );
    // Position is the index among remaining notes
    const insertIndex = notes.findIndex((n) => n.compareDocumentPosition(noteElement) & 2);
    body.position = insertIndex;
  }

  return api.post(`/api/notes/${noteId}/move`, body);
}

// ---------------------------------------------------------------------------
// Vista "Hoy" - Bloques de renderizado
// ---------------------------------------------------------------------------

function renderRoutinesBlock(iso, todayRoutineRecords, routineStreaks) {
  const today = isoToDate(iso);
  const routineItems = getTodayRoutines(today);
  
  if (!routineItems.length) {
    return `<div class="routine-block">
      <div class="routine-block-header">
        <span class="routine-block-title">${escapeHtml(t("day.routines"))}</span>
      </div>
      <div class="routine-block-content">
        <p class="empty-state">${escapeHtml(t("day.empty"))}</p>
      </div>
    </div>`;
  }

  const routineHTML = routineItems.map((routine) => {
    const record = todayRoutineRecords[routine.id] || {};
    const completed = record.completed;
    const streakInfo = routineStreaks[routine.id] || { streak: 0 };
    const checklist = getChecklistItems(routine.checklist_template || "");
    
    return `<div class="routine-item" data-routine-id="${routine.id}">
      <span class="routine-icon">${routine.icon || "🔄"}</span>
      <span class="routine-title">${escapeHtml(routine.title)}</span>
      <span class="routine-streak">${streakInfo.streak}d streak</span>
      <div class="routine-checklist">
        ${checklist.map((item, i) => `
          <label class="checklist-item">
            <input type="checkbox" ${completed ? "checked" : ""} disabled>
            <span>${escapeHtml(item)}</span>
          </label>
        `).join("")}
      </div>
    </div>`;
  }).join("");

  return `<div class="routine-block">
    <div class="routine-block-header">
      <span class="routine-block-title">${escapeHtml(t("day.routines"))}</span>
    </div>
    <div class="routine-block-content">
      ${routineHTML}
    </div>
  </div>`;
}

function renderTasksBlock(iso, items) {
  const today = isoToDate(iso);
  const todayTasks = items.filter(item => item.note_date && item.note_date <= today);
  const upcomingTasks = items.filter(item => 
    item.note_date && item.note_date > isoToDate(state.anchorDate) && 
    item.note_date <= isoToDate(addDays(iso, 7))
  );
  
  const allTasks = [...todayTasks, ...upcomingTasks.filter(t => !todayTasks.some(tt => tt.id === t.id))];
  
  if (!allTasks.length) {
    return `<div class="tasks-block">
      <div class="tasks-block-header">
        <span class="tasks-block-title">${escapeHtml(t("day.tasks"))}</span>
      </div>
      <div class="tasks-block-content">
        <p class="empty-state">${escapeHtml(t("day.empty"))}</p>
      </div>
    </div>`;
  }

  const taskHTML = allTasks.map((task) => {
    const isToday = task.note_date && task.note_date <= today;
    const isCompleted = task.completed;
    const dueClass = isToday && !isCompleted ? " task-due" : "";
    const dueText = isToday && !isCompleted ? 
      `${escapeHtml(t("day.add"))} ${t("quick.date_optional")}` : "";
    
    return `<div class="task-item${dueClass}" data-note-id="${task.id}">
      <span class="task-dot" style="--dot-color: ${task.color || '#3B82F6'}"></span>
      <span class="task-title">${escapeHtml(taskTitle(task))}</span>
      ${dueText ? `<span class="task-due">${dueText}</span>` : ""}
    </div>`;
  }).join("");

  return `<div class="tasks-block">
    <div class="tasks-block-header">
      <span class="tasks-block-title">${escapeHtml(t("day.tasks"))}</span>
    </div>
    <div class="tasks-block-content">
      ${taskHTML.length > 0 ? taskHTML : `<p class="empty-state">${escapeHtml(t("day.empty"))}</p>`}
    </div>
  </div>`;
}

function renderAgendaBlock(iso, items) {
  const today = isoToDate(iso);
  const dayStart = startOfDay(iso);
  const dayEnd = endOfDay(iso);
  
  const dayItems = items.filter(item => 
    item.note_date && 
    new Date(item.note_date + 'T' + (item.time || '00:00')) >= dayStart && 
    new Date(item.note_date + 'T' + (item.time || '00:00')) <= dayEnd
  );
  
  const otherItems = items.filter(item => 
    item.note_date && 
    (new Date(item.note_date + 'T' + (item.time || '00:00')) < dayStart || 
     new Date(item.note_date + 'T' + (item.time || '00:00')) > dayEnd)
  ).slice(0, 3);
  
  const otherHtml = otherItems.length > 0 ? 
    `<div class="agenda-more">
      +${otherItems.length} más
    </div>` : "";

  if (!dayItems.length && !otherItems.length) {
    return `<div class="agenda-block">
      <div class="agenda-block-header">
        <span class="agenda-block-title">${escapeHtml(t("day.agenda"))}</span>
      </div>
      <div class="agenda-block-content">
        <p class="empty-state">${escapeHtml(t("day.empty"))}</p>
      </div>
    </div>`;
  }

  const dayHtml = dayItems.map((item) => {
    const timeStr = item.time ? `${escapeHtml(item.time)}` : "";
    const colorStyle = item.color ? `--dot-color: ${item.color}` : "";
    return `<div class="agenda-item" data-note-id="${item.id}">
      <span class="agenda-dot" style="${colorStyle}"></span>
      <span>${timeStr} ${escapeHtml(noteTitle(item))}</span>
    </div>`;
  }).join("");

  return `<div class="agenda-block">
    <div class="agenda-block-header">
      <span class="agenda-block-title">${escapeHtml(t("day.agenda"))}</span>
    </div>
    <div class="agenda-block-content">
      ${dayHtml}
      ${otherHtml}
    </div>
  </div>`;
}

// Helper functions for the day view
function getTodayRoutines(todayIso) {
  return api.get(`/api/routines/today`).then((data) => data || []);
}

function getChecklistItems(template) {
  return api.get(`/api/checklist/${template}`).then((items) => items || []);
}


// Helper functions for the day view
function isoToDate(iso) {
  const dateStr = iso.split('T')[0];
  const parts = dateStr.split('-');
  return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
}


function noteDate(note) {
  return note.note_date;
}

function taskTitle(task) {
  return task.title || t("note.untitled");
}

// Export for use in renderDayView
window.todayRoutineRecords = todayRoutineRecords;
window.routineStreaks = routineStreaks;
