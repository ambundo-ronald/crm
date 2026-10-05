/* global document, window, localStorage */
(() => {
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = "system";
  try {
    preference = localStorage.getItem("theme") || "system";
  } catch {
    /* Storage may be unavailable. */
  }
  function apply() {
    if (!["light", "dark", "system"].includes(preference))
      preference = "system";
    document.documentElement.dataset.theme =
      preference === "system"
        ? system.matches
          ? "dark"
          : "light"
        : preference;
    const control = document.getElementById("agent-theme");
    if (control) control.value = preference;
  }
  apply();
  system.addEventListener("change", apply);
  window.addEventListener("storage", (event) => {
    if (event.key === "theme" || event.key === null) {
      preference = event.newValue || "system";
      apply();
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document
      .getElementById("agent-theme")
      .addEventListener("change", (event) => {
        preference = event.target.value;
        try {
          localStorage.setItem("theme", preference);
        } catch {
          /* Retain the choice for this page. */
        }
        apply();
      });
  });
})();
