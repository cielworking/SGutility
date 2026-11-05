"""Generate crawlable weather pages and homepage summaries from cached official data."""
import html
import json
import re
import runpy
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SGT = timezone(timedelta(hours=8))
NOW = datetime.now(SGT)
PAGES = [
    ("singapore", "rain-forecast", "Singapore Rain Forecast", "Two-hour weather forecasts across Singapore, with area conditions and official forecast validity times.", "sg_rain"),
    ("malaysia", "rain-forecast", "Malaysia Rain Forecast", "Malaysia seven-day rain forecasts by location, including Johor Bahru, with morning, afternoon and night conditions.", "my_rain"),
    ("singapore", "haze", "Singapore Haze & Air Quality", "Singapore regional 24-hour PSI and one-hour PM2.5 readings, with reporting times and air-quality categories.", "sg_psi"),
    ("malaysia", "haze", "Malaysia Haze & Air Quality", "Malaysia API / IPU air-quality readings by monitoring station, with source times and official DOE APIMS categories.", "my_haze"),
]


def updated_label(value):
    try:
        parsed = parse(value).astimezone(SGT)
        hour = int(parsed.strftime("%I"))
        return f"Updated {parsed.day} {parsed.strftime('%b')}, {hour}:{parsed.strftime('%M')} {parsed.strftime('%p').lower()} UTC+08"
    except (ValueError, TypeError, AttributeError):
        return "Updated —"


def freshness_chip(value, href):
    return (
        '<p class="freshness-chip" id="weather-freshness">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
        f'<span class="freshness-time">{esc(updated_label(value))}</span>'
        f'<a href="{esc(href)}" target="_blank" rel="noopener noreferrer">Source</a></p>'
    )


def primary_nav(current):
    def item(href, label, key):
        current_attr = ' aria-current="page"' if current == key else ""
        return f'<a href="{href}"{current_attr}>{label}</a>'

    live = ' aria-current="true"' if current in {"rain", "haze", "haze-my", "woodlands", "tuas"} else ""
    more = ' aria-current="true"' if current in {"about", "contact", "results"} else ""
    return (
        '<nav class="primary-nav" aria-label="Primary">'
        f'<details class="nav-menu"><summary aria-expanded="false"{live}>Live</summary><div class="nav-panel">'
        f'{item("/weather/", "Rain", "rain")}{item("/singapore/haze/", "Haze", "haze")}'
        f'{item("/woodlands-checkpoint.html", "Woodlands", "woodlands")}{item("/tuas-checkpoint.html", "Tuas", "tuas")}'
        "</div></details>"
        f'{item("/singapore-petrol-prices.html", "Petrol", "petrol")}'
        f'{item("/latest-coe-prices.html", "COE", "coe")}'
        f'{item("/bto-launches.html", "BTO", "bto")}'
        f'{item("/guides/", "Guides", "guides")}'
        f'<details class="nav-menu nav-more"><summary aria-expanded="false"{more}>More</summary><div class="nav-panel">'
        f'{item("/#news", "News", "news")}{item("/#quick-info", "Quick Info", "quick")}'
        f'{item("/#results", "Results", "results")}{item("/about.html", "About", "about")}{item("/contact.html", "Contact", "contact")}'
        "</div></details></nav>"
    )


def esc(value):
    return html.escape(str(value if value is not None else "Unavailable"), quote=True)


def parse(value):
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def time(value):
    try:
        return parse(value).astimezone(SGT).strftime("%d %b %Y, %I:%M %p UTC+08")
    except (ValueError, TypeError, AttributeError):
        return "Unavailable"


