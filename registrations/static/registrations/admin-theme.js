"use strict";

(() => {
  const modes = new Set(["light", "dark", "auto"]);
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = "auto";
  try {
    const stored = window.localStorage.getItem("theme");
    if (modes.has(stored)) preference = stored;
  } catch (_) {
    // The switch still works for this page when browser storage is unavailable.
  }

  function applyTheme(mode, persist = false) {
    preference = modes.has(mode) ? mode : "auto";
    document.documentElement.dataset.theme = preference === "auto"
      ? (systemTheme.matches ? "dark" : "light")
      : preference;
    document.querySelectorAll("[data-admin-theme]").forEach((control) => {
      control.value = preference;
    });
    if (persist) {
      try {
        window.localStorage.setItem("theme", preference);
      } catch (_) {
        // Keep the page usable in private or restricted browser contexts.
      }
    }
  }

  // Run in the head so a saved dark theme does not flash a light background.
  applyTheme(preference);
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-admin-theme]").forEach((control) => {
      control.value = preference;
      control.addEventListener("change", () => applyTheme(control.value, true));
    });
  });
  systemTheme.addEventListener("change", () => {
    if (preference === "auto") applyTheme("auto");
  });
  window.addEventListener("storage", (event) => {
    if (event.key === "theme" || event.key === null) applyTheme(event.newValue);
  });
})();
