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
    initFeedbackWidget();
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

  function initFeedbackWidget() {
    if (document.body && document.body.getAttribute("data-no-feedback") === "1") return;
    var headerInner = document.querySelector(".site-header .header-inner");
    var themeControl = headerInner ? headerInner.querySelector(".theme-control") : null;
    if (headerInner && !headerInner.querySelector(".sga-fb-trigger")) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sga-fb-trigger";
      btn.setAttribute("aria-label", "Send feedback");
      btn.setAttribute("title", "Help us improve SG Alerts");
      btn.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>' +
        '<span class="sga-fb-trigger-label">Feedback</span>';
      btn.addEventListener("click", openFeedbackModal);
      if (themeControl) {
        headerInner.insertBefore(btn, themeControl);
      } else {
        headerInner.appendChild(btn);
      }
    }

    var footer = document.querySelector(".site-footer");
    if (footer && !footer.querySelector(".sga-fb-footer-prompt")) {
      var bar = document.createElement("div");
      bar.className = "sga-fb-footer-prompt";
      bar.innerHTML =
        '<span>Spotted wrong data or want a new feature on SG Alerts?</span>' +
        '<button type="button" class="sga-fb-footer-btn">Send feedback \u2192</button>';
      bar.querySelector("button").addEventListener("click", openFeedbackModal);
      footer.insertBefore(bar, footer.firstChild);
    }
  }

  function openFeedbackModal() {
    var existing = document.getElementById("sga-fb-backdrop");
    if (existing) {
      existing.hidden = false;
      var ta = existing.querySelector("textarea");
      if (ta) ta.focus();
      return;
    }

    var path = window.location.pathname || "/";
    var defaultTopic = /checkpoint|travel/i.test(path) ? "checkpoints" : "feature";
    var placeholders = {
      feature: "What feature or data would make SG Alerts more useful for you?",
      bug: "Which page, rate, or number looked off?",
      checkpoints: "Spotted an AI count or camera issue? Let us know which checkpoint & time.",
      general: "Tell us what you think — we read every note.",
    };

    var backdrop = document.createElement("div");
    backdrop.id = "sga-fb-backdrop";
    backdrop.className = "sga-fb-backdrop";
    backdrop.innerHTML =
      '<div class="sga-fb-modal" role="dialog" aria-modal="true" aria-labelledby="sga-fb-title">' +
        '<div class="sga-fb-head">' +
          '<div>' +
            '<h2 id="sga-fb-title">Help us improve SG Alerts</h2>' +
            '<p>Spot wrong data or want a new feature? We read every note.</p>' +
          '</div>' +
          '<button type="button" class="sga-fb-close" aria-label="Close feedback">\u00d7</button>' +
        '</div>' +
        '<form class="sga-fb-body" novalidate>' +
          '<div class="sga-fb-section">' +
            '<span class="sga-fb-label">Topic</span>' +
            '<div class="sga-fb-topics" role="radiogroup" aria-label="Feedback topic">' +
              '<button type="button" class="sga-fb-chip" data-topic="feature" aria-checked="false">Feature request</button>' +
              '<button type="button" class="sga-fb-chip" data-topic="bug" aria-checked="false">Bug / wrong data</button>' +
              '<button type="button" class="sga-fb-chip" data-topic="checkpoints" aria-checked="false">Checkpoints / AI</button>' +
              '<button type="button" class="sga-fb-chip" data-topic="general" aria-checked="false">General</button>' +
            '</div>' +
          '</div>' +
          '<div class="sga-fb-section">' +
            '<span class="sga-fb-label">How is your experience today? <small>(optional)</small></span>' +
            '<div class="sga-fb-ratings" role="radiogroup" aria-label="Experience rating">' +
              '<button type="button" class="sga-fb-rate" data-rating="1" aria-checked="false" title="Very bad">\ud83d\ude20</button>' +
              '<button type="button" class="sga-fb-rate" data-rating="2" aria-checked="false" title="Bad">\ud83d\ude15</button>' +
              '<button type="button" class="sga-fb-rate" data-rating="3" aria-checked="false" title="Okay">\ud83d\ude10</button>' +
              '<button type="button" class="sga-fb-rate" data-rating="4" aria-checked="false" title="Good">\ud83d\ude42</button>' +
              '<button type="button" class="sga-fb-rate" data-rating="5" aria-checked="false" title="Great">\ud83e\udd29</button>' +
            '</div>' +
          '</div>' +
          '<div class="sga-fb-section">' +
            '<label class="sga-fb-label" for="sga-fb-msg">Your feedback</label>' +
            '<textarea id="sga-fb-msg" class="sga-fb-textarea" rows="4" maxlength="2000" required></textarea>' +
          '</div>' +
          '<div class="sga-fb-section">' +
            '<label class="sga-fb-label" for="sga-fb-email">Email <small>(optional, only if you want a reply)</small></label>' +
            '<input id="sga-fb-email" class="sga-fb-input" type="email" maxlength="160" placeholder="you@example.com" autocomplete="email" />' +
          '</div>' +
          '<div class="sga-fb-status" role="status" aria-live="polite"></div>' +
          '<div class="sga-fb-actions">' +
            '<span class="sga-fb-privacy">Private — only the SG Alerts team sees this.</span>' +
            '<button type="submit" class="sga-fb-submit">Send feedback</button>' +
          '</div>' +
        '</form>' +
      '</div>';

    var state = { topic: defaultTopic, rating: null };
    var form = backdrop.querySelector("form");
    var textarea = backdrop.querySelector("#sga-fb-msg");
    var emailInput = backdrop.querySelector("#sga-fb-email");
    var statusEl = backdrop.querySelector(".sga-fb-status");
    var submitBtn = backdrop.querySelector(".sga-fb-submit");
    var topicBtns = backdrop.querySelectorAll(".sga-fb-chip");
    var rateBtns = backdrop.querySelectorAll(".sga-fb-rate");

    function selectTopic(t) {
      state.topic = t;
      for (var i = 0; i < topicBtns.length; i++) {
        var active = topicBtns[i].getAttribute("data-topic") === t;
        topicBtns[i].setAttribute("aria-checked", active ? "true" : "false");
        topicBtns[i].classList.toggle("is-active", active);
      }
      textarea.placeholder = placeholders[t] || placeholders.general;
    }

    function selectRating(r) {
      state.rating = state.rating === r ? null : r;
      for (var i = 0; i < rateBtns.length; i++) {
        var active = Number(rateBtns[i].getAttribute("data-rating")) === state.rating;
        rateBtns[i].setAttribute("aria-checked", active ? "true" : "false");
        rateBtns[i].classList.toggle("is-active", active);
      }
    }

    for (var i = 0; i < topicBtns.length; i++) {
      topicBtns[i].addEventListener("click", function () {
        selectTopic(this.getAttribute("data-topic"));
      });
    }
    for (var j = 0; j < rateBtns.length; j++) {
      rateBtns[j].addEventListener("click", function () {
        selectRating(Number(this.getAttribute("data-rating")));
      });
    }
    selectTopic(defaultTopic);

    function closeModal() {
      backdrop.hidden = true;
    }

    backdrop.querySelector(".sga-fb-close").addEventListener("click", closeModal);
    backdrop.addEventListener("click", function (ev) {
      if (ev.target === backdrop) closeModal();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !backdrop.hidden) closeModal();
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var msg = (textarea.value || "").trim();
      if (msg.length < 3) {
        statusEl.textContent = "Please write a quick note (at least 3 characters).";
        statusEl.className = "sga-fb-status is-error";
        textarea.focus();
        return;
      }
      submitBtn.disabled = true;
      submitBtn.textContent = "Sending...";
      statusEl.textContent = "";
      statusEl.className = "sga-fb-status";

      var payload = {
        topic: state.topic,
        rating: state.rating,
        message: msg,
        email: (emailInput.value || "").trim(),
        page: window.location.pathname + (window.location.search || ""),
        viewport: window.innerWidth <= 640 ? "mobile (" + window.innerWidth + "px)" : "desktop (" + window.innerWidth + "px)",
      };

      fetch("https://sgalerts.com/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok && data && data.ok, error: data && data.error };
          });
        })
        .then(function (result) {
          if (!result.ok) {
            throw new Error(result.error || "Could not send feedback right now.");
          }
          textarea.value = "";
          emailInput.value = "";
          selectRating(state.rating);
          statusEl.textContent = "Thanks! We\u2019ve received your feedback.";
          statusEl.className = "sga-fb-status is-ok";
          submitBtn.textContent = "Sent \u2713";
          window.setTimeout(function () {
            closeModal();
            submitBtn.disabled = false;
            submitBtn.textContent = "Send feedback";
            statusEl.textContent = "";
          }, 1600);
        })
        .catch(function (err) {
          statusEl.textContent = err && err.message ? err.message : "Network error. Please try again.";
          statusEl.className = "sga-fb-status is-error";
          submitBtn.disabled = false;
          submitBtn.textContent = "Send feedback";
        });
    });

    document.body.appendChild(backdrop);
    textarea.focus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
