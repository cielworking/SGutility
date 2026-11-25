(function () {
  const AVAILABILITY_URL = "https://api.data.gov.sg/v1/transport/carpark-availability";
  const NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search";
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
  let markersById = {};
  let selectedCarparkId = null;

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

  function cleanRateText(raw) {
    return String(raw || "")
      .replace(/\s+/g, " ")
      .replace(/\bor part thereof\.?/gi, "")
      .replace(/\bMonday to Thursday\b/gi, "Mon–Thu")
      .replace(/\bMonday to Friday\b/gi, "Mon–Fri")
      .replace(/\bMonday to Saturday\b/gi, "Mon–Sat")
      .replace(/\bFriday to Sunday and Public Holidays?\b/gi, "Fri–Sun & PH")
      .replace(/\bSaturday, Sunday and Public Holidays?\b/gi, "Sat, Sun & PH")
      .replace(/\bSundays? and Public Holidays?\b/gi, "Sun & PH")
      .replace(/\bFirst (\d+ )?hours?\b/gi, (_, n) => (n ? `1st ${n.trim()}hr` : "1st hr"))
      .replace(/\bFirst 30 mins\b/gi, "1st 30m")
      .replace(/\bFirst min\b/gi, "1st min")
      .replace(/\bSubsequent\b/gi, "Sub.")
      .replace(/\bsub\.\s*0\s*mins?\s*free[;,\s]*/gi, "")
      .replace(/\bsub\.\s*30\s*min(?:s|utes)?\b/gi, "sub. 30m")
      .replace(/\bsub\.\s*15\s*min(?:s|utes)?\b/gi, "sub. 15m")
      .replace(/\bper 30 mins?\b/gi, "/ 30m")
      .replace(/\bper (?:hour|hr)\b/gi, "/ hr")
      .replace(/\bper entry\b/gi, "/ entry")
      .replace(/\bper min(?:ute)?\b/gi, "/ min")
      .replace(/\b0?\s*(?:hours?|hrs?|mins?)\s*grace period[;:\s]*/gi, " ")
      .replace(/\b(\d+m grace)\s*·\s*\/\s*(30m|hr|min|entry)\s*(\$\d+(?:\.\d{2})?)/gi, "$3 / $2 ($1)")
      .replace(/\b12:00 AM - 12:00 AM\s*/gi, "24h: ")
      .replace(/\b0?7\.00am\s*-\s*0?7\.00am\b/gi, "24h")
      .replace(/\.00(am|pm)/gi, "$1")
      .replace(/\s+([;,])/g, "$1")
      .replace(/\s{2,}/g, " ")
      .replace(/\.\s*$/g, "")
      .trim();
  }

  function extractShortPrice(text, fallback) {
    const t = cleanRateText(text);
    if (!t || /^commercial gantry/i.test(t) || t === "-") return fallback;
    if (/^no motorcycle parking/i.test(t)) return "No bike parking";
    if (/^free\b/i.test(t)) return "Free";
    const suffixMatch = t.match(/\$\d+(?:\.\d{2})?\s*(?:\/\s*(?:1st\s*\d*\s*(?:hr|30m|min)|hr|hour|30\s*m(?:in)?|15\s*m(?:in)?|min|entry|day|session)|for\s+1st\s+\d*\s*hrs?|per\s+(?:entry|hr|hour|min|30\s*min|day))/i);
    const prefixMatch = t.match(/(?:(1st\s*(?:\d+\s*)?(?:30m|min|hr))|\/\s*(30m|15m|hr|min|entry))\s*(\$\d+(?:\.\d{2})?)/i);
    const usePrefix = prefixMatch && (!suffixMatch || prefixMatch.index < suffixMatch.index);
    if (usePrefix) {
      const unit = (prefixMatch[1] || prefixMatch[2]).trim();
      return `${prefixMatch[3]} / ${unit}`;
    }
    if (suffixMatch) {
      return suffixMatch[0]
        .replace(/\bfor 1st (\d*)\s*hrs?\b/i, (_, n) => `/ 1st ${n ? n + " " : ""}hr`)
        .replace(/\bper entry\b/i, "/ entry")
        .replace(/\bper hr\b|\bper hour\b/i, "/ hr")
        .replace(/\bper min\b/i, "/ min")
        .replace(/\s+/g, " ")
        .trim();
    }
    const bareDollar = t.match(/\$\d+(?:\.\d{2})?/);
    if (bareDollar) return bareDollar[0];
    return t.length > 26 ? t.slice(0, 24).trim() + "…" : t;
  }

  function findNearestBikeFallback(cp) {
    if (!dataset?.carparks?.length || cp.source_type === "HDB / data.gov.sg") return null;
    let best = null;
    let bestDist = 1.6;
    for (const cand of dataset.carparks) {
      if (cand.id === cp.id || cand.no_moto) continue;
      const isHdb = cand.source_type === "HDB / data.gov.sg";
      if (!isHdb && !cand.free_bike) continue;
      const d = haversineKm(cp.lat, cp.lng, cand.lat, cand.lng);
      if (d < bestDist) {
        bestDist = d;
        best = { name: cand.name, dist: d, free: Boolean(cand.free_bike) };
      }
    }
    return best;
  }

  function formatRateLines(val) {
    // Split semicolon-separated time tiers onto clean lines (max 3 lines per row)
    const parts = String(val || "").split(/\s*;\s*(?=(?:\d|Mon|Tue|Wed|Thu|Fri|Sat|Sun|Aft|Same))/).filter(Boolean);
    if (parts.length <= 1) return `<span class="parking-rate-val">${esc(val)}</span>`;
    return `<span class="parking-rate-val">${parts.slice(0, 3).map((p) => `<span class="parking-rate-line">${esc(p)}</span>`).join("")}</span>`;
  }

  function estimateCost(cp) {
    const dayEl = document.getElementById("parkingDayType");
    const hrsEl = document.getElementById("parkingDuration");
    const day = dayEl ? dayEl.value : "weekday";
    const hours = Number(hrsEl ? hrsEl.value : 2);

    if (vehicleMode === "motorcycle") {
      if (cp.no_moto) return "No public bike lots";
      if (cp.free_bike) return "Free bike parking";
      if (day === "sun_ph" && cp.free_sun_ph) return "Free (Sun & PH)";
      if (cp.source_type === "LTA Commercial Rates" || cp.source_type === "SG Commercial Directory" || cp.source_type === "Commercial reference") {
        return extractShortPrice(cp.bike_rate, "Private gantry rate");
      }
      return hours >= 10 ? "$0.65 day + $0.65 night" : "$0.65 cap / session";
    }

    if (day === "sun_ph" && cp.free_sun_ph) return "Free (Sun & PH)";
    if (cp.source_type === "LTA Commercial Rates") {
      const src = (day === "sun_ph" && cp.sunday_rate && cp.sunday_rate !== "-") ? cp.sunday_rate : (cp.weekday_rate || cp.car_rate);
      return extractShortPrice(src, "Gantry rate");
    }
    if (cp.source_type === "SG Commercial Directory" || cp.source_type === "Commercial reference") {
      return extractShortPrice(cp.car_rate, "Check signage");
    }
    if (hours === 10) return cp.night_parking ? "$5.00 overnight cap" : "No overnight";
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
    if (vehicleMode === "motorcycle" && cp.no_moto) {
      return '<span class="lot-pill is-limited">No Bike Lots</span>';
    }
    if (vehicleMode === "motorcycle" && cp.free_bike) {
      return '<span class="lot-pill is-free is-plenty">Free / Rider Spot</span>';
    }
    if (!lotInfo) {
      if (cp.source_type === "LTA Commercial Rates" || cp.source_type === "SG Commercial Directory" || cp.source_type === "Commercial reference") {
        return '<span class="lot-pill is-ref">Commercial</span>';
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
      selectedCarparkId = null;
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
    markersById = {};

    const anchor = activeAnchor();
    const selectedItem = items.find((i) => i.cp.id === selectedCarparkId) || (items.length === 1 ? items[0] : null);

    if (anchor && selectedItem) {
      L.polyline([[anchor.lat, anchor.lng], [selectedItem.cp.lat, selectedItem.cp.lng]], {
        color: "#2563eb",
        weight: 3,
        dashArray: "6, 7",
        opacity: 0.8,
      }).addTo(markerLayer);
    }

    if (selectedItem) {
      const { cp, lotInfo } = selectedItem;
      let color = "#2563eb";
      if (vehicleMode === "motorcycle" && cp.free_bike) color = "#059669";
      else if (lotInfo && (vehicleMode === "car" || lotInfo.type === "Y")) {
        color = lotInfo.avail >= 25 ? "#059669" : lotInfo.avail >= 5 ? "#d97706" : "#dc2626";
      } else if (cp.free_sun_ph) {
        color = "#0d9488";
      } else if (cp.source_type === "LTA Commercial Rates" || cp.source_type === "SG Commercial Directory" || cp.source_type === "Commercial reference") {
        color = "#7c3aed";
      }
      const cpIcon = L.divIcon({
        className: "sga-carpark-pin",
        html: `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="54" viewBox="0 0 44 54" style="width:44px !important;height:54px !important;filter:drop-shadow(0 4px 8px rgba(0,0,0,0.45));display:block;"><path d="M22 2C11.5 2 3 10.5 3 21c0 14.2 19 31 19 31s19-16.8 19-31C41 10.5 32.5 2 22 2z" fill="${color}" stroke="#ffffff" stroke-width="3"/><circle cx="22" cy="20" r="11" fill="#ffffff"/><text x="22" y="25" text-anchor="middle" font-family="system-ui,sans-serif" font-size="15" font-weight="800" fill="${color}">P</text></svg>`,
        iconSize: [44, 54],
        iconAnchor: [22, 52],
        popupAnchor: [0, -48],
      });
      const lotText = lotInfo ? `${lotInfo.avail} / ${lotInfo.total} ${lotInfo.type === "Y" ? "bike" : "car"} lots` : esc(cp.type);
      const m = L.marker([cp.lat, cp.lng], { icon: cpIcon, zIndexOffset: 1000 });
      m.bindPopup(`
        <strong>${esc(cp.name)}</strong> (${esc(cp.id)})<br>
        <span>${lotText}</span><br>
        <span>${esc(estimateCost(cp))}</span><br>
        <a href="https://www.google.com/maps/search/?api=1&query=${cp.lat},${cp.lng}" target="_blank" rel="noopener noreferrer">Open in Google Maps →</a>
      `);
      m.addTo(markerLayer);
      markersById[cp.id] = m;
    }

    if (anchor) {
      let aLat = anchor.lat;
      let aLng = anchor.lng;
      if (selectedItem && haversineKm(aLat, aLng, selectedItem.cp.lat, selectedItem.cp.lng) < 0.025) {
        aLng -= 0.00014;
      }
      const pinIcon = L.divIcon({
        className: "sga-anchor-pin",
        html: `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="54" viewBox="0 0 44 54" style="width:44px !important;height:54px !important;filter:drop-shadow(0 4px 8px rgba(0,0,0,0.45));display:block;"><path d="M22 2C11.5 2 3 10.5 3 21c0 14.2 19 31 19 31s19-16.8 19-31C41 10.5 32.5 2 22 2z" fill="#ef4444" stroke="#ffffff" stroke-width="3"/><circle cx="22" cy="20" r="7.5" fill="#ffffff"/></svg>`,
        iconSize: [44, 54],
        iconAnchor: [22, 52],
        popupAnchor: [0, -48],
      });
      L.marker([aLat, aLng], { icon: pinIcon, zIndexOffset: 900 })
        .bindPopup(searchedLocation ? `<strong>Searched Location:</strong><br>${esc(searchedLocation.address)}` : "<strong>Your current location</strong>")
        .addTo(markerLayer);
    }
  }

  function rateDetailsHtml(cp) {
    if (cp.source_type === "LTA Commercial Rates" && vehicleMode === "car") {
      const rows = [];
      const wk1 = cleanRateText(cp.weekday_rate);
      const wk2 = cleanRateText(cp.weekday_rate_2);
      const sat = cleanRateText(cp.saturday_rate);
      const sun = cleanRateText(cp.sunday_rate);

      const satSameWk = /^same as weekday/i.test(sat);
      const sunSameSat = /^same as sat/i.test(sun);
      const sunSameWk = /^same as weekday/i.test(sun);

      if (wk1 && wk1 !== "-") {
        const label = (satSameWk && (sunSameWk || sunSameSat)) ? "Daily" : "Weekday";
        rows.push([label, wk1]);
      }
      if (wk2 && wk2 !== "-" && wk2.toLowerCase() !== wk1.toLowerCase()) {
        rows.push(["Evening", wk2]);
      }
      if (sat && sat !== "-" && !satSameWk) {
        const label = sunSameSat ? "Sat & Sun" : "Saturday";
        rows.push([label, sat]);
      }
      if (sun && sun !== "-" && !sunSameSat && !(satSameWk && sunSameWk)) {
        rows.push(["Sun & PH", sun]);
      }

      if (rows.length) {
        return `<div class="parking-rate-rows">${rows.map(([k, v]) => `<div class="parking-rate-row"><span class="parking-rate-label">${esc(k)}</span>${formatRateLines(v)}</div>`).join("")}</div>`;
      }
    }

    if (vehicleMode === "motorcycle" && cp.no_moto) {
      const alt = findNearestBikeFallback(cp);
      return `<div class="parking-rate-rows"><div class="parking-rate-row"><span class="parking-rate-label is-warn">Bike</span><span class="parking-rate-val">No public motorcycle parking inside</span></div>${alt ? `<div class="parking-rate-row"><span class="parking-rate-label is-free">${alt.free ? "Free Alt" : "HDB $0.65"}</span><span class="parking-rate-val">${esc(alt.name)} (${alt.dist.toFixed(2)} km)</span></div>` : ""}</div>`;
    }

    const raw = vehicleMode === "motorcycle" ? cp.bike_rate : cp.car_rate;
    const cleaned = cleanRateText(raw);
    if (!cleaned || /^commercial gantry rate/i.test(cleaned)) {
      if (vehicleMode === "motorcycle") {
        const alt = findNearestBikeFallback(cp);
        return `<div class="parking-rate-rows"><div class="parking-rate-row"><span class="parking-rate-label">Gantry</span><span class="parking-rate-val">Private gantry (rate not published online)</span></div>${alt ? `<div class="parking-rate-row"><span class="parking-rate-label is-free">${alt.free ? "Free Alt" : "HDB $0.65"}</span><span class="parking-rate-val">${esc(alt.name)} (${alt.dist.toFixed(2)} km)</span></div>` : ""}</div>`;
      }
      return `<div class="parking-rate-empty"><span>Private gantry — rate follows on-site signage</span></div>`;
    }
    const label = vehicleMode === "motorcycle" ? (cp.free_bike ? "Free" : "Bike") : (cp.source_type === "HDB / data.gov.sg" ? "HDB" : "Rate");
    return `<div class="parking-rate-rows"><div class="parking-rate-row"><span class="parking-rate-label${cp.free_bike && vehicleMode === "motorcycle" ? " is-free" : ""}">${label}</span>${formatRateLines(cleaned)}</div></div>`;
  }

  let visibleLimit = 0;
  let lastItemsKey = "";

  function pageStep() {
    return window.matchMedia && window.matchMedia("(max-width: 700px)").matches ? 12 : 30;
  }

  function renderCards(items) {
    const grid = document.getElementById("parkingResults");
    const countNote = document.getElementById("parkingResultNote");
    if (!grid) return;

    const itemsKey = items.length + ":" + (items[0] ? items[0].cp.id : "");
    if (itemsKey !== lastItemsKey || !visibleLimit) {
      lastItemsKey = itemsKey;
      visibleLimit = pageStep();
    }

    const shown = items.slice(0, Math.min(visibleLimit, 120));
    if (countNote) {
      countNote.textContent = items.length
        ? `Showing ${shown.length} of ${items.length.toLocaleString()} matching carparks — tap a carpark card to pin and zoom it on the map.`
        : "No carparks match those filters. Try clearing a filter or searching a Singapore postal code (e.g. 460401) or area.";
    }

    let moreWrap = document.getElementById("parkingMoreWrap");
    if (!moreWrap) {
      moreWrap = document.createElement("div");
      moreWrap.id = "parkingMoreWrap";
      moreWrap.className = "parking-more-wrap";
      grid.insertAdjacentElement("afterend", moreWrap);
    }
    const canShowMore = shown.length < Math.min(items.length, 120);
    moreWrap.innerHTML = canShowMore
      ? `<button type="button" class="parking-more-btn">Show ${Math.min(pageStep(), Math.min(items.length, 120) - shown.length)} more carparks</button>`
      : "";
    const moreBtn = moreWrap.querySelector(".parking-more-btn");
    if (moreBtn) {
      moreBtn.addEventListener("click", () => {
        visibleLimit += pageStep();
        renderCards(items);
      });
    }

    grid.innerHTML = shown.map(({ cp, lotInfo, dist }) => `
      <article class="parking-card${cp.id === selectedCarparkId ? " is-selected" : ""}" data-card-id="${esc(cp.id)}" data-focus-lat="${cp.lat}" data-focus-lng="${cp.lng}">
        <div class="parking-card-top">
          <div>
            <span class="parking-code">${esc(cp.id)} · ${esc(cp.source_type === "LTA Commercial Rates" || cp.source_type === "SG Commercial Directory" ? "Commercial / Building" : cp.source_type === "Commercial reference" ? "Commercial Reference" : cp.area_tier === "central" ? "Central Area" : "Heartlands / Islandwide")}</span>
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
            <button type="button" data-card-id="${esc(cp.id)}" data-focus-lat="${cp.lat}" data-focus-lng="${cp.lng}">Zoom Map</button>
            <a href="https://www.google.com/maps/search/?api=1&query=${cp.lat},${cp.lng}" target="_blank" rel="noopener noreferrer">Navigate →</a>
          </span>
        </div>
      </article>
    `).join("");

    function focusCarpark(id, lat, lng) {
      selectedCarparkId = id;
      renderAll();
      if (!map) return;
      const anchor = activeAnchor();
      if (anchor) {
        const dKm = haversineKm(anchor.lat, anchor.lng, lat, lng);
        if (dKm >= 0.04 && dKm <= 1.2) {
          map.fitBounds([[anchor.lat, anchor.lng], [lat, lng]], { maxZoom: 18, padding: [70, 70], animate: true });
        } else {
          map.setView([lat, lng], 18, { animate: true });
        }
      } else {
        map.setView([lat, lng], 18, { animate: true });
      }
      const marker = markersById[id];
      if (marker) marker.openPopup();
      if (window.innerWidth < 1100) {
        document.getElementById("parkingMap")?.scrollIntoView({ behavior: "smooth", block: "center" });
      } else {
        const mapEl = document.getElementById("parkingMap");
        if (mapEl) {
          const r = mapEl.getBoundingClientRect();
          if (r.top < 0 || r.bottom > window.innerHeight) {
            mapEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
          }
        }
      }
    }

    grid.querySelectorAll("article.parking-card[data-focus-lat]").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        const id = card.getAttribute("data-card-id");
        const lat = Number(card.getAttribute("data-focus-lat"));
        const lng = Number(card.getAttribute("data-focus-lng"));
        focusCarpark(id, lat, lng);
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
      // Primary: official Singapore SLA OneMap Elastic Search (fast & exact for SG buildings, condos, MRTs & 6-digit postals)
      const omUrl = `https://www.onemap.gov.sg/api/common/elastic/search?searchVal=${encodeURIComponent(query)}&returnGeom=Y&getAddrDetails=Y&pageNum=1`;
      const omRes = await fetch(omUrl);
      if (omRes.ok) {
        const omJson = await omRes.json();
        const hit = Array.isArray(omJson?.results) ? omJson.results[0] : null;
        if (hit && Number.isFinite(Number(hit.LATITUDE)) && Number.isFinite(Number(hit.LONGITUDE))) {
          const currentVal = (document.getElementById("parkingSearch")?.value || "").trim();
          if (currentVal !== query) return;
          const lat = Number(hit.LATITUDE);
          const lng = Number(hit.LONGITUDE);
          searchedLocation = {
            lat,
            lng,
            address: hit.BUILDING && hit.BUILDING !== "NIL" ? `${hit.BUILDING} (${hit.ADDRESS || query})` : (hit.ADDRESS || query),
          };
          if (map) map.setView([lat, lng], 18, { animate: true });
          renderAll();
          return;
        }
      }

      // Fallback: OpenStreetMap Nominatim (SG)
      const url = `${NOMINATIM_SEARCH_URL}?format=json&countrycodes=sg&limit=1&q=${encodeURIComponent(query)}`;
      const res = await fetch(url);
      if (!res.ok) return;
      const json = await res.json();
      const first = Array.isArray(json) ? json[0] : null;
      if (!first) return;
      const lat = Number(first.lat);
      const lng = Number(first.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      const currentVal = (document.getElementById("parkingSearch")?.value || "").trim();
      if (currentVal !== query) return;
      searchedLocation = {
        lat,
        lng,
        address: first.display_name || first.name || query,
      };
      if (map) map.setView([lat, lng], 18, { animate: true });
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
    let suggestMenu = null;
    let suggestItems = [];
    let activeSuggestIdx = -1;
    let omSuggestTimer = null;
    let omSeq = 0;

    if (searchInput && !searchInput.parentElement.classList.contains("parking-search-wrap")) {
      const wrap = document.createElement("div");
      wrap.className = "parking-search-wrap";
      searchInput.parentNode.insertBefore(wrap, searchInput);
      wrap.appendChild(searchInput);
      suggestMenu = document.createElement("div");
      suggestMenu.id = "parkingSuggestMenu";
      suggestMenu.className = "parking-suggest-menu";
      suggestMenu.setAttribute("role", "listbox");
      suggestMenu.hidden = true;
      wrap.appendChild(suggestMenu);
      searchInput.setAttribute("autocomplete", "off");
      searchInput.setAttribute("aria-autocomplete", "list");
      searchInput.setAttribute("aria-controls", "parkingSuggestMenu");
    }

    function closeSuggestions() {
      if (!suggestMenu) return;
      suggestMenu.hidden = true;
      activeSuggestIdx = -1;
    }

    function selectSuggestion(item) {
      if (!item || !searchInput) return;
      clearTimeout(searchDebounce);
      clearTimeout(omSuggestTimer);
      searchInput.value = item.fillText || item.title;
      lastGeocodedQuery = searchInput.value.trim();
      searchedLocation = {
        lat: item.lat,
        lng: item.lng,
        address: item.subtitle ? `${item.title} (${item.subtitle})` : item.title,
      };
      selectedCarparkId = item.cpId || null;
      closeSuggestions();
      renderAll();
      if (map) {
        map.setView([item.lat, item.lng], 18, { animate: true });
        if (item.cpId && markersById[item.cpId]) {
          markersById[item.cpId].openPopup();
        }
      }
    }

    function highlightText(text, rawQuery) {
      const clean = esc(text || "");
      const toks = normText(rawQuery).split(/\s+/).filter((t) => t.length >= 2);
      if (!toks.length) return clean;
      const pattern = toks.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
      try {
        return clean.replace(new RegExp(`(${pattern})`, "gi"), "<mark>$1</mark>");
      } catch {
        return clean;
      }
    }

    function renderSuggestMenu(rawVal) {
      if (!suggestMenu) return;
      if (!suggestItems.length) {
        closeSuggestions();
        return;
      }
      suggestMenu.innerHTML = suggestItems.map((it, idx) => `
        <button type="button" class="parking-suggest-item${idx === activeSuggestIdx ? " is-active" : ""}" role="option" aria-selected="${idx === activeSuggestIdx ? "true" : "false"}" data-sidx="${idx}">
          <span class="parking-suggest-icon" aria-hidden="true">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
          </span>
          <span class="parking-suggest-main">
            <strong>${highlightText(it.title, rawVal)}</strong>
            <small>${esc(it.subtitle || "")}</small>
          </span>
          <span class="parking-suggest-badge">${esc(it.badge || "")}</span>
        </button>
      `).join("");
      suggestMenu.hidden = false;
    }

    function buildLocalSuggestions(rawVal) {
      if (!dataset?.carparks?.length || rawVal.length < 2) return [];
      const qLower = rawVal.toLowerCase();
      const qNorm = normText(rawVal);
      const toks = qNorm.split(/\s+/).filter(Boolean);
      if (!toks.length) return [];

      const scored = [];
      for (const cp of dataset.carparks) {
        const nameNorm = normText(cp.name);
        const idLower = String(cp.id || "").toLowerCase();
        const hayNorm = normText(`${cp.id} ${cp.name} ${cp.address || ""} ${cp.postal || ""}`);
        if (!toks.every((t) => hayNorm.includes(t)) && !idLower.includes(qLower)) continue;

        let score = 10;
        if (idLower === qLower || String(cp.postal || "") === rawVal) score = 100;
        else if (nameNorm.startsWith(qNorm)) score = 90;
        else if (toks.every((t) => nameNorm.includes(t))) score = 75;
        else if (nameNorm.includes(toks[0])) score = 55;
        if (cp.source_type === "LTA Commercial Rates" || cp.source_type === "SG Commercial Directory" || cp.source_type === "Commercial reference") {
          score += 6;
        }
        scored.push({ score, cp });
      }
      scored.sort((a, b) => b.score - a.score || a.cp.name.localeCompare(b.cp.name));
      return scored.slice(0, 6).map(({ cp }) => {
        const lotInfo = getLotInfo(cp);
        const isComm = cp.source_type === "LTA Commercial Rates" || cp.source_type === "SG Commercial Directory" || cp.source_type === "Commercial reference";
        let badge = isComm ? "Mall / Bldg" : (cp.free_bike ? "Free Bike" : "HDB");
        if (lotInfo && (lotInfo.type === "Y" || vehicleMode === "car")) {
          badge = `${lotInfo.avail} lots`;
        }
        return {
          cpId: cp.id,
          title: cp.name,
          fillText: cp.name,
          subtitle: cp.address && normText(cp.address) !== normText(cp.name) ? `${cp.id} · ${cp.address}` : cp.id,
          badge,
          lat: cp.lat,
          lng: cp.lng,
        };
      });
    }

    async function fetchOneMapSuggestions(rawVal, seq) {
      if (rawVal.length < 2) return;
      try {
        const url = `https://www.onemap.gov.sg/api/common/elastic/search?searchVal=${encodeURIComponent(rawVal)}&returnGeom=Y&getAddrDetails=Y&pageNum=1`;
        const res = await fetch(url);
        if (!res.ok || seq !== omSeq) return;
        const data = await res.json();
        if (seq !== omSeq) return;
        const curVal = (searchInput?.value || "").trim();
        if (curVal !== rawVal) return;

        const seenNorm = new Set(suggestItems.map((i) => normText(i.title)));
        const extras = [];
        for (const r of (data?.results || []).slice(0, 5)) {
          const lat = Number(r.LATITUDE);
          const lng = Number(r.LONGITUDE);
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
          const bldg = r.BUILDING && r.BUILDING !== "NIL" ? r.BUILDING : "";
          const title = bldg || r.ADDRESS || rawVal;
          const nTitle = normText(title);
          if (seenNorm.has(nTitle)) continue;
          seenNorm.add(nTitle);
          extras.push({
            cpId: null,
            title,
            fillText: title,
            subtitle: r.ADDRESS && r.ADDRESS !== title ? r.ADDRESS : (r.POSTAL && r.POSTAL !== "NIL" ? `Singapore ${r.POSTAL}` : "Singapore Place"),
            badge: r.POSTAL && r.POSTAL !== "NIL" ? `S(${r.POSTAL})` : "SG Map",
            lat,
            lng,
          });
          if (extras.length >= 3) break;
        }
        if (extras.length) {
          suggestItems = [...suggestItems.slice(0, 5), ...extras].slice(0, 8);
          renderSuggestMenu(rawVal);
        }
      } catch {}
    }

    suggestMenu?.addEventListener("mousedown", (ev) => {
      // Prevent input blur before click fires
      ev.preventDefault();
    });

    suggestMenu?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-sidx]");
      if (!btn) return;
      const idx = Number(btn.getAttribute("data-sidx"));
      if (suggestItems[idx]) selectSuggestion(suggestItems[idx]);
    });

    searchInput?.addEventListener("keydown", (ev) => {
      if (!suggestMenu || suggestMenu.hidden || !suggestItems.length) return;
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        activeSuggestIdx = (activeSuggestIdx + 1) % suggestItems.length;
        renderSuggestMenu(searchInput.value.trim());
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        activeSuggestIdx = (activeSuggestIdx - 1 + suggestItems.length) % suggestItems.length;
        renderSuggestMenu(searchInput.value.trim());
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        const pick = suggestItems[activeSuggestIdx >= 0 ? activeSuggestIdx : 0];
        if (pick) selectSuggestion(pick);
      } else if (ev.key === "Escape") {
        closeSuggestions();
      }
    });

    searchInput?.addEventListener("focus", () => {
      const val = searchInput.value.trim();
      if (val.length >= 2 && suggestItems.length) {
        suggestMenu.hidden = false;
      }
    });

    document.addEventListener("click", (ev) => {
      if (suggestMenu && !suggestMenu.hidden && !ev.target.closest(".parking-search-wrap")) {
        closeSuggestions();
      }
    });

    searchInput?.addEventListener("input", () => {
      const val = searchInput.value.trim();
      clearTimeout(searchDebounce);
      clearTimeout(omSuggestTimer);
      selectedCarparkId = null;
      activeSuggestIdx = -1;
      if (!val) {
        searchedLocation = null;
        lastGeocodedQuery = "";
        suggestItems = [];
        closeSuggestions();
        renderAll();
        return;
      }
      if (val.length >= 2) {
        suggestItems = buildLocalSuggestions(val);
        renderSuggestMenu(val);
        const mySeq = ++omSeq;
        omSuggestTimer = setTimeout(() => fetchOneMapSuggestions(val, mySeq), 140);
      } else {
        suggestItems = [];
        closeSuggestions();
      }
      renderAll();
      const delay = /^\d{6}$/.test(val) ? 120 : 420;
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
        if (map) map.setView([userLocation.lat, userLocation.lng], 18);
        renderAll();
      });
    });
  }

  async function init() {
    initMap();
    wireControls();
    try {
      dataset = await fetch("./data/carparks.json?v=4", { cache: "no-store" }).then((r) => r.json());
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