def freshness(feed, stamp=None, end=None, hours=3):
    stamp = stamp or feed.get("fetched_at")
    try:
        stale = not feed.get("ok") or NOW - parse(stamp) > timedelta(hours=hours) or (end and NOW > parse(end)) or parse(stamp) > NOW + timedelta(minutes=15)
    except (ValueError, TypeError, AttributeError):
        stale = True
    return f'<p class="feed-status {"is-stale" if stale else ""}" data-freshness data-ok="{str(bool(feed.get("ok"))).lower()}" data-stamp="{esc(stamp or "")}" data-end="{esc(end or "")}" data-hours="{hours}">{"Older or unavailable data — check the official source." if stale else "Latest cached official data"}</p>'


def condition(value):
    raw = str(value or "Unavailable")
    translations = {"tiada hujan": "No rain", "hujan": "Rain", "berjerebu": "Hazy", "ribut petir": "Thunderstorms"}
    text = raw.lower()
    if text in translations:
        return translations[text]
    for key, label in [("ribut petir", "Thunderstorms"), ("hujan", "Rain")]:
        if text.startswith(key):
            suffix = text[len(key):].strip()
            tail = {"di beberapa tempat": "scattered", "di satu dua tempat": "isolated", "di satu dua tempat di kawasan pantai": "isolated, coastal areas", "di satu dua tempat di kawasan pedalaman": "isolated, inland areas", "di beberapa tempat di kawasan pedalaman": "scattered, inland areas"}.get(suffix)
            if tail:
                return f"{label} ({tail})"
    return raw


def weather_tile(row):
    return f'''<article class="weather-tile"><h3>{esc(row['date'])}</h3><p><strong>{esc(condition(row.get('summary_forecast')))}</strong></p>
      <dl class="weather-periods"><dt>Morning</dt><dd>{esc(condition(row.get('morning_forecast')))}</dd><dt>Afternoon</dt><dd>{esc(condition(row.get('afternoon_forecast')))}</dd><dt>Night</dt><dd>{esc(condition(row.get('night_forecast')))}</dd></dl>
      <p>{esc(row.get('min_temp'))}–{esc(row.get('max_temp'))} °C</p></article>'''


def category(value):
    if not isinstance(value, (int, float)) or value < 0:
        return "Unavailable", "neutral"
    for ceiling, label, tone in [(50, "Good", "good"), (100, "Moderate", "moderate"), (200, "Unhealthy", "unhealthy"), (300, "Very unhealthy", "unhealthy")]:
        if value <= ceiling:
            return label, tone
    return "Hazardous", "unhealthy"


