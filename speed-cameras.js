(function () {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));

  let cameras = [];
  let activeRoad = "ALL";
  let userLocation = null;
  let map = null;
  let tileLayer = null;
  let markerLayer = null;
  let canvasRenderer = null;

  function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function initMap() {
    const el = document.getElementById("speedCameraMap");
    if (!el || typeof window.L === "undefined" || map) return;
    map = L.map(el, { preferCanvas: true }).setView([1.3521, 103.8198], 12);
    canvasRenderer = L.canvas({ padding: 0.4 });
    tileLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
  }

  function renderChips() {
    const wrap = document.getElementById("cameraRoadChips");
    if (!wrap) return;
    const counts = { ALL: cameras.length };
    for (const c of cameras) counts[c.road_group] = (counts[c.road_group] || 0) + 1;
    const order = ["ALL", "PIE", "AYE", "CTE", "ECP", "BKE", "SLE", "KJE", "TPE", "MCE", "Arterial"].filter((k) => counts[k]);
    wrap.innerHTML = order.map((k) =>
      `<button type="button" class="filter-pill" data-road="${esc(k)}" aria-pressed="${activeRoad === k ? "true" : "false"}">${k === "ALL" ? "All Roads" : esc(k)} (${counts[k]})</button>`
    ).join("");

    wrap.querySelectorAll("button[data-road]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeRoad = btn.getAttribute("data-road");
        render();
      });
    });
  }

  function render() {
    renderChips();
    const q = (document.getElementById("cameraSearch")?.value || "").trim().toLowerCase();
    const filtered = cameras.filter((c) => {
      if (activeRoad !== "ALL" && c.road_group !== activeRoad) return false;
      if (q && !`${c.location} ${c.road_group} ${c.category}`.toLowerCase().includes(q)) return false;
      return true;
    }).map((c) => ({
      cam: c,
      dist: userLocation ? haversineKm(userLocation.lat, userLocation.lng, c.latitude, c.longitude) : null,
    }));

    if (userLocation) filtered.sort((a, b) => a.dist - b.dist);

    const note = document.getElementById("cameraResultNote");
    if (note) note.textContent = `Showing ${filtered.length} official SPF speed enforcement camera locations.`;

    if (map && markerLayer) {
      markerLayer.clearLayers();
      for (const { cam } of filtered) {
        const isExp = cam.road_group !== "Arterial";
        L.circleMarker([cam.latitude, cam.longitude], {
          renderer: canvasRenderer,
          radius: 7,
          color: "#ffffff",
          weight: 1.5,
          fillColor: isExp ? "#ef4444" : "#f59e0b",
          fillOpacity: 0.9,
        }).bindPopup(`
          <strong>${esc(cam.location)}</strong><br>
          <span>${esc(cam.category)} (${esc(cam.road_group)})</span><br>
          <span>${cam.latitude.toFixed(6)}, ${cam.longitude.toFixed(6)}</span><br>
          <a href="https://www.google.com/maps/search/?api=1&query=${cam.latitude},${cam.longitude}" target="_blank" rel="noopener noreferrer">Open in Google Maps →</a>
        `).addTo(markerLayer);
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

    const list = document.getElementById("cameraResults");
    if (!list) return;
    list.innerHTML = filtered.map(({ cam, dist }) => `
      <article class="parking-card">
        <div class="parking-card-top">
          <div>
            <span class="parking-code">${esc(cam.road_group)} · ${esc(cam.category)}</span>
            <h3 class="parking-card-title">${esc(cam.location)}</h3>
          </div>
          ${dist !== null ? `<span class="lot-pill is-ref">${dist.toFixed(1)} km</span>` : `<span class="lot-pill is-limited">SPF Camera</span>`}
        </div>
        <div style="font-size:0.8rem;color:var(--muted);">Coords: ${cam.latitude.toFixed(6)}, ${cam.longitude.toFixed(6)}</div>
        <div class="parking-card-footer">
          <span class="parking-tag">${esc(cam.road_group)}</span>
          <span class="parking-card-actions">
            <button type="button" data-focus-lat="${cam.latitude}" data-focus-lng="${cam.longitude}">Locate on Map</button>
            <a href="https://www.google.com/maps/search/?api=1&query=${cam.latitude},${cam.longitude}" target="_blank" rel="noopener noreferrer">Google Maps →</a>
          </span>
        </div>
      </article>
    `).join("");

    list.querySelectorAll("button[data-focus-lat]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!map) return;
        const lat = Number(btn.getAttribute("data-focus-lat"));
        const lng = Number(btn.getAttribute("data-focus-lng"));
        map.setView([lat, lng], 16, { animate: true });
        document.getElementById("speedCameraMap")?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
  }

  async function init() {
    initMap();
    document.getElementById("cameraSearch")?.addEventListener("input", render);
    document.getElementById("cameraGeoBtn")?.addEventListener("click", () => {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition((pos) => {
        userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        if (map) map.setView([userLocation.lat, userLocation.lng], 13);
        render();
      });
    });

    try {
      const json = await fetch("./data/speed-cameras.json?v=2", { cache: "no-store" }).then((r) => r.json());
      cameras = json.cameras || [];
      const stampEl = document.getElementById("cameraSourceUpdated");
      if (stampEl && json.source_updated_at) stampEl.textContent = `Updated ${json.source_updated_at}`;
      render();
    } catch (err) {
      console.error("Failed to load speed-cameras.json", err);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
