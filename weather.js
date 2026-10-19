"use strict";

// Readings remain in the HTML; filters and freshness checks progressively enhance it.
function updateWeatherFreshness() {
  const now = Date.now();
  document.querySelectorAll("[data-freshness]").forEach(node => {
    const stamp = Date.parse(node.dataset.stamp);
    const end = node.dataset.end ? Date.parse(node.dataset.end) : Infinity;
    const stale = node.dataset.ok !== "true" || !Number.isFinite(stamp) ||
      now - stamp > Number(node.dataset.hours) * 3600000 || stamp > now + 900000 || now > end;
    node.classList.toggle("is-stale", stale);
    node.textContent = stale ? "Older or unavailable data — check the official source." : "Latest cached official data";
  });
  document.querySelectorAll("[data-warning-end]").forEach(node => {
    const raw = node.dataset.warningEnd;
    const end = Date.parse(/[Zz]|[+-]\d\d:\d\d$/.test(raw) ? raw : `${raw}+08:00`);
    node.hidden = !Number.isFinite(end) || now > end;
  });
}
updateWeatherFreshness();
setInterval(updateWeatherFreshness, 60000);

for (const name of ["area", "state"]) {
  document.addEventListener("change", event => {
    const select = event.target.closest(`[data-${name}-filter]`);
    if (!select) return;
    document.querySelectorAll(`[data-${name}]`).forEach(tile => {
      tile.hidden = Boolean(select.value) && tile.dataset[name] !== select.value;
    });
  });
}

// Haze uses the latest published snapshot; never imply this triggers a new DOE/NEA reading.
document.querySelectorAll('[data-refresh-air]').forEach(button => {
  button.addEventListener('click', async () => {
    const target = document.querySelector('[data-air-content]');
    const feedback = document.querySelector('[data-air-feedback]');
    if (!target || !feedback) return;
    const state = target.querySelector('[data-state-filter]')?.value;
    button.disabled = true;feedback.textContent = 'Checking the latest saved readings…';
    try {
      const response = await fetch(location.pathname,{cache:'no-store',signal:AbortSignal.timeout(15000)});
      if (!response.ok) throw new Error('Unavailable');
      const doc = new DOMParser().parseFromString(await response.text(),'text/html');
      const next = doc.querySelector('[data-air-content]');
      if (!next) throw new Error('Missing readings');
      const same = target.innerHTML === next.innerHTML;
      target.replaceChildren(...next.childNodes);
      const select = target.querySelector('[data-state-filter]');
      if (select && state !== undefined) {select.value=state;select.dispatchEvent(new Event('change',{bubbles:true}));}
      updateWeatherFreshness();
      feedback.textContent = same ? 'No newer saved readings available. Source reporting times are unchanged.' : 'Latest saved readings loaded. Check the source reporting times above.';
    } catch {
      feedback.textContent = 'Refresh failed — previous readings retained. Please try again.';
    } finally {setTimeout(()=>{button.disabled=false;},5000);}
  });
});

function weatherCondition(raw = "Unavailable") {
  const value = raw.toLowerCase();
  const simple = {"tiada hujan": "No rain", "hujan": "Rain", "berjerebu": "Hazy", "jerebu": "Hazy", "ribut petir": "Thunderstorms"};
  if (simple[value]) return simple[value];
  const tails = {"di beberapa tempat": "scattered", "di satu dua tempat": "isolated", "di satu dua tempat di kawasan pantai": "isolated, coastal areas", "di satu dua tempat di kawasan pedalaman": "isolated, inland areas", "di beberapa tempat di kawasan pedalaman": "scattered, inland areas"};
  for (const [key, label] of [["ribut petir", "Thunderstorms"], ["hujan", "Rain"]]) {
    const suffix = value.slice(key.length).trim();
    if (value.startsWith(key) && tails[suffix]) return `${label} (${tails[suffix]})`;
  }
  return raw;
}

const locationSelect = document.getElementById("malaysia-location");
if (locationSelect) {
  let cached;
  let previous = locationSelect.value;
  const feedback = document.createElement("p");
  feedback.setAttribute("role", "status");
  locationSelect.closest("label").after(feedback);
  locationSelect.addEventListener("change", async () => {
    const wanted = locationSelect.value;
    locationSelect.disabled = true;
    feedback.textContent = "Loading location…";
    try {
      if (!cached) {
        const response = await fetch("/data/weather.json");
        if (!response.ok) throw new Error("Forecast unavailable");
        cached = (await response.json()).my_rain.data;
      }
      const rows = cached.filter(r => r.location.location_id === wanted).sort((a, b) => a.date.localeCompare(b.date));
      if (!rows.length) throw new Error("No forecast for location");
      const tiles = rows.map(row => {
        const tile = document.createElement("article");
        tile.className = "weather-tile";
        const heading = document.createElement("h3");
        heading.textContent = row.date;
        const summary = document.createElement("p");
        const strong = document.createElement("strong");
        strong.textContent = weatherCondition(row.summary_forecast);
        summary.append(strong);
        const periods = document.createElement("dl");
        periods.className = "weather-periods";
        for (const [label, field] of [["Morning", "morning_forecast"], ["Afternoon", "afternoon_forecast"], ["Night", "night_forecast"]]) {
          const term = document.createElement("dt");
          term.textContent = label;
          const description = document.createElement("dd");
          description.textContent = weatherCondition(row[field]);
          periods.append(term, description);
        }
        const temperature = document.createElement("p");
        temperature.textContent = `${row.min_temp ?? "Unavailable"}–${row.max_temp ?? "Unavailable"} °C`;
        tile.append(heading, summary, periods, temperature);
        return tile;
      });
      document.getElementById("forecast-location").textContent = rows[0].location.location_name;
      document.getElementById("malaysia-forecast").replaceChildren(...tiles);
      previous = wanted;
      feedback.textContent = `Showing ${rows[0].location.location_name}`;
    } catch {
      locationSelect.value = previous;
      feedback.textContent = "Unable to load that location. The previous forecast is still shown. Please try again or check MET Malaysia.";
    } finally {
      locationSelect.disabled = false;
    }
  });
}