def render_content(country, kind, cache):
    if country == "singapore" and kind == "rain-forecast":
        feed = cache.get("sg_rain", {})
        data = feed.get("data", {})
        period = data.get("valid_period", {})
        rows = data.get("forecasts", [])
        controls = '<label class="weather-filter">Singapore area <select data-area-filter><option value="">All areas</option>' + ''.join(f'<option>{esc(r["area"])}</option>' for r in rows) + '</select></label>'
        content = freshness(feed, data.get("timestamp"), period.get("end")) + f'<p>Forecast valid: <strong>{time(period.get("start"))} to {time(period.get("end"))}</strong></p>'
        content += controls + '<div class="weather-grid">' + ''.join(f'<article class="weather-tile" data-area="{esc(r["area"])}"><h3>{esc(r["area"])}</h3><p class="weather-condition">{esc(r["forecast"])}</p></article>' for r in rows) + '</div>'
        return content, "https://www.weather.gov.sg/", "Meteorological Service Singapore / data.gov.sg", "The two-hour forecast describes expected weather by area. It is a forecast, not a measurement of rain already fallen or an exact rain-start time. Check the validity window before planning your journey."
    if country == "malaysia" and kind == "rain-forecast":
        feed = cache.get("my_rain", {})
        rows = feed.get("data", [])
        places = {r["location"]["location_id"]: r["location"]["location_name"] for r in rows}
        default = next((k for k, v in places.items() if v == "Johor Bahru"), next(iter(places), ""))
        selected = sorted([r for r in rows if r["location"]["location_id"] == default], key=lambda r: r["date"])
        end = max((r["date"] for r in rows), default=NOW.date().isoformat()) + "T23:59:59+08:00"
        content = freshness(feed, end=end, hours=36) + f'<p>Retrieved: {time(feed.get("fetched_at"))}. Official general forecast updates daily.</p>'
        content += '<label class="weather-filter">Malaysia location <select id="malaysia-location">' + ''.join(f'<option value="{esc(k)}" {"selected" if k == default else ""}>{esc(v)} ({esc(k[:2])})</option>' for k, v in sorted(places.items(), key=lambda x: (x[1], x[0]))) + '</select></label>'
        content += '<p>Location types: St = state, Ds = district, Tn = town, Dv = division, Rc = recreation centre.</p>'
        content += f'<h2 id="forecast-location">{esc(places.get(default, "Forecast unavailable"))}</h2><div id="malaysia-forecast" class="weather-grid" aria-live="polite">' + ''.join(weather_tile(r) for r in selected) + '</div>'
        content += '<noscript><p>Johor Bahru is shown by default. Enable JavaScript to select another location, or visit MET Malaysia.</p></noscript>'
        warnings = cache.get("my_warnings", {})
        active = []
        for row in warnings.get("data", []):
            try:
                end_time = parse(row["valid_to"])
                start_time = parse(row["valid_from"])
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=SGT)
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=SGT)
                if start_time <= NOW <= end_time:
                    active.append(row)
            except (KeyError, ValueError, TypeError):
                continue
        content += '<section class="weather-warnings"><h2>Malaysia weather warnings</h2><p>Warnings below cover Malaysia; check the affected locations in each notice.</p>' + freshness(warnings, hours=3)
        for row in active:
            content += f'<article class="weather-tile" data-warning-end="{esc(row["valid_to"])}"><h3>{esc(row.get("heading_en") or row.get("heading_bm"))}</h3><p>{esc(row.get("text_en") or row.get("text_bm"))}</p><p>{esc(row.get("instruction_en") or row.get("instruction_bm") or "See MET Malaysia for details.")}</p><p>Valid until {esc(row["valid_to"])} Malaysia time</p></article>'
        if not active:
            content += '<p>No currently valid warnings were found in this cached feed. Check MET Malaysia for the latest notices.</p>'
        content += '</section>'
        return content, "https://www.met.gov.my/", "MET Malaysia / data.gov.my", "This seven-day general forecast uses morning, afternoon and night periods. It does not offer the same two-hour detail as Singapore. Conditions are translated from the official Malay descriptions; unrecognised descriptions remain in Malay. A forecast of no rain is not a guarantee of dry conditions."
    if country == "singapore":
        feed = cache.get("sg_psi", {})
        pmfeed = cache.get("sg_pm25", {})
        data = feed.get("data", {})
        pm = pmfeed.get("data", {})
        psi = data.get("readings", {}).get("psi_twenty_four_hourly", {})
        fine = pm.get("readings", {}).get("pm25_one_hourly", {})
        content = '<p>24-hour PSI</p>' + freshness(feed, data.get("timestamp")) + f'<p>PSI reported: {time(data.get("timestamp"))}</p>'
        content += '<p>One-hour PM2.5</p>' + freshness(pmfeed, pm.get("timestamp")) + f'<p>PM2.5 reported: {time(pm.get("timestamp"))}</p><div class="weather-grid">'
        for region in ["north", "south", "east", "west", "central"]:
            label, tone = category(psi.get(region))
            content += f'<article class="weather-tile"><h3>{region.title()}</h3><p class="air-reading">{esc(psi.get(region))} <small>24-hour PSI</small></p><span class="air-category {tone}">{label}</span><p>One-hour PM2.5: <strong>{esc(fine.get(region))} µg/m³</strong></p></article>'
        content += '</div>'
        return content, "https://www.haze.gov.sg/", "NEA / data.gov.sg", "The 24-hour Pollutant Standards Index (PSI) and one-hour PM2.5 concentration have different averaging periods and units. PM2.5 is shown in micrograms per cubic metre, not as an index. Air-quality readings alone do not establish the cause of pollution. See NEA for current advisories."
    feed = cache.get("my_haze", {})
    rows = feed.get("data", [])
    content = '<label class="weather-filter">State / territory <select data-state-filter><option value="">All states</option>' + ''.join(f'<option>{esc(s)}</option>' for s in sorted({r["state"] for r in rows})) + '</select></label><div class="weather-grid">'
    for row in rows:
        _, tone = category(row.get("api"))
        label = row.get("category") if row.get("api") is not None else "Unavailable"
        content += f'<article class="weather-tile" data-state="{esc(row["state"])}"><h3>{esc(row["location"])}</h3><p class="air-reading">{esc(row.get("api"))} <small>API / IPU</small></p><span class="air-category {tone}">{esc(label)}</span><p>Dominant pollutant: {esc(row.get("dominant"))}</p><p>Reported: {time(row.get("reported_at"))}</p>{freshness(feed, row.get("reported_at"))}</article>'
    content += '</div>'
    return content, "https://eqms.doe.gov.my/APIMS/main", "Department of Environment Malaysia / APIMS", "Malaysia reports the Air Pollutant Index (API), also called Indeks Pencemaran Udara (IPU), by monitoring station. Select a state to find nearby stations. The displayed category comes from DOE. API / IPU and Singapore PSI are different national indices; compare their labels and reporting periods rather than treating the values as interchangeable. These are reported readings, not a haze forecast."


