(function () {
  "use strict";

  var STORAGE_KEY = "sga-theme-mode";
  var PWA_DISMISS_KEY = "sga-pwa-dismissed-until";
  var MODES = ["system", "light", "dark"];
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  var deferredInstallPrompt = null;
  var pwaReadyCallback = null;

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    if (typeof pwaReadyCallback === "function") pwaReadyCallback("android");
  });

  window.addEventListener("appinstalled", function () {
    deferredInstallPrompt = null;
    try {
      window.localStorage.setItem(PWA_DISMISS_KEY, String(Date.now() + 365 * 86400000));
    } catch (error) {}
    var banner = document.getElementById("sga-pwa-banner");
    if (banner) banner.remove();
  });

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
    initNavHoverMenus();
    initPwaInstall();
    initHubTabs();
  }

  function initNavHoverMenus() {
    var nav = document.querySelector(".primary-nav");
    if (!nav || nav.getAttribute("data-nav-wired") === "1") return;
    nav.setAttribute("data-nav-wired", "1");
    var menus = Array.prototype.slice.call(nav.querySelectorAll(".nav-menu"));
    if (!menus.length) return;
    var timers = new Map();

    function sync(menu) {
      var summary = menu.querySelector("summary");
      if (summary) summary.setAttribute("aria-expanded", menu.open ? "true" : "false");
    }

    function clearTimer(menu) {
      var t = timers.get(menu);
      if (t) {
        clearTimeout(t);
        timers.delete(menu);
      }
    }

    menus.forEach(function (menu) {
      sync(menu);
      menu.addEventListener("toggle", function () {
        sync(menu);
        if (!menu.open) return;
        menus.forEach(function (other) {
          if (other !== menu && other.open) {
            clearTimer(other);
            other.open = false;
            sync(other);
          }
        });
      });

      menu.addEventListener("pointerenter", function (e) {
        if (e.pointerType && e.pointerType !== "mouse") return;
        clearTimer(menu);
        menus.forEach(function (other) {
          if (other !== menu && other.open) {
            clearTimer(other);
            other.open = false;
            sync(other);
          }
        });
        if (!menu.open) {
          menu.open = true;
          sync(menu);
        }
      });

      menu.addEventListener("pointerleave", function (e) {
        if (e.pointerType && e.pointerType !== "mouse") return;
        clearTimer(menu);
        var t = setTimeout(function () {
          if (menu.open) {
            menu.open = false;
            sync(menu);
          }
        }, 120);
        timers.set(menu, t);
      });
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      menus.forEach(function (menu) {
        if (menu.open) {
          clearTimer(menu);
          menu.open = false;
          sync(menu);
        }
      });
    });

    document.addEventListener("pointerdown", function (event) {
      if (event.target.closest && event.target.closest(".primary-nav")) return;
      menus.forEach(function (menu) {
        if (menu.open) {
          clearTimer(menu);
          menu.open = false;
          sync(menu);
        }
      });
    });
  }

  function initPwaInstall() {
    if ("serviceWorker" in navigator) {
      var registerSw = function () {
        navigator.serviceWorker.register("/sw.js").catch(function () {});
      };
      if (document.readyState === "complete") {
        registerSw();
      } else {
        window.addEventListener("load", registerSw);
      }
    }

    if (window.location.pathname === "/offline.html") return;

    var isStandalone =
      (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true;
    if (isStandalone) return;

    function isDismissed() {
      try {
        var raw = window.localStorage.getItem(PWA_DISMISS_KEY);
        return raw ? Number(raw) > Date.now() : false;
      } catch (error) {
        return false;
      }
    }

    function setDismissed(days) {
      try {
        window.localStorage.setItem(PWA_DISMISS_KEY, String(Date.now() + days * 86400000));
      } catch (error) {}
    }

    function hideBanner() {
      var existing = document.getElementById("sga-pwa-banner");
      if (existing) existing.remove();
    }

    function showBanner(kind) {
      if (isDismissed() || !document.body || document.getElementById("sga-pwa-banner")) return;

      var banner = document.createElement("aside");
      banner.id = "sga-pwa-banner";
      banner.className = "sga-pwa-banner";
      banner.setAttribute("role", "region");
      banner.setAttribute("aria-label", "Install SG Alerts app");

      var subtitle = kind === "ios"
        ? "Tap Share (\u2191) then \u201cAdd to Home Screen\u201d for quick 1-tap access."
        : "Add SG Alerts to your home screen for 1-tap checkpoints, rain radar & parking.";

      var actionHtml = kind === "ios"
        ? ""
        : '<button type="button" class="sga-pwa-install" data-pwa-install="1">Install</button>';

      banner.innerHTML =
        '<div class="sga-pwa-main">' +
          '<img class="sga-pwa-icon" src="/assets/logo-96.webp" alt="" width="40" height="40">' +
          '<div class="sga-pwa-copy">' +
            '<strong>Install SG Alerts App</strong>' +
            '<span>' + subtitle + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="sga-pwa-actions">' +
          actionHtml +
          '<button type="button" class="sga-pwa-close" data-pwa-dismiss="1" aria-label="Dismiss install prompt">&times;</button>' +
        '</div>';

      var installBtn = banner.querySelector("[data-pwa-install]");
      if (installBtn) {
        installBtn.addEventListener("click", function () {
          if (!deferredInstallPrompt) {
            hideBanner();
            return;
          }
          var promptEvent = deferredInstallPrompt;
          deferredInstallPrompt = null;
          promptEvent.prompt();
          if (promptEvent.userChoice && typeof promptEvent.userChoice.then === "function") {
            promptEvent.userChoice.then(function (choice) {
              if (choice && choice.outcome === "accepted") {
                setDismissed(365);
              } else {
                setDismissed(14);
              }
              hideBanner();
            }).catch(function () {
              hideBanner();
            });
          } else {
            hideBanner();
          }
        });
      }

      var closeBtn = banner.querySelector("[data-pwa-dismiss]");
      if (closeBtn) {
        closeBtn.addEventListener("click", function () {
          setDismissed(14);
          hideBanner();
        });
      }

      document.body.appendChild(banner);
    }

    pwaReadyCallback = showBanner;
    if (deferredInstallPrompt) {
      showBanner("android");
      return;
    }

    var ua = window.navigator.userAgent || "";
    var isIosDevice = /iPhone|iPad|iPod/i.test(ua) || (ua.indexOf("Macintosh") !== -1 && navigator.maxTouchPoints > 1);
    if (isIosDevice && !isDismissed()) {
      window.setTimeout(function () {
        if (!deferredInstallPrompt) showBanner("ios");
      }, 1500);
    }
  }

  function initHubTabs() {
    var groups = document.querySelectorAll("[data-hub-tabs]");
    if (!groups.length) return;
    Array.prototype.forEach.call(groups, function (group) {
      if (group.getAttribute("data-hub-tabs-wired") === "1") return;
      group.setAttribute("data-hub-tabs-wired", "1");
      var tabs = Array.prototype.slice.call(group.querySelectorAll('[role="tab"]'));
      var panels = Array.prototype.slice.call(group.querySelectorAll('[role="tabpanel"]'));
      function activate(tabId) {
        tabs.forEach(function (t) {
          var active = t.getAttribute("data-tab-target") === tabId;
          t.setAttribute("aria-selected", active ? "true" : "false");
          t.tabIndex = active ? 0 : -1;
        });
        panels.forEach(function (p) {
          p.hidden = p.getAttribute("data-tab-panel") !== tabId;
        });
      }
      tabs.forEach(function (t) {
        t.addEventListener("click", function () {
          activate(t.getAttribute("data-tab-target"));
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
