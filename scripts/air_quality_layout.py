"""Static, readable entry point for the interactive homepage air-quality panel."""
import html
import json


def esc(value):
    return html.escape(str(value if value is not None else "Unavailable"), quote=True)


def render_air_quality(cache):
    keys = ["sg_psi", "sg_pm25", "sg_psi_history", "sg_pm25_history", "my_haze", "my_haze_history"]
    snapshot = {key: cache.get(key, {}) for key in keys}
    values = snapshot["sg_psi"].get("data", {}).get("readings", {}).get("psi_twenty_four_hourly", {})
    valid = {k: v for k, v in values.items() if isinstance(v, (int, float)) and v >= 0}
    region = max(valid, key=valid.get) if valid else "west"
    value = valid.get(region)
    bands = [(50, "Good"), (100, "Moderate"), (200, "Unhealthy"), (300, "Very unhealthy"), (float("inf"), "Hazardous")]
    category = next((label for ceiling, label in bands if value is not None and value <= ceiling), "Unavailable")
    regions = ''.join(f'<button type="button" data-air-region="{r}" aria-pressed="{str(r == region).lower()}">{r.title()} <strong>{esc(values.get(r))}</strong></button>' for r in ["north", "south", "east", "west", "central"])
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'''<div class="air-dashboard" data-air-dashboard data-default-region="{region}">
<div class="weather-toolbar"><div role="tablist" aria-label="Air quality country" class="air-country-tabs"><button type="button" role="tab" id="air-country-sg" data-air-country="sg" aria-controls="air-country-panel" aria-selected="true">Singapore</button><button type="button" role="tab" id="air-country-my" data-air-country="my" aria-controls="air-country-panel" aria-selected="false" tabindex="-1">Malaysia</button></div><button type="button" id="refresh-air-dashboard" class="button button-secondary">↻ Refresh air quality</button></div>
<div id="air-country-panel" role="tabpanel" aria-labelledby="air-country-sg">
<div class="air-options"><div id="air-metric-controls" role="group" aria-label="Singapore air-quality metric"><button type="button" data-air-metric="psi" aria-pressed="true">24-hr PSI</button><button type="button" data-air-metric="pm25" aria-pressed="false">1-hr PM2.5</button></div><div id="air-malaysia-controls" hidden><label>State / territory<select id="air-state"><option>Johor</option></select></label><label>Monitoring station<select id="air-station"><option>Larkin, JOHOR</option></select></label></div></div>
<p id="air-source-stamp" class="note">Singapore source reported: {esc(snapshot['sg_psi'].get('data', {}).get('timestamp'))}</p>
<div class="air-visual-grid"><div class="air-headline"><span id="air-metric-label">24-hour PSI</span><div class="air-gauge" id="air-gauge"><strong id="air-number">{esc(value)}</strong><small id="air-unit">PSI</small></div><strong id="air-category-label">{esc(category)}</strong><span id="air-location-label">{region.title()} · Singapore</span><p id="air-reading-context">Selected reporting region</p></div>
<div class="air-map-column"><div id="air-map" role="region" aria-label="Air-quality reporting regions and monitoring stations"><p class="air-map-fallback">Interactive map loads here. Regional readings appear below.</p></div><div id="air-region-list" class="air-region-list" aria-label="Select Singapore region">{regions}</div><p class="note" id="air-map-note">Select a region on the map or use the buttons below it.</p></div>
<div class="air-trend-column"><h3 id="air-chart-title">Recent hourly readings · 24-hr PSI</h3><div id="air-trend" class="air-trend"><p>Hourly history loads here.</p></div><p id="air-history-note" class="note">Chart values use the selected region and metric.</p><details class="air-history-table"><summary>Read hourly values</summary><div id="air-history-values"></div></details></div></div>
<div id="air-legend" class="air-legend" aria-label="Air-quality categories"></div><p id="air-refresh-feedback" class="refresh-feedback" role="status">Checking official air-quality sources…</p>
<p class="note" id="air-source-link">Source: <a href="https://www.haze.gov.sg/">NEA / data.gov.sg</a>. PSI is an index; PM2.5 is a concentration with separate bands.</p><div class="air-detail-links"><a class="detail-link" href="/singapore/haze/">Singapore air-quality details →</a><a class="detail-link" href="/malaysia/haze/">Malaysia air-quality details →</a></div>
<noscript><p>Enable JavaScript to switch countries, metrics and map selections. The Singapore reading above is from the last saved update; both detail pages remain readable.</p></noscript>
</div><script type="application/json" id="air-quality-snapshot">{payload}</script></div>'''