def main():
    cache = json.loads((ROOT / "data/weather.json").read_text(encoding="utf-8"))
    combined = runpy.run_path(str(ROOT / "scripts/weather_layout.py"))["render_combined"](cache)
    air_panel = runpy.run_path(str(ROOT / "scripts/air_quality_layout.py"))["render_air_quality"](cache)
    cards = []
    for country, kind, title, desc, key in PAGES:
        path = f"/{country}/{kind}/"
        content, source, source_name, explanation = render_content(country, kind, cache)
        if kind == "rain-forecast":
            content = combined
            explanation = "Explore Singapore and Malaysia together using observed rain radar, Singapore's official five-region forecast periods, and Malaysia location forecasts. Choose an individual Singapore area for the two-hour forecast. Radar playback shows recent observations; it does not predict exact rain arrival times."
        related = ''.join(f'<a class="detail-link" href="/{c}/{k}/" {"aria-current=page" if (c,k)==(country,kind) else ""}>{esc(t)}</a>' for c,k,t,_,_ in PAGES)
        if kind == "rain-forecast":
            related = '<a class="detail-link" href="/weather/">Combined rain radar &amp; forecast</a><a class="detail-link" href="/#haze">Haze &amp; air quality</a>'
            nav_current = "rain"
            chip_source = "https://www.weather.gov.sg/"
            outlook = cache.get("sg_outlook") or {}
            chip_stamp = (outlook.get("data") or {}).get("timestamp") or outlook.get("fetched_at")
            head_extra = '<link rel="preload" as="image" href="/assets/rain-map-poster.webp" fetchpriority="high"><link rel="preconnect" href="https://tile.openstreetmap.org" crossorigin>'
        elif country == "singapore":
            nav_current = "haze"
            chip_source = "https://www.haze.gov.sg/"
            psi = cache.get("sg_psi") or {}
            chip_stamp = (psi.get("data") or {}).get("timestamp") or psi.get("fetched_at")
            head_extra = ""
            content = '<div data-air-content>' + content + '</div><button class="button button-secondary" type="button" data-refresh-air>↻ Refresh saved readings</button><p data-air-feedback class="refresh-feedback" role="status">Saved readings update on the 15-minute schedule.</p>'
        else:
            nav_current = "haze-my"
            chip_source = "https://eqms.doe.gov.my/APIMS/main"
            haze = cache.get("my_haze") or {}
            rows = haze.get("data") if isinstance(haze.get("data"), list) else []
            chip_stamp = min((row.get("reported_at") for row in rows if isinstance(row, dict) and row.get("reported_at")), default=None) or haze.get("fetched_at")
            head_extra = ""
            content = '<div data-air-content>' + content + '</div><button class="button button-secondary" type="button" data-refresh-air>↻ Refresh saved readings</button><p data-air-feedback class="refresh-feedback" role="status">Saved readings update on the 15-minute schedule.</p>'
        chip = freshness_chip(chip_stamp, chip_source)
        nav = primary_nav(nav_current)
        schema = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc, "url": "https://sgalerts.com" + path, "isPartOf": {"@type": "WebSite", "name": "SG Alerts", "url": "https://sgalerts.com/"}}
        document = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)} | SG Alerts</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="https://sgalerts.com{path}">
