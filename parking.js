(function () {
  const AVAILABILITY_URL = "https://api.data.gov.sg/v1/transport/carpark-availability";
  const ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));

  let dataset = null;
  let liveMap = {};
  let liveTimestamp = "";
  let vehicleMode = "motorcycle"; // "motorcycle" | "car"
  let activeFilters = new Set();
  let userLocation = null;
  let searchedLocation = null; // OneMap resolved point from postal code / address / landmark
  let searchDebounce = null;
  let lastGeocodedQuery = "";
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

  function initMap() {
    const el = document.getElementById("parkingMap");
    if (!el || typeof window.L === "undefined" || map) return;
    map = L.map(el, { preferCanvas: true }).setView([1.3521, 103.8198], 12);
    canvasRenderer = L.canvas({ padding: 0.4 });
    tileLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
  }

  function activeAnchor() {
    return searchedLocation || userLocation;
  }

  function estimateCost(cp) {
    const dayEl = document.getElementById("parkingDayType");
    const hrsEl = document.getElementById("parkingDuration");
    const day = dayEl ? dayEl.value : "weekday";
    const hours = Number(hrsEl ? hrsEl.value : 2);

    if (vehicleMode === "motorcycle") {
      if (cp.free_bike) return "Free / Grace check";
      if (day === "sun_ph" && cp.free_sun_ph) return "Free (Sun & PH 7am–10:30pm)";
      if (cp.source_type === "LTA Commercial Rates" || cp.source_type === "Commercial reference") {
        return cp.bike_rate || "Commercial / Mall rate";
      }
      return hours >= 10 ? "$0.65 day + $0.65 night cap" : "$0.10/30m ($0.65 cap/session)";
    }

    if (day === "sun_ph" && cp.free_sun_ph) return "Free (Sun & PH 7am–10:30pm)";
    if (cp.source_type === "LTA Commercial Rates") {
      if (day === "sun_ph" && cp.sunday_rate && cp.sunday_rate !== "-") return `Sun/PH: ${cp.sunday_rate}`;
      return cp.weekday_rate || cp.car_rate;
    }
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
      if (cp.source_type === "LTA Commercial Rates") {
        return '<span class="lot-pill is-ref">Commercial Mall</span>';
      }
      return `<span class="lot-pill is-ref">${cp.free_sun_ph ? "Free Sun/PH" : esc(cp.system === "COUPON PARKING" ? "Coupon" : "HDB")}</span>`;
    }
    if (lotInfo.type === "C_fallback") {
      return `<span class="lot-pill is-ref">${lotInfo.avail} Car lots</span>`;
    }
    const cls = lotInfo.avail >= 25 ? "is-plenty" : lotInfo.avail >= 5 ? "is-limited" : "is-full";
    const label = vehicleMode === "motorcycle" ? "bike lots" : "lots";
    return `<span class="lot-pill ${cls}">${lotInfo.avail} / ${lotInfo.total} ${label}</span>`;
  }

  function normText(v) {
    return String(v || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function filterCarparks() {
    if (!dataset) return [];
    const rawQ = (document.getElementById("parkingSearch")?.value || "").trim();
    const q = rawQ.toLowerCase();
    const qNorm = normText(rawQ);
    const qTokens = qNorm ? qNorm.split(/\s+/) : [];
    const anchor = activeAnchor();

    const list = dataset.carparks.filter((cp) => {
      if (q) {
        const hayRaw = `${cp.id} ${cp.name} ${cp.address} ${cp.type} ${cp.postal || ""}`.toLowerCase();
        const hayNorm = normText(hayRaw);
        const textMatch = hayRaw.includes(q) || (qTokens.length > 0 && qTokens.every((tok) => hayNorm.includes(tok)));
        const nearResolved = searchedLocation && haversineKm(searchedLocation.lat, searchedLocation.lng, cp.lat, cp.lng) <= 2.5;
        if (!textMatch && !nearResolved) return false;
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
      if (activeFilters.has("commercial") && cp.source_type !== "LTA Commercial Rates" && cp.source_type !== "Commercial reference" && cp.source_type !== "SG Commercial Directory") return false;
      return true;
    });

    const enriched = list.map((cp) => {
      const lotInfo = getLotInfo(cp);
      const dist = anchor ? haversineKm(anchor.lat, anchor.lng, cp.lat, cp.lng) : null;
      return { cp, lotInfo, dist };
    });

    enriched.sort((a, b) => {
      if (anchor && a.dist !== null && b.dist !== null) return a.dist - b.dist;
      if (vehicleMode === "motorcycle") {
        const aScore = (a.cp.free_bike ? 3 : 0) + (a.lotInfo?.type === "Y" ? 2 : 0) + (a.cp.free_sun_ph ? 1 : 0);
        const bScore = (b.cp.free_bike ? 3 : 0) + (b.lotInfo?.type === "Y" ? 2 : 0) + (b.cp.free_sun_ph ? 1 : 0);
        if (bScore !== aScore) return bScore - aScore;
      } else {
        const aAvail = a.lotInfo ? a.lotInfo.avail : -1;
        const bAvail = b.lotInfo ? b.lotInfo.avail : -1;
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

  function renderSearchBadge() {
    const el = document.getElementById("parkingSearchBadge");
    if (!el) return;
    if (!searchedLocation) {
      el.style.display = "none";
      el.innerHTML = "";
      return;
    }
    el.style.display = "block";
    el.innerHTML = `Near <strong>${esc(searchedLocation.address)}</strong> (within 2.5 km, sorted nearest first) · <button type="button" id="clearGeoSearchBtn" style="background:none;border:0;color:var(--brand-strong);font-weight:700;cursor:pointer;padding:0;">Clear location</button>`;
    document.getElementById("clearGeoSearchBtn")?.addEventListener("click", () => {
      searchedLocation = null;
      lastGeocodedQuery = "";
      const input = document.getElementById("parkingSearch");
      if (input) input.value = "";
      if (map) map.setView([1.3521, 103.8198], 12);
      renderAll();
    });
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
          ["commercial", "Malls & Commercial Rates"],
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
      } else if (cp.source_type === "LTA Commercial Rates") {
        color = "#a855f7";
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
        <span>${esc(estimateCost(cp))}</span><br>
        <a href="https://www.google.com/maps/search/?api=1&query=${cp.lat},${cp.lng}" target="_blank" rel="noopener noreferrer">Open in Google Maps →</a>
      `);
      m.addTo(markerLayer);
    }

    const anchor = activeAnchor();
    if (anchor) {
      L.circleMarker([anchor.lat, anchor.lng], {
        renderer: canvasRenderer,
        radius: 9,
        color: "#ffffff",
        weight: 2.5,
        fillColor: "#2563eb",
        fillOpacity: 1,
      }).bindPopup(searchedLocation ? `Search: ${esc(searchedLocation.address)}` : "Your current location").addTo(markerLayer);
    }
  }

  function rateDetailsHtml(cp) {
    if (cp.source_type === "LTA Commercial Rates" && vehicleMode === "car") {
      const parts = [];
      if (cp.weekday_rate && cp.weekday_rate !== "-") parts.push(`Wkday: ${esc(cp.weekday_rate)}`);
      if (cp.weekday_rate_2 && cp.weekday_rate_2 !== "-") parts.push(esc(cp.weekday_rate_2));
      if (cp.saturday_rate && cp.saturday_rate !== "-") parts.push(`Sat: ${esc(cp.saturday_rate)}`);
      if (cp.sunday_rate && cp.sunday_rate !== "-") parts.push(`Sun/PH: ${esc(cp.sunday_rate)}`);
      return parts.join(" · ");
    }
    return esc(vehicleMode === "motorcycle" ? cp.bike_rate : cp.car_rate);
  }

  function renderCards(items) {
    const grid = document.getElementById("parkingResults");
    const countNote = document.getElementById("parkingResultNote");
    if (!grid) return;

    const shown = items.slice(0, 60);
    if (countNote) {
      countNote.textContent = items.length
        ? `Showing ${shown.length} of ${items.length.toLocaleString()} matching carparks (top ${Math.min(items.length, 320)} plotted on map).`
        : "No carparks match those filters. Try clearing a filter or searching a Singapore postal code (e.g. 460401) or area.";
    }

    grid.innerHTML = shown.map(({ cp, lotInfo, dist }) => `
      <article class="parking-card">
        <div class="parking-card-top">
          <div>
            <span class="parking-code">${esc(cp.id)} · ${esc(cp.source_type === "LTA Commercial Rates" ? "Commercial Mall" : cp.area_tier === "central" ? "Central Area" : "Heartlands / Islandwide")}</span>
            <h3 class="parking-card-title">${esc(cp.name)}</h3>
          </div>
          ${lotPillHtml(cp, lotInfo)}
        </div>
        <div class="parking-meta-tags">
          ${cp.free_sun_ph ? '<span class="parking-tag is-free">Free Sun &amp; PH</span>' : ""}
          ${cp.free_bike ? '<span class="parking-tag is-free">Free / Grace Bike</span>' : ""}
          ${cp.system === "COUPON PARKING" ? '<span class="parking-tag">Coupon / Parking.sg</span>' : ""}
          ${cp.sheltered ? '<span class="parking-tag">Sheltered</span>' : '<span class="parking-tag">Open / Surface</span>'}
          ${cp.night_parking ? '<span class="parking-tag">Night Parking</span>' : ""}
          ${cp.gantry_height > 0 ? `<span class="parking-tag">Gantry ${cp.gantry_height}m</span>` : ""}
          ${dist !== null ? `<span class="parking-tag">${dist.toFixed(2)} km away</span>` : ""}
        </div>
        <div style="font-size:0.84rem;color:var(--muted);">${rateDetailsHtml(cp)}</div>
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
    renderSearchBadge();
    renderFilterChips();
    const filtered = filterCarparks();
    renderSummary(filtered);
    updateMapMarkers(filtered);
    renderCards(filtered);
  }

  async function geocodeWithOneMap(query) {
    if (!query || query.length < 3 || query === lastGeocodedQuery) return;
    lastGeocodedQuery = query;
    try {
      const url = `${ONEMAP_SEARCH_URL}?searchVal=${encodeURIComponent(query)}&returnGeom=Y&getAddrDetails=Y&pageNum=1`;
      const res = await fetch(url);
      if (!res.ok) return;
      const json = await res.json();
      const first = json?.results?.[0];
      if (!first) return;
      const lat = Number(first.LATITUDE);
      const lng = Number(first.LONGITUDE);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      // Ignore stale responses if the user changed the query
      const currentVal = (document.getElementById("parkingSearch")?.value || "").trim();
      if (currentVal !== query) return;
      searchedLocation = {
        lat,
        lng,
        address: first.ADDRESS || first.SEARCHVAL || query,
      };
      if (map) map.setView([lat, lng], 15, { animate: true });
      renderAll();
    } catch {}
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

    const searchInput = document.getElementById("parkingSearch");
    searchInput?.addEventListener("input", () => {
      const val = searchInput.value.trim();
      clearTimeout(searchDebounce);
      if (!val) {
        searchedLocation = null;
        lastGeocodedQuery = "";
        renderAll();
        return;
      }
      renderAll();
      const delay = /^\d{6}$/.test(val) ? 120 : 350;
      searchDebounce = setTimeout(() => geocodeWithOneMap(val), delay);
    });

    ["parkingDayType", "parkingDuration"].forEach((id) => {
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
      dataset = await fetch("./data/carparks.json?v=3", { cache: "no-store" }).then((r) => r.json());
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
