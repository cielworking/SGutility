(function () {
  "use strict";

  var STORAGE_KEY = "sga-theme-mode";
  var MODES = ["system", "light", "dark"];
  var media = window.matchMedia("(prefers-color-scheme: dark)");

  function readMode() {
    try {
      var stored = window.localStorage.getItem(STORAGE_KEY);
      return MODES.indexOf(stored) !== -1 ? stored : "system";
    } catch (error) {
      return "system";
    }
  }

  function effectiveTheme(mode) {
    return mode === "dark" || (mode === "system" && media.matches) ? "dark" : "light";
  }

  function updateMeta(theme, mode) {
    var lightMeta = document.querySelector('meta[name="theme-color"][content="#0c2554"]');
    var darkMeta = document.querySelector('meta[name="theme-color"][content="#0b1220"]');
    if (!lightMeta || !darkMeta) return;
    if (mode === "system") {
      lightMeta.setAttribute("media", "(prefers-color-scheme: light)");
      darkMeta.setAttribute("media", "(prefers-color-scheme: dark)");
    } else if (theme === "dark") {
      lightMeta.setAttribute("media", "not all");
      darkMeta.setAttribute("media", "all");
    } else {
      lightMeta.setAttribute("media", "all");
      darkMeta.setAttribute("media", "not all");
    }
  }

  function paint(mode) {
    var theme = effectiveTheme(mode);
    var root = document.documentElement;
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-theme-mode", mode);
    root.style.colorScheme = theme;
    updateMeta(theme, mode);
    var choices = document.querySelectorAll("[data-theme-choice]");
    for (var index = 0; index < choices.length; index++) {
      var choice = choices[index];
      choice.setAttribute("aria-pressed", choice.getAttribute("data-theme-choice") === mode ? "true" : "false");
    }
  }

  function setMode(mode, persist) {
    if (MODES.indexOf(mode) === -1) mode = "system";
    if (persist) {
      try {
        window.localStorage.setItem(STORAGE_KEY, mode);
      } catch (error) {
        /* Storage can be unavailable in private modes; the choice still applies for this page. */
      }
    }
    paint(mode);
  }

  function init() {
    paint(readMode());
    var choices = document.querySelectorAll("[data-theme-choice]");
    for (var index = 0; index < choices.length; index++) {
      choices[index].addEventListener("click", function () {
        setMode(this.getAttribute("data-theme-choice"), true);
      });
    }
    var onSystemChange = function () {
      if (readMode() === "system") paint("system");
    };
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", onSystemChange);
    } else if (typeof media.addListener === "function") {
      media.addListener(onSystemChange);
    }
    window.addEventListener("storage", function (event) {
      if (event.key === STORAGE_KEY) paint(readMode());
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