<meta property="og:title" content="{esc(title)} | SG Alerts"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="https://sgalerts.com{path}"><meta property="og:type" content="website"><meta property="og:image" content="https://sgalerts.com/assets/og-share.png"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(title)} | SG Alerts"><meta name="twitter:description" content="{esc(desc)}"><meta name="twitter:image" content="https://sgalerts.com/assets/og-share.png">
<link rel="icon" href="/favicon.ico"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#0c2554"><link rel="manifest" href="/site.webmanifest">{head_extra}<link rel="stylesheet" href="/style.css?v=19">
<script type="application/ld+json">{json.dumps(schema).replace('<', chr(92)+'u003c')}</script><script src="/weather.js?v=3" defer></script><script src="/script.js?v=13" defer></script></head>
<body><a class="skip-link" href="#main-content">Skip to content</a><header class="site-header"><div class="header-inner"><a class="brand" href="/" aria-label="SG Alerts home"><span class="brand-mark"><img src="/assets/logo-96.webp" alt="" width="48" height="48"></span><span><strong>SG Alerts</strong><small>Singapore daily utility dashboard</small></span></a>{nav}</div></header>
<main id="main-content" class="content-page weather-page"><nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">SG Alerts</a> / {esc(title)}</nav><section class="page-hero"><div><p class="eyebrow">{country.title()} · Official data</p><h1>{esc(title)}</h1><p>{esc(desc)}</p></div></section>
<nav class="weather-tabs" aria-label="Weather pages">{related}</nav><section class="surface-card specialist-data-card">{chip}{"" if kind == "rain-forecast" else "<h2>Air-quality readings</h2>"}{content}<p class="note">Source: <a href="{source}" target="_blank" rel="noopener noreferrer">{source_name}</a>. Scheduled refresh every 15 minutes; upstream publication and GitHub scheduling can be delayed.</p></section>
<section class="surface-card seo-guide"><h2>Understanding {esc(title.lower())}</h2><p>{esc(explanation)}</p><h3>How current is this information?</h3><p>Always check the forecast validity or reporting time. Older cached readings remain visible with a warning when a source is delayed or unavailable. Times use Singapore / Malaysia time (UTC+08).</p><h3>Where can I check official updates?</h3><p>Visit <a href="{source}">{source_name}</a> for the latest official information and advisories.</p><div class="seo-related">{related}</div></section></main>
<footer class="site-footer"><div class="footer-inner"><strong>SG Alerts</strong><nav class="footer-links" aria-label="Footer"><a href="/about.html">About</a><a href="/contact.html">Contact</a><a href="/guides/">Guides</a><a href="/privacy-policy.html">Privacy</a><a href="/terms.html">Terms</a></nav></div></footer></body></html>'''
        target = ROOT / country / kind / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document + "\n", encoding="utf-8")
        if kind == "rain-forecast":
            document = document.replace('<script src="/weather.js?v=3" defer></script>', '<link rel="stylesheet" href="/assets/leaflet/leaflet.css" media="print" onload="this.media=\'all\'"><noscript><link rel="stylesheet" href="/assets/leaflet/leaflet.css"></noscript><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" defer></script><script src="/weather.js?v=3" defer></script><script src="/weather-dashboard.js?v=3" defer></script>')
            target.write_text(document + "\n", encoding="utf-8")
            if country == "singapore":
                hub = document.replace(title, "Singapore &amp; Malaysia Rain Radar and Forecast").replace("https://sgalerts.com" + path, "https://sgalerts.com/weather/")
                hub = hub.replace(esc(desc), "Watch recent rain movement, explore timed regional forecasts, and check Singapore and Malaysia weather together.")
                hub = hub.replace("Singapore · Official data", "Singapore &amp; Malaysia · Official data")
                hub_path = ROOT / "weather/index.html"
                hub_path.parent.mkdir(parents=True, exist_ok=True)
                hub_path.write_text(hub + "\n", encoding="utf-8")
        feed = cache.get(key, {})
        data = feed.get("data", {} if country == "singapore" else [])
        stamp, end, hours = None, None, 3
        summary = "Readings unavailable — check the official source."
        if key == "sg_rain":
            city = next((r for r in data.get("forecasts", []) if r["area"] == "City"), {})
            summary = "City: " + city.get("forecast", "Unavailable")
            stamp, end = data.get("timestamp"), data.get("valid_period", {}).get("end")
        elif key == "my_rain":
            row = next((r for r in data if r["location"]["location_name"] == "Johor Bahru" and r["date"] == NOW.date().isoformat()), {})
            summary = "Johor Bahru today: " + condition(row.get("summary_forecast"))
            hours = 36
        elif key == "sg_psi":
            values = list(data.get("readings", {}).get("psi_twenty_four_hourly", {}).values())
            if values:
                summary = f"Regional 24-hour PSI: {min(values)}–{max(values)}"
            stamp = data.get("timestamp")
        elif key == "my_haze":
            summary = f"{len(data)} monitoring stations across Malaysia"
            # Use the oldest station time so a summary never hides delayed stations.
            stamp = min((r["reported_at"] for r in data if r.get("reported_at")), default=None)
        status = freshness(feed, stamp, end, hours)
        cards.append((kind, f'<a class="weather-summary" href="{path}"><span class="eyebrow">{country.title()}</span><h3>{esc(title)}</h3><p><strong>{esc(summary)}</strong></p><p>{esc(desc)}</p>{status}<span class="detail-link">View {"forecast" if kind == "rain-forecast" else "air quality"} →</span></a>'))
    home = ROOT / "index.html"
    text = home.read_text(encoding="utf-8")
    for kind, marker in [("rain-forecast", "RAIN"), ("haze", "HAZE")]:
        rendered = combined + '<p><a class="detail-link" href="/weather/">Open full rain radar &amp; forecast →</a></p>' if kind == "rain-forecast" else '<div data-air-content><div class="weather-summary-grid">' + ''.join(card for k, card in cards if k == kind) + '</div></div><button class="button button-secondary" type="button" data-refresh-air>Refresh saved readings</button><p data-air-feedback class="refresh-feedback" role="status">Saved readings checked every 15 minutes.</p>'
        if kind == "haze":
            rendered = air_panel
        pattern = rf'<!-- STATIC:{marker}:START -->.*?<!-- STATIC:{marker}:END -->'
        text, count = re.subn(pattern, lambda _: f'<!-- STATIC:{marker}:START -->\n{rendered}\n<!-- STATIC:{marker}:END -->', text, flags=re.S)
        if count != 1:
            raise RuntimeError(f"Missing homepage {marker} marker")
    home.write_text(text, encoding="utf-8")
    print("Rendered four weather pages and homepage links")


if __name__ == "__main__":
    main()
