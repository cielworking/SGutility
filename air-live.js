"use strict";

(() => {
  const root = document.querySelector("[data-air-live]");
  if (!root) return;

  const API = "https://api-open.data.gov.sg/v2/real-time/api/";
  const REGIONS = ["north", "south", "east", "west", "central"];
  const PSI_BANDS = [
    [50, "Good", "good"],
    [100, "Moderate", "moderate"],
    [200, "Unhealthy", "unhealthy"],
    [300, "Very unhealthy", "unhealthy"],
    [Infinity, "Hazardous", "unhealthy"]
  ];

  let busy = false;

  const format = value => {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "Unavailable";
    return new Intl.DateTimeFormat("en-SG", {
      timeZone: "Asia/Singapore",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
      hour12: true
    }).format(date) + " UTC+08";
  };

  const updatedLabel = value => {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return null;
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Singapore",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
      hour12: true
    }).formatToParts(date);
    const part = type => parts.find(item => item.type === type)?.value || "";
    const hour = String(Number(part("hour")));
    const minute = part("minute");
    const dayPeriod = part("dayPeriod").toLowerCase();
    if (!part("day") || !part("month") || !hour || !minute || !dayPeriod) return null;
    return `Updated ${part("day")} ${part("month")}, ${hour}:${minute} ${dayPeriod} UTC+08`;
  };

  const category = value => {
    const band = PSI_BANDS.find(([ceiling]) => value <= ceiling);
    return { label: band[1], tone: band[2] };
  };

  const readNumber = (value, region) => {
    const number = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(number) || number < 0 || number > 500) {
      throw new Error(`Invalid reading for ${region}`);
    }
    return number;
  };

  async function fetchMetric(metric) {
    const endpoint = metric === "psi" ? "psi" : "pm25";
    const field = metric === "psi" ? "psi_twenty_four_hourly" : "pm25_one_hourly";
    const response = await fetch(`${API}${endpoint}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(9000)
    });
    if (!response.ok) throw new Error(`NEA returned ${response.status}`);
    const payload = await response.json();
    if (payload.code !== 0) throw new Error("NEA source unavailable");
    const item = payload.data?.items?.[0];
    if (!item) throw new Error("NEA returned no current reading");
    const timestamp = item.timestamp;
    const parsed = Date.parse(timestamp);
    if (!Number.isFinite(parsed) || parsed > Date.now() + 15 * 60000) {
      throw new Error("NEA returned an invalid timestamp");
    }
    const readings = item.readings?.[field];
    if (!readings) throw new Error("NEA returned no regional readings");
    const values = {};
    for (const region of REGIONS) values[region] = readNumber(readings[region], region);
    return { timestamp, values };
  }

  function apply(metric, payload) {
    root.querySelectorAll("[data-air-region]").forEach(tile => {
      const region = tile.dataset.airRegion;
      const value = payload.values[region];
      if (metric === "psi") {
        const output = tile.querySelector("[data-air-psi-value]");
        const categoryNode = tile.querySelector("[data-air-category]");
        if (output) output.textContent = String(value);
        if (categoryNode) {
          const band = category(value);
          categoryNode.textContent = band.label;
          categoryNode.classList.remove("good", "moderate", "unhealthy");
          categoryNode.classList.add(band.tone);
        }
      } else {
        const output = tile.querySelector("[data-air-pm25-value]");
        if (output) output.textContent = String(value);
      }
    });

    const reported = root.querySelector(`[data-air-reported="${metric}"] [data-air-reported-time]`);
    if (reported) reported.textContent = format(payload.timestamp);

    const status = root.querySelector(`[data-air-status="${metric}"]`);
    if (status) {
      status.dataset.stamp = payload.timestamp;
      status.dataset.ok = "true";
      status.dataset.live = "true";
      status.classList.remove("is-stale");
    }

    if (metric === "psi") {
      const chip = document.querySelector("#weather-freshness .freshness-time");
      const label = updatedLabel(payload.timestamp);
      if (chip && label) chip.textContent = label;
    }
  }

  function feedback(psiOk, pmOk) {
    const node = document.querySelector("[data-air-feedback]");
    if (!node) return;
    if (psiOk && pmOk) {
      node.textContent = "Live PSI and PM2.5 loaded from NEA. Checked " + format(new Date().toISOString()) + ".";
    } else if (psiOk) {
      node.textContent = "Live PSI loaded; PM2.5 could not refresh. The saved PM2.5 reading remains visible.";
    } else if (pmOk) {
      node.textContent = "Live PM2.5 loaded; PSI could not refresh. The saved PSI reading remains visible.";
    } else {
      node.textContent = "Live NEA check failed — saved readings remain visible. Check the official source for the latest.";
    }
  }

  async function refresh(manual = false) {
    if (busy) return;
    busy = true;
    const button = document.querySelector("[data-refresh-air]");
    const node = document.querySelector("[data-air-feedback]");
    if (button) button.disabled = true;
    if (node) node.textContent = "Checking live NEA readings…";

    const [psi, pm] = await Promise.allSettled([fetchMetric("psi"), fetchMetric("pm25")]);
    const psiOk = psi.status === "fulfilled";
    const pmOk = pm.status === "fulfilled";
    if (psiOk) apply("psi", psi.value);
    if (pmOk) apply("pm25", pm.value);
    if (typeof window.updateWeatherFreshness === "function") window.updateWeatherFreshness();
    feedback(psiOk, pmOk);
    if (manual && button) button.focus({ preventScroll: true });
    if (button) button.disabled = false;
    busy = false;
  }

  window.SGAlertsAirLive = { refresh };
  refresh(false);
})();
