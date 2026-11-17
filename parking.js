(function () {
  const AVAILABILITY_URL = "https://api.data.gov.sg/v1/transport/carpark-availability";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));

  let dataset = null;
  let liveMap = {};
  let liveTimestamp = "";
  let vehicleMode = "motorcycle"; // "motorcycle" | "car"
  let activeFilters = new Set();
  let userLocation = null;
  let map = null;
  let tileLayer = null;
  let markerLayer = null;
  let canvasRenderer = null;

  const params = new URLSearchParams(window.location.search);
  if (params.get("mode") === "car") vehicleMode = "car";
  if (params.get("free") === "true") activeFilters.add("free");

  function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function tileUrlForTheme() {
    return "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  }

  function initMap() {
    const el = document.getElementById("parkingMap");
    if (!el || typeof window.L === "undefined" || map) return;
    map = L.map(el, { preferCanvas: true }).setView([1.3521, 103.8198], 12);
    canvasRenderer = L.canvas({ padding: 0.4 });
    tileLayer = L.tileLayer(tileUrlForTheme(), {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
  }

  function estimateCost(cp) {
    const dayEl = document.getElementById("parkingDayType");
    const hrsEl = document.getElementById("parkingDuration");
    const day = dayEl ? dayEl.value : "weekday";
    const hours = Number(hrsEl ? hrsEl.value : 2);

    if (vehicleMode === "motorcycle") {
      if (cp.free_bike) return "Free / Grace check";
      if (day === "sun_ph" && cp.free_sun_ph) return "Free (Sun & PH 7am–10:30pm)";
      if (cp.source_type === "Commercial reference") return cp.bike_rate;
      return hours >= 10 ? "$0.65 day + $0.65 night" : "$0.65 / session";
    }

    if (day === "sun_ph" && cp.free_sun_ph) return "Free (Sun & PH 7am–10:30pm)";
    if (cp.source_type === "Commercial reference") return cp.car_rate;
    if (hours === 10) return cp.night_parking ? "$5.00 max overnight cap" : "No overnight parking";
    const halfHours = Math.max(1, Math.ceil(hours * 2));
    const unit = cp.area_tier === "central" ? 1.2 : 0.6;
    return `$${(halfHours * unit).toFixed(2)} est. (${hours}h HDB)`;
  }

  function getLotInfo(cp) {
    const mergedLive = liveMap[cp.id] || cp.live || {};
    if (vehicleMode === "motorcycle") {
      if (mergedLive.Y) return { type: "Y", avail: mergedLive.Y.avail, total: mergedLive.Y.total };
      if (mergedLive.C) return { type: "C_fallback", avail: mergedLive.C.avail, total: mergedLive.C.total };
      return null;
    }
    if (mergedLive.C) return { type: "C", avail: mergedLive.C.avail, total: mergedLive.C.total };
    return null;
  }

  function lotPillHtml(cp, lotInfo) {
    if (vehicleMode === "motorcycle" && cp.free_bike) {
      return '<span class="lot-pill is-free is-plenty">Free / Rider Spot</span>';
    }
    if (!lotInfo) {
      return `<span class="lot-pill is-ref">${cp.free_sun_ph ? "Free Sun/PH" : esc(cp.source_type === "Commercial reference" ? "Mall / Hub" : "HDB")}</span>`;
    }
    if (lotInfo.type === "C_fallback") {
      return `<span class="lot-pill is-ref">${lotInfo.avail} Car lots</span>`;
    }
    const cls = lotInfo.avail >= 25 ? "is-plenty" : lotInfo.avail >= 5 ? "is-limited" : "is-full";
    const label = vehicleMode === "motorcycle" ? "bike lots" : "lots";
    return `<span class="lot-pill ${cls}">${lotInfo.avail} / ${lotInfo.total} ${label}</span>`;
  }

  function filterCarparks() {
    if (!dataset) return [];
    const q = (document.getElementById("parkingSearch")?.value || "").trim().toLowerCase();
    const list = dataset.carparks.filter((cp) => {
      if (q) {
        const hay = `${cp.id} ${cp.name} ${cp.address} ${cp.type}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (activeFilters.has("free")) {
        if (!(cp.free_sun_ph || cp.free_bike)) return false;
      }
      if (activeFilters.has("live")) {
        const l = getLotInfo(cp);
        if (vehicleMode === "motorcycle" && (!l || l.type !== "Y" || l.avail <= 0)) return false;
        if (vehicleMode === "car" && (!l || l.avail <= 0)) return false;
      }
      if (activeFilters.has("sheltered") && !cp.sheltered) return false;
      if (activeFilters.has("central") && cp.area_tier !== "central") return false;
      if (activeFilters.has("night") && !cp.night_parking) return false;
      if (activeFilters.has("high_gantry") && (!cp.gantry_height || cp.gantry_height < 2.1)) return false;
      return true;
    });

    const enriched = list.map((cp) => {
      const lotInfo = getLotInfo(cp);
      const dist = userLocation ? haversineKm(userLocation.lat, userLocation.lng, cp.lat, cp.lng) : null;
      return { cp, lotInfo, dist };
    });

    enriched.sort((a, b) => {
      if (userLocation && a.dist !== null && b.dist !== null) return a.dist - b.dist;
      if (vehicleMode === "motorcycle") {
        const aScore = (a.cp.free_bike ? 3 : 0) + (a.lotInfo?.type === "Y" ? 2 : 0) + (a.cp.free_sun_ph ? 1 : 0);
        const bScore = (b.cp.free_bike ? 3 : 0) + (b.lotInfo?.type === "Y" ? 2 : 0) + (b.cp.free_sun_ph ? 1 : 0);
        if (bScore !== aScore) return bScore - aScore;
      } else {
        const aAvail = a.lotInfo ? a.lotInfo.avail : -1;
        const bAvail = b.lotInfo ? b.lotInfo.avail : -1;
        if ((b.cp.source_type === "Commercial reference") !== (a.cp.source_type === "Commercial reference") && !a.lotInfo && !b.lotInfo) {
          return a.cp.source_type === "Commercial reference" ? -1 : 1;
        }
        if (bAvail !== aAvail) return bAvail - aAvail;
      }
      return a.cp.name.localeCompare(b.cp.name);
    });

    return enriched;
  }

  function renderSummary(filtered) {
    const el = document.getElementById("parkingSummary");
    if (!el || !dataset) return;
    let liveLots = 0;
    let feedCount = 0;
    let freeCount = 0;
    for (const { cp, lotInfo } of filtered) {
      if (cp.free_sun_ph || cp.free_bike) freeCount += 1;
      if (vehicleMode === "motorcycle") {
        if (lotInfo && lotInfo.type === "Y") {
          liveLots += lotInfo.avail;
          feedCount += 1;
        }
      } else if (lotInfo && lotInfo.type === "C") {
        liveLots += lotInfo.avail;
        feedCount += 1;
      }
    }
    const stamp = liveTimestamp ? new Date(liveTimestamp).toLocaleTimeString("en-SG", { hour: "numeric", minute: "2-digit" }) : "Snapshot";
    el.innerHTML = `
      <div class="parking-stat"><small>Matching Carparks</small><strong>${filtered.length.toLocaleString()}</strong></div>
      <div class="parking-stat"><small>${vehicleMode === "motorcycle" ? "Live Bike Lots (Y)" : "Live Car Lots (C)"}</small><strong>${liveLots.toLocaleString()}</strong><span style="font-size:0.75rem;color:var(--muted);">across ${feedCount} tracked feeds</span></div>
      <div class="parking-stat"><small>Free Sun &amp; PH</small><strong>${freeCount.toLocaleString()}</strong></div>
      <div class="parking-stat"><small>LTA Live Feed</small><strong>${esc(stamp)}</strong></div>
    `;
  }

  function renderFilterChips() {
    const wrap = document.getElementById("parkingFilterChips");
    if (!wrap) return;
    const chips = vehicleMode === "motorcycle"
      ? [
          ["free", "Free Sun & PH / Rider Free"],
          ["live", "Live Bike Lots (Y)"],
          ["sheltered", "Sheltered MSCP"],
          ["central", "Central / Town"],
        ]
      : [
          ["free", "Free Sun & PH"],
          ["live", "Live Car Lots Available"],
          ["sheltered", "Sheltered MSCP / Basement"],
          ["night", "Overnight ($5 Cap)"],
          ["high_gantry", "High Gantry (>=2.1m)"],
          ["central", "Central Area"],
        ];

    wrap.innerHTML = chips.map(([id, label]) =>
      `<button type="button" class="filter-pill" data-filter="${id}" aria-pressed="${activeFilters.has(id) ? "true" : "false"}">${label}</button>`
    ).join("");

    wrap.querySelectorAll("button[data-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const f = btn.getAttribute("data-filter");
        if (activeFilters.has(f)) activeFilters.delete(f);
        else activeFilters.add(f);
        renderAll();
      });
    });
  }

  function updateMapMarkers(items) {
    if (!map || !markerLayer) return;
    markerLayer.clearLayers();
    const subset = items.slice(0, 320);
    for (const { cp, lotInfo } of subset) {
      let color = "#3b82f6";
      if (vehicleMode === "motorcycle" && cp.free_bike) color = "#10b981";
      else if (lotInfo && (vehicleMode === "car" || lotInfo.type === "Y")) {
        color = lotInfo.avail >= 25 ? "#10b981" : lotInfo.avail >= 5 ? "#f59e0b" : "#ef4444";
      } else if (cp.free_sun_ph) {
        color = "#14b8a6";
      }
      const m = L.circleMarker([cp.lat, cp.lng], {
        renderer: canvasRenderer,
        radius: 6,
        color,
        weight: 1.5,
        fillColor: color,
        fillOpacity: 0.78,
      });
      const lotText = lotInfo ? `${lotInfo.avail} / ${lotInfo.total} ${lotInfo.type === "Y" ? "bike" : "car"} lots` : esc(cp.type);
      m.bindPopup(`
        <strong>${esc(cp.name)}</strong> (${esc(cp.id)})<br>
        <span>${lotText}</span><br>
        <span>Est: ${esc(estimateCost(cp))}</span><br>
        <a href="https://www.google.com/maps/search/?api=1&query=${cp.lat},${cp.lng}" target="_blank" rel="noopener noreferrer">Open in Google Maps →</a>
      `);
      m.addTo(markerLayer);
    }
    if (userLocation) {
      L.circleMarker([userLocation.lat, userLocation.lng], {
        renderer: canvasRenderer,
        radius: 8,
        color: "#ffffff",
        weight: 2,
        fillColor: "#2563eb",
        fillOpacity: 1,
      }).bindPopup("Your current location").addTo(markerLayer);
    }
  }

  function renderCards(items) {
    const grid = document.getElementById("parkingResults");
    const countNote = document.getElementById("parkingResultNote");
    if (!grid) return;

    const shown = items.slice(0, 60);
    if (countNote) {
      countNote.textContent = items.length
        ? `Showing ${shown.length} of ${items.length.toLocaleString()} matching carparks (top ${Math.min(items.length, 320)} plotted on map).`
        : "No carparks match those filters. Try clearing a filter or broadening your search.";
    }

    grid.innerHTML = shown.map(({ cp, lotInfo, dist }) => `
      <article class="parking-card">
        <div class="parking-card-top">
          <div>
            <span class="parking-code">${esc(cp.id)} · ${esc(cp.area_tier === "central" ? "Central Area" : "Heartlands / Islandwide")}</span>
            <h3 class="parking-card-title">${esc(cp.name)}</h3>
          </div>
          ${lotPillHtml(cp, lotInfo)}
        </div>
        <div class="parking-meta-tags">
          ${cp.free_sun_ph ? '<span class="parking-tag is-free">Free Sun &amp; PH</span>' : ""}
          ${cp.free_bike ? '<span class="parking-tag is-free">Free / Grace Bike</span>' : ""}
          ${cp.sheltered ? '<span class="parking-tag">Sheltered</span>' : '<span class="parking-tag">Open / Surface</span>'}
          ${cp.night_parking ? '<span class="parking-tag">Night Parking</span>' : ""}
          ${cp.gantry_height > 0 ? `<span class="parking-tag">Gantry ${cp.gantry_height}m</span>` : ""}
          ${dist !== null ? `<span class="parking-tag">${dist.toFixed(1)} km away</span>` : ""}
        </div>
        <div style="font-size:0.84rem;color:var(--muted);">${esc(vehicleMode === "motorcycle" ? cp.bike_rate : cp.car_rate)}</div>
        <div class="parking-card-footer">
          <strong>${esc(estimateCost(cp))}</strong>
          <span class="parking-card-actions">
            <button type="button" data-focus-lat="${cp.lat}" data-focus-lng="${cp.lng}">Map</button>
            <a href="https://www.google.com/maps/search/?api=1&query=${cp.lat},${cp.lng}" target="_blank" rel="noopener noreferrer">Navigate →</a>
          </span>
        </div>
      </article>
    `).join("");

    grid.querySelectorAll("button[data-focus-lat]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!map) return;
        const lat = Number(btn.getAttribute("data-focus-lat"));
        const lng = Number(btn.getAttribute("data-focus-lng"));
        map.setView([lat, lng], 17, { animate: true });
        document.getElementById("parkingMap")?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
  }

  function renderAll() {
    renderFilterChips();
    const filtered = filterCarparks();
    renderSummary(filtered);
    updateMapMarkers(filtered);
    renderCards(filtered);
  }

  async function refreshLiveLots() {
    try {
      const res = await fetch(AVAILABILITY_URL, { cache: "no-store" });
      if (!res.ok) return;
      const json = await res.json();
      const item = json?.items?.[0];
      if (!item) return;
      liveTimestamp = item.timestamp || "";
      const next = {};
      for (const entry of item.carpark_data || []) {
        const lots = {};
        for (const info of entry.carpark_info || []) {
          if (info.lot_type) {
            lots[info.lot_type] = { avail: Number(info.lots_available || 0), total: Number(info.total_lots || 0) };
          }
        }
        next[String(entry.carpark_number || "").toUpperCase()] = lots;
      }
      liveMap = next;
      renderAll();
    } catch {}
  }

  function wireControls() {
    document.querySelectorAll(".parking-tab[data-mode]").forEach((tab) => {
      tab.setAttribute("aria-selected", tab.getAttribute("data-mode") === vehicleMode ? "true" : "false");
      tab.addEventListener("click", () => {
        vehicleMode = tab.getAttribute("data-mode");
        document.querySelectorAll(".parking-tab[data-mode]").forEach((t) => {
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });
        activeFilters.clear();
        renderAll();
      });
    });

    ["parkingSearch", "parkingDayType", "parkingDuration"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", renderAll);
      document.getElementById(id)?.addEventListener("change", renderAll);
    });

    document.getElementById("parkingRefreshBtn")?.addEventListener("click", refreshLiveLots);

    document.getElementById("parkingGeoBtn")?.addEventListener("click", () => {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition((pos) => {
        userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        if (map) map.setView([userLocation.lat, userLocation.lng], 15);
        renderAll();
      });
    });
  }

  async function init() {
    initMap();
    wireControls();
    try {
      dataset = await fetch("./data/carparks.json").then((r) => r.json());
      liveTimestamp = dataset.last_updated || "";
      renderAll();
      refreshLiveLots();
    } catch (err) {
      console.error("Failed to load carparks.json", err);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
