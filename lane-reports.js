(function () {
  "use strict";

  var API_URL = "/api/lane-reports";

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatSgtTime(tsMs) {
    if (!tsMs) return "No reports yet today";
    try {
      var d = new Date(tsMs);
      var timeStr = d.toLocaleTimeString("en-SG", {
        timeZone: "Asia/Singapore",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      });
      var minsAgo = Math.max(0, Math.round((Date.now() - tsMs) / 60000));
      var rel = minsAgo < 1 ? "just now" : minsAgo < 60 ? minsAgo + "m ago" : Math.floor(minsAgo / 60) + "h " + (minsAgo % 60) + "m ago";
      return timeStr + " (" + rel + ")";
    } catch (e) {
      return "Updated today";
    }
  }

  function renderLaneCard(laneId, lane) {
    var recent = lane.recent_90m || { fc: 0, nfc: 0, total: 0, fc_pct: 0, nfc_pct: 0 };
    var today = lane.today || { fc: 0, nfc: 0, total: 0, fc_pct: 0, nfc_pct: 0 };
    var activeStats = recent.total > 0 ? recent : today;
    var windowLabel = recent.total > 0 ? "Last 90 mins" : today.total > 0 ? "Earlier today" : "Today";

    var badgeClass = "lr-badge lr-badge-none";
    var badgeText = "No reports yet";
    if (activeStats.total > 0) {
      if (activeStats.fc > activeStats.nfc) {
        badgeClass = "lr-badge lr-badge-fc";
        badgeText = activeStats.fc_pct + "% Check (" + lane.fcCode + ")";
      } else if (activeStats.nfc > activeStats.fc) {
        badgeClass = "lr-badge lr-badge-nfc";
        badgeText = activeStats.nfc_pct + "% No Check (" + lane.nfcCode + ")";
      } else {
        badgeClass = "lr-badge lr-badge-split";
        badgeText = "50 / 50 Split";
      }
    }

    var nfcWidth = activeStats.total > 0 ? activeStats.nfc_pct : 0;
    var fcWidth = activeStats.total > 0 ? activeStats.fc_pct : 0;
    var latestHtml = lane.latest
      ? "Latest: <strong>" + escapeHtml(lane.latest.code) + "</strong> · " + escapeHtml(formatSgtTime(lane.latest.ts))
      : "No reports yet today · Be the first to update safely";

    return (
      '<article class="lr-card" data-lane="' + escapeHtml(laneId) + '">' +
        '<div class="lr-card-head">' +
          '<div>' +
            '<h3 class="lr-lane-title">' + escapeHtml(lane.label) + '</h3>' +
            '<span class="lr-zone-tag">' + escapeHtml(lane.zone) + '</span>' +
          '</div>' +
          '<span class="' + badgeClass + '">' + escapeHtml(badgeText) + '</span>' +
        '</div>' +

        '<div class="lr-meter-wrap" aria-label="Anonymous vote distribution">' +
          '<div class="lr-meter-bar">' +
            '<span class="lr-meter-nfc" style="width:' + nfcWidth + '%"></span>' +
            '<span class="lr-meter-fc" style="width:' + fcWidth + '%"></span>' +
          '</div>' +
          '<div class="lr-meter-meta">' +
            '<span>' + escapeHtml(windowLabel) + ': <strong>' + activeStats.total + '</strong> ' + (activeStats.total === 1 ? 'vote' : 'votes') + '</span>' +
            '<span>' + escapeHtml(lane.nfcCode) + ' ' + activeStats.nfc_pct + '% · ' + escapeHtml(lane.fcCode) + ' ' + activeStats.fc_pct + '%</span>' +
          '</div>' +
        '</div>' +

        '<p class="lr-latest">' + latestHtml + '</p>' +

        '<details class="lr-breakdown">' +
          '<summary>View vote breakdown (' + today.total + ' today)</summary>' +
          '<div class="lr-breakdown-grid">' +
            '<div><span>Last 90 mins</span><strong>' + recent.nfc + ' ' + escapeHtml(lane.nfcCode) + ' · ' + recent.fc + ' ' + escapeHtml(lane.fcCode) + '</strong></div>' +
            '<div><span>Today total</span><strong>' + today.nfc + ' ' + escapeHtml(lane.nfcCode) + ' · ' + today.fc + ' ' + escapeHtml(lane.fcCode) + '</strong></div>' +
          '</div>' +
        '</details>' +

        '<div class="lr-actions">' +
          '<button type="button" class="lr-btn lr-btn-nfc" data-report-code="' + escapeHtml(lane.nfcCode) + '">' +
            '<span>No Check</span><kbd>' + escapeHtml(lane.nfcCode) + '</kbd>' +
          '</button>' +
          '<button type="button" class="lr-btn lr-btn-fc" data-report-code="' + escapeHtml(lane.fcCode) + '">' +
            '<span>Fuel Check</span><kbd>' + escapeHtml(lane.fcCode) + '</kbd>' +
          '</button>' +
        '</div>' +
      '</article>'
    );
  }

  function renderBoard(section, data, message, isError) {
    var scope = section.getAttribute("data-lane-reports") || "all";
    var laneIds = scope === "woodlands" ? ["WL", "WR"] : scope === "tuas" ? ["TL", "TR"] : ["WL", "WR", "TL", "TR"];
    var lanes = (data && data.lanes) || {};
    var dateLabel = (data && data.date_sgt) ? data.date_sgt : "Today";

    var title = scope === "woodlands"
      ? "Woodlands Live Lane Reports (Today)"
      : scope === "tuas"
        ? "Tuas Live Lane Reports (Today)"
        : "Woodlands & Tuas Live Lane Reports (Today)";

    var cardsHtml = laneIds
      .filter(function (id) { return lanes[id]; })
      .map(function (id) { return renderLaneCard(id, lanes[id]); })
      .join("");

    var toastHtml = message
      ? '<div class="lr-toast ' + (isError ? 'lr-toast-err' : 'lr-toast-ok') + '" role="status">' + escapeHtml(message) + '</div>'
      : "";

    section.innerHTML =
      '<div class="lr-header">' +
        '<div>' +
          '<p class="eyebrow">Anonymous Community Reports · ' + escapeHtml(dateLabel) + ' · Resets 00:00 SGT</p>' +
          '<h2>' + escapeHtml(title) + '</h2>' +
          '<p class="lr-sub">Tap a button only when safe &amp; stationary. 100% anonymous — no login, no history stored past midnight SGT.</p>' +
        '</div>' +
        '<button type="button" class="lr-refresh-btn" data-lr-refresh="1">Refresh</button>' +
      '</div>' +
      toastHtml +
      '<div class="lr-grid lr-grid-' + laneIds.length + '">' + cardsHtml + '</div>' +
      '<div class="lr-footer-note">' +
        '<details class="lr-legend">' +
          '<summary>Legend (Zones &amp; Abbreviations)</summary>' +
          '<p><strong>Woodlands:</strong> Zones 1 &amp; 2 = Right (<code>WRFC</code> / <code>WRNFC</code>) · Zones 3 &amp; 4 = Left (<code>WLFC</code> / <code>WLNFC</code>). ' +
          '<strong>Tuas:</strong> D1 = Right (<code>TRFC</code> / <code>TRNFC</code>) · D2 = Left (<code>TLFC</code> / <code>TLNFC</code>). ' +
          '<code>FC</code> = Fuel Check reported, <code>NFC</code> = No Fuel Check reported.</p>' +
        '</details>' +
        '<p class="lr-compliance">For situational awareness only. Reminder: Singapore Customs enforces the mandatory <strong>3/4-tank rule</strong> across all Woodlands &amp; Tuas departure lanes — always keep at least 3/4 tank before exiting Singapore.</p>' +
      '</div>';

    var refreshBtn = section.querySelector("[data-lr-refresh]");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", function () {
        loadBoard(section, "Refreshed live lane reports.");
      });
    }

    var buttons = section.querySelectorAll("[data-report-code]");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        var code = btn.getAttribute("data-report-code");
        if (!code) return;
        btn.disabled = true;
        fetch(API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: code }),
        })
          .then(function (res) {
            return res.json().then(function (json) {
              return { status: res.status, json: json };
            });
          })
          .then(function (result) {
            if (result.status === 200 && result.json && result.json.ok) {
              renderBoard(section, result.json, "Recorded " + code + " anonymously — thank you for updating safely!", false);
            } else if (result.status === 429 && result.json) {
              renderBoard(section, result.json, result.json.error || "Please wait 10 minutes before updating this lane again.", true);
            } else {
              renderBoard(section, data, (result.json && result.json.error) || "Could not submit report right now.", true);
            }
          })
          .catch(function () {
            renderBoard(section, data, "Network error — please try again when connected.", true);
          });
      });
    });
  }

  function loadBoard(section, notice) {
    fetch(API_URL, { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        renderBoard(section, data, notice || "", false);
      })
      .catch(function () {
        section.innerHTML =
          '<div class="lr-header"><div><p class="eyebrow">Anonymous Community Reports</p><h2>Live Lane Reports</h2><p class="lr-sub">Unable to load live reports right now. Please refresh shortly.</p></div></div>';
      });
  }

  function init() {
    var sections = document.querySelectorAll("[data-lane-reports]");
    if (!sections.length) return;
    Array.prototype.forEach.call(sections, function (section) {
      section.innerHTML =
        '<div class="lr-header"><div><p class="eyebrow">Anonymous Community Reports</p><h2>Loading today\u2019s lane reports\u2026</h2></div></div>';
      loadBoard(section, "");
    });
    window.setInterval(function () {
      if (document.hidden) return;
      Array.prototype.forEach.call(sections, function (section) {
        loadBoard(section, "");
      });
    }, 60000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
