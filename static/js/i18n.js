/**
 * Carga y aplicación de traducciones. Los archivos viven en static/i18n/.
 * El español es el idioma de respaldo si falta una clave o un archivo.
 */

const state = {
  dictionary: {},
  fallback: {},
  language: "es",
};

function lookup(dictionary, key) {
  return key.split(".").reduce((value, part) => {
    if (value && typeof value === "object" && part in value) {
      return value[part];
    }
    return undefined;
  }, dictionary);
}

async function fetchDictionary(language) {
  const response = await fetch(`/static/i18n/${language}.json`, {
    cache: "no-cache",
  });
  if (!response.ok) {
    throw new Error(`Idioma no disponible: ${language}`);
  }
  return response.json();
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
  const value =
    lookup(state.dictionary, key) ?? lookup(state.fallback, key) ?? key;
  if (typeof value !== "string") {
    return key;
  }
  return value.replace(/\{\{(\w+)\}\}/g, (_match, name) => {
    return Object.prototype.hasOwnProperty.call(variables, name)
      ? String(variables[name])
      : "";
  });
}

export function tPlural(key, count, variables = {}) {
  const suffix = Number(count) === 1 ? "one" : "other";
  return t(`${key}.${suffix}`, { ...variables, count });
}

export function getLanguage() {
  return state.language;
}

export function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.setAttribute("placeholder", t(element.dataset.i18nPlaceholder));
  });
  root.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });
  root.querySelectorAll("[data-i18n-title]").forEach((element) => {
    element.setAttribute("title", t(element.dataset.i18nTitle));
  });
}
