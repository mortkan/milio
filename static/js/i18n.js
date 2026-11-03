/**
 * Carga y aplicación de traducciones. Los archivos viven en static/i18n/.
 * El español es el idioma de respaldo si falta una clave o un archivo.
 */

const state = {
  dictionary: {},
  fallback: {},
  language: "es",
};

function normalizeDictionary(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {};
  }
  const normalized = { ...raw };
  const root =
    raw.root && typeof raw.root === "object" && !Array.isArray(raw.root)
      ? raw.root
      : {};
  delete normalized.root;
  return { ...normalized, ...root };
}

function lookup(dictionary, key) {
  if (!dictionary || typeof dictionary !== "object") {
    return undefined;
  }
  if (Object.prototype.hasOwnProperty.call(dictionary, key)) {
    return dictionary[key];
  }
  return key.split(".").reduce((value, part) => {
    if (value && typeof value === "object" && part in value) {
      return value[part];
    }
    return undefined;
  }, dictionary);
}

function resolve(key) {
  return lookup(state.dictionary, key) ?? lookup(state.fallback, key);
}

function interpolate(value, variables = {}) {
  return value.replace(/\{\{(\w+)\}\}|\{(\w+)\}/g, (_match, doubleName, name) => {
    const variableName = doubleName || name;
    return Object.prototype.hasOwnProperty.call(variables, variableName)
      ? String(variables[variableName])
      : "";
  });
}

async function fetchDictionary(language) {
  const response = await fetch(`/static/i18n/${language}.json`, {
    cache: "no-cache",
  });
  if (!response.ok) {
    throw new Error(`Idioma no disponible: ${language}`);
  }
  return normalizeDictionary(await response.json());
}

export async function loadLanguage(language) {
  const requested = String(language || "es").toLowerCase();
  let dictionary = null;
  let loadedLanguage = requested;

  try {
    dictionary = await fetchDictionary(requested);
  } catch {
    dictionary = null;
  }

  if (!dictionary) {
    dictionary = await fetchDictionary("es");
    loadedLanguage = "es";
  }

  state.dictionary = dictionary;
  state.language = loadedLanguage;

  try {
    state.fallback =
      loadedLanguage === "es" ? dictionary : await fetchDictionary("es");
  } catch {
    state.fallback = dictionary;
  }

  document.documentElement.lang = loadedLanguage;
}

export function t(key, variables = {}) {
  const value = resolve(key);
  return typeof value === "string" ? interpolate(value, variables) : key;
}

export function tPlural(key, count, variables = {}) {
  const suffix = Number(count) === 1 ? "one" : "other";
  return t(`${key}.${suffix}`, { ...variables, count });
}

export function getLanguage() {
  return state.language;
}

function applyText(element, key, target) {
  const value = resolve(key);
  if (typeof value !== "string") {
    return;
  }
  const translated = interpolate(value);
  if (target === "text") {
    element.textContent = translated;
  } else {
    element.setAttribute(target, translated);
  }
}

export function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((element) => {
    applyText(element, element.dataset.i18n, "text");
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    applyText(element, element.dataset.i18nPlaceholder, "placeholder");
  });
  root.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    applyText(element, element.dataset.i18nAriaLabel, "aria-label");
  });
  root.querySelectorAll("[data-i18n-title]").forEach((element) => {
    applyText(element, element.dataset.i18nTitle, "title");
  });
}
