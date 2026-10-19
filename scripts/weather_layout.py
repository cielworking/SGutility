"""Shared static weather overview. Browser controls enhance this readable HTML."""
import html
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))


def esc(value):
    return html.escape(str(value if value is not None else "Unavailable"), quote=True)


def short_time(raw):
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ).strftime("%d %b, %I:%M %p")
    except (ValueError, TypeError, AttributeError):
        return "Unavailable"


def describe(raw):
    text = str(raw or "Unavailable")
    value = text.lower()
    for source, target in [("tiada hujan", "No rain"), ("ribut petir di beberapa tempat", "Scattered thunderstorms"), ("ribut petir di satu dua tempat", "Isolated thunderstorms"), ("hujan di beberapa tempat", "Scattered rain"), ("hujan di satu dua tempat", "Isolated rain"), ("ribut petir", "Thunderstorms"), ("hujan", "Rain"), ("berjerebu", "Hazy")]:
        if value == source:
            return target
    return text


def regional_cards(outlook):
    now = datetime.now(TZ)
    cards = []
    for region in ["north", "south", "east", "west", "central"]:
        items = []
        for period in outlook.get("periods", []):
            window = period.get("timePeriod", {})
            try:
                if datetime.fromisoformat(window["end"]) <= now:
                    continue
            except (KeyError, ValueError, TypeError):
                continue
            text = period.get("regions", {}).get(region, {}).get("text", "Unavailable")
            items.append(f'<li data-period-end="{esc(window.get("end"))}"><span>{short_time(window.get("start"))} – {short_time(window.get("end"))}</span><strong>{esc(text)}</strong></li>')
        cards.append(f'<article class="region-card"><h3>{region.title()}</h3><ol class="outlook-timeline">{"".join(items) or "<li>Forecast unavailable or expired. Refresh for the latest outlook.</li>"}</ol></article>')
    return '<div class="region-grid">' + ''.join(cards) + '</div>'


def render_combined(cache):
    outlook = cache.get("sg_outlook", {}).get("data", {})
    rain = cache.get("sg_rain", {}).get("data", {})
    places = {r["location"]["location_id"]: r["location"]["location_name"] for r in cache.get("my_rain", {}).get("data", [])}
    chosen = next((k for k, v in places.items() if v == "Johor Bahru"), "Ds090")
    sg_options = ''.join(f'<option value="{esc(r["area"])}">{esc(r["area"])}</option>' for r in rain.get("forecasts", []))
    my_options = ''.join(f'<option value="{esc(k)}" {"selected" if k == chosen else ""}>{esc(v)} ({esc(k[:2])})</option>' for k, v in sorted(places.items(), key=lambda r: (r[1], r[0])))
    rows = sorted([r for r in cache.get("my_rain", {}).get("data", []) if r["location"]["location_id"] == chosen and r["date"] >= datetime.now(TZ).date().isoformat()], key=lambda r: r["date"])
    today = rows[0] if rows else {}
    period_text = ''.join(f'<div><dt>{label}</dt><dd>{esc(describe(today.get(field)))}</dd></div>' for label, field in [("Morning", "morning_forecast"), ("Afternoon", "afternoon_forecast"), ("Night", "night_forecast")])
    return f'''<div class="combined-weather" data-combined-weather>
<div class="weather-toolbar"><div><p class="eyebrow">Singapore &amp; Malaysia</p><h2>Rain radar &amp; outlook</h2></div><button id="refresh-weather" class="button button-secondary" type="button">↻ Refresh weather</button></div>
<p id="weather-refresh-status" class="refresh-feedback" role="status">Saved forecast shown below. Checking official sources…</p>
<section class="radar-panel" aria-label="Rain movement radar">
 <div class="radar-heading"><div><h3>Watch the rain move</h3><p>Recent observed rainfall · drag the timeline or press Play</p></div><label class="radar-range-label">Radar coverage<select id="radar-range"><option value="70km">Singapore &amp; Johor · 70 km</option><option value="240km">Wider region · 240 km</option><option value="480km">Wider region · 480 km</option></select></label></div>
 <div id="rain-map" role="region" aria-label="Rain radar map of Singapore and surrounding Malaysia"></div>
 <div class="radar-playback"><button id="radar-play" class="button button-secondary" type="button" disabled>▶ Play</button><label class="radar-scrubber">Radar time<input id="radar-time" type="range" min="0" max="0" value="0" step="1" disabled aria-label="Radar time"></label><button id="radar-latest" class="button button-secondary" type="button" disabled>Latest</button></div>
 <div class="radar-time-labels"><span id="radar-start">—</span><output id="radar-stamp" for="radar-time">Loading radar…</output><span id="radar-end">—</span></div>
 <div class="radar-legend"><span>Light</span><span class="rain-intensity" aria-label="Rain intensity from light cyan through green, yellow, red to heavy purple"></span><span>Heavy</span></div>
 <p id="radar-status" class="refresh-feedback" role="status">Fetching official NEA radar frames…</p><p class="note">Radar shows past observations, not a prediction of where rain will go next. Regional coverage is centred on Singapore and does not cover all Malaysia. <a href="https://www.nea.gov.sg/weather/rain-areas" target="_blank" rel="noopener noreferrer">Official NEA rain areas</a></p>
</section>
<section id="regional-outlook" class="outlook-section"><div class="weather-toolbar"><div><p class="eyebrow">What to expect · UTC+08</p><h3>Singapore regional outlook</h3></div><label class="weather-filter">Detailed area<select id="sg-area"><option value="">All areas · five-region overview</option>{sg_options}</select></label></div>
<p id="outlook-source-time" class="note">Source issued: {short_time(outlook.get("timestamp"))} UTC+08. Official regional forecast periods are shown below.</p>
<div id="sg-outlook-result">{regional_cards(outlook)}</div>
<details class="weather-explainer"><summary>What do these conditions mean?</summary><p><strong>Cloudy:</strong> cloud-covered skies are forecast; the word alone does not specify rain. <strong>Showers:</strong> rain is expected within the stated area and period. <strong>Thundery showers:</strong> showers with thunder are forecast. These are period forecasts, not exact rain-start times at your address.</p></details></section>
<section id="malaysia-outlook" class="outlook-section"><div class="weather-toolbar"><div><p class="eyebrow">Across the border</p><h3>Malaysia outlook</h3></div><label class="weather-filter">Malaysia location<select id="my-weather-location">{my_options}</select></label></div>
<p class="note">Daily general forecast · morning, afternoon and night. Location types: Ds district, Tn town, St state, Dv division, Rc recreation centre.</p>
<div id="my-outlook-result"><article class="malaysia-day"><h4>Johor Bahru · {esc(today.get("date"))}</h4><dl class="day-periods">{period_text}</dl></article></div><p id="my-source-time" class="note">Last source check: {short_time(cache.get("my_rain", {}).get("fetched_at"))} UTC+08</p></section>
<details class="weather-explainer"><summary>Official warnings and data timing</summary><div id="combined-warnings"><p>Check <a href="https://www.weather.gov.sg/">MSS Singapore</a> and <a href="https://www.met.gov.my/">MET Malaysia</a> for official warnings. Cached Malaysia warnings load with the forecasts.</p></div><p>Radar and forecasts check for updates every five minutes while this page is visible. Weather and haze also have a scheduled 15-minute saved-data refresh. Malaysia's general forecast is published daily. A successful refresh does not mean the source has issued new information.</p></details>
</div>'''
