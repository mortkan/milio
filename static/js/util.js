/** Utilidades de fechas, formato y seguridad para el frontend. */

const HTML_ENTITIES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => HTML_ENTITIES[char]);
}

export const pad = (value) => String(value).padStart(2, "0");

export function toISO(dateValue) {
  const date = dateValue instanceof Date ? dateValue : parseISO(dateValue);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function parseISO(value) {
  if (value instanceof Date) {
    return new Date(
      value.getFullYear(),
      value.getMonth(),
      value.getDate(),
      12,
    );
  }
  const [year, month, day] = String(value).split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1, 12);
}

export function daysInMonth(year, monthIndex) {
  return new Date(year, monthIndex + 1, 0).getDate();
}

export function addDays(value, amount) {
  const date = parseISO(value);
  date.setDate(date.getDate() + amount);
  return date;
}

export function addMonths(value, amount) {
  const date = parseISO(value);
  const targetMonth = date.getMonth() + amount;
  const year = date.getFullYear() + Math.floor(targetMonth / 12);
  const month = ((targetMonth % 12) + 12) % 12;
  const day = Math.min(date.getDate(), daysInMonth(year, month));
  return new Date(year, month, day, 12);
}

export function startOfWeek(value, firstDay = 1) {
  const date = parseISO(value);
  const offset = (date.getDay() - firstDay + 7) % 7;
  return addDays(date, -offset);
}

export function endOfWeek(value, firstDay = 1) {
  return addDays(startOfWeek(value, firstDay), 6);
}

export function startOfMonth(value) {
  const date = parseISO(value);
  return new Date(date.getFullYear(), date.getMonth(), 1, 12);
}

export function endOfMonth(value) {
  const date = parseISO(value);
  return new Date(date.getFullYear(), date.getMonth() + 1, 0, 12);
}

export function startOfMonthGrid(value, firstDay = 1) {
  return startOfWeek(startOfMonth(value), firstDay);
}

export function isoWeekNumber(value) {
  const date = parseISO(value);
  const utc = new Date(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()),
  );
  const day = utc.getUTCDay() || 7;
  utc.setUTCDate(utc.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(utc.getUTCFullYear(), 0, 1));
  return Math.ceil(((utc - yearStart) / 86_400_000 + 1) / 7);
}

export function formatDate(value, format = "DD/MM/YYYY") {
  const date = parseISO(value);
  const day = pad(date.getDate());
  const month = pad(date.getMonth() + 1);
  const year = date.getFullYear();
  switch (format) {
    case "MM/DD/YYYY":
      return `${month}/${day}/${year}`;
    case "YYYY-MM-DD":
      return `${year}-${month}-${day}`;
    case "DD.MM.YYYY":
      return `${day}.${month}.${year}`;
    default:
      return `${day}/${month}/${year}`;
  }
}

export function capitalize(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

export function formatLongDate(value, locale) {
  const date = parseISO(value);
  return capitalize(
    new Intl.DateTimeFormat(locale, {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(date),
  );
}

export function formatShortDate(value, locale) {
  const date = parseISO(value);
  return capitalize(
    new Intl.DateTimeFormat(locale, {
      day: "numeric",
      month: "short",
    }).format(date),
  );
}

export function formatMonthYear(value, locale) {
  const date = parseISO(value);
  return capitalize(
    new Intl.DateTimeFormat(locale, {
      month: "long",
      year: "numeric",
    }).format(date),
  );
}

export function formatWeekRange(startValue, endValue, locale) {
  const start = parseISO(startValue);
  const end = parseISO(endValue);
  const formatter = new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
  });
  let text = `${formatter.format(start)} – ${formatter.format(end)}`;
  if (start.getFullYear() === end.getFullYear()) {
    text += ` ${start.getFullYear()}`;
  } else {
    text += ` ${start.getFullYear()} – ${end.getFullYear()}`;
  }
  return capitalize(text);
}

export function formatTime(value, mode = "24h", locale = "es") {
  if (!value) {
    return "";
  }
  if (mode === "24h") {
    return value;
  }
  const [hours, minutes] = value.split(":").map(Number);
  const date = new Date(2000, 0, 1, hours, minutes);
  return new Intl.DateTimeFormat(locale, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function weekdayNames(locale, width = "short") {
  const formatter = new Intl.DateTimeFormat(locale, { weekday: width });
  const sunday = new Date(2023, 0, 1, 12);
  return Array.from({ length: 7 }, (_item, index) => {
    const date = new Date(sunday);
    date.setDate(sunday.getDate() + index);
    return formatter.format(date);
  });
}

export function weekdaysInOrder(firstDay, locale, width = "short") {
  const names = weekdayNames(locale, width);
  return Array.from({ length: 7 }, (_item, index) => names[(firstDay + index) % 7]);
}

export function humanSize(bytes) {
  if (!bytes) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** index;
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function uniqueId(prefix) {
  let random;
  try {
    random = crypto.randomUUID().slice(0, 8);
  } catch {
    random = Math.random().toString(36).slice(2, 10);
  }
  return `${prefix}-${random}`;
}

export function isValidISODate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const date = parseISO(value);
  return toISO(date) === value;
}
