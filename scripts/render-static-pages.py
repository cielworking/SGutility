import html
import json
import pathlib
import re
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def parse_number(value):
    if value in (None, "", "N/A"):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(value).replace(",", ""))
    return float(match.group(1)) if match else None


def money(value):
    return f"{chr(36)}{int(value):,}"


def updated_label(value):
    if not value:
        return "Updated —"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        singapore_time = timezone(timedelta(hours=8))
        parsed = parsed.astimezone(singapore_time)
        hour = int(parsed.strftime("%I"))
        return f"Updated {parsed.day} {parsed.strftime('%b')}, {hour}:{parsed.strftime('%M')} {parsed.strftime('%p').lower()} UTC+08"
    except ValueError:
        return "Updated —"


def freshness_chip(value, href):
    safe_href = html.escape(href, quote=True)
    return (
        '<p class="freshness-chip">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
        f'<span class="freshness-time">{html.escape(updated_label(value))}</span>'
        f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">Source</a>'
        "</p>"
    )


def timestamp(value):
    if not value:
        return "Unknown"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        singapore_time = timezone(timedelta(hours=8), name="SGT")
        return parsed.astimezone(singapore_time).strftime("%d %b %Y, %I:%M %p %Z")
    except ValueError:
        return html.escape(str(value))


def date_only(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
        return match.group(0) if match else None


def set_camera_preload(filename, image_url):
    path = ROOT / filename
    text = path.read_text(encoding="utf-8")
    if image_url:
        link = f'<link rel="preload" as="image" href="{html.escape(image_url, quote=True)}" fetchpriority="high">'
        block = f"<!-- CAM-PRELOAD:START -->{link}<!-- CAM-PRELOAD:END -->"
    else:
        block = "<!-- CAM-PRELOAD:START --><!-- CAM-PRELOAD:END -->"
    pattern = re.compile(r"<!-- CAM-PRELOAD:START -->.*?<!-- CAM-PRELOAD:END -->", re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(block, text, count=1)
    else:
        text = text.replace(
            '<link rel="stylesheet" href="/style.css',
            block + '\n  <link rel="stylesheet" href="/style.css',
            1,
        )
    path.write_text(text, encoding="utf-8")


def replace_static_block(filename, key, rendered):
    path = ROOT / filename
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"<!-- STATIC:{re.escape(key)}:START -->.*?<!-- STATIC:{re.escape(key)}:END -->",
        re.DOTALL,
    )
    replacement = f"<!-- STATIC:{key}:START -->\n{rendered.rstrip()}\n<!-- STATIC:{key}:END -->"
    updated, count = pattern.subn(replacement, source)
    if count != 1:
        raise RuntimeError(f"Expected one {key} static block in {filename}; found {count}.")
    path.write_text(updated, encoding="utf-8")


def render_checkpoint_ai(traffic, location_key):
    if not traffic or location_key not in traffic:
        return ""
    loc = traffic.get(location_key) or {}
    status = str(loc.get("status") or "Unknown")
    status_slug = re.sub(r"[^a-z]+", "-", status.lower()).strip("-") or "unknown"
    counts = loc.get("counts") or {}
    cars = int(counts.get("car") or 0)
    motos = int(counts.get("motorcycle") or 0)
    heavy = int(counts.get("bus") or 0) + int(counts.get("truck") or 0)
    to_jb = int(loc.get("towards_jb") or 0)
    to_sg = int(loc.get("towards_sg") or 0)
    jb_status = html.escape(str(loc.get("towards_jb_status") or "—"))
    sg_status = html.escape(str(loc.get("towards_sg_status") or "—"))
    total = int(loc.get("total_vehicles") or 0)
    cam_ids = " &amp; ".join(str(c.get("camera_id")) for c in (loc.get("cameras") or []) if c.get("camera_id"))
    cam_label = f" (Cam {cam_ids})" if cam_ids else ""
    checked = html.escape(updated_label(traffic.get("last_updated")))
    note = (
        "Automated YOLOX vehicle count on Cam 4703 only (Cam 4712 excluded); indoor immigration hall queues may differ."
        if location_key == "tuas"
        else "Automated YOLOX vehicle count on public LTA road cameras; indoor immigration hall queues may differ."
    )
    return f"""<div class="ai-traffic-panel" data-checkpoint-ai="{html.escape(location_key, quote=True)}">
      <div class="ai-traffic-head">
        <div>
          <span class="ai-traffic-kicker">AI traffic density{cam_label}</span>
          <strong>{html.escape(status)}</strong>
          <span class="ai-traffic-time"> · {checked}</span>
        </div>
        <span class="ai-status-pill is-{status_slug}">{html.escape(status)} ({total} detected)</span>
      </div>
      <div class="ai-traffic-stats">
        <span><strong>Towards JB:</strong> {to_jb} ({jb_status})</span>
        <span><strong>Towards SG:</strong> {to_sg} ({sg_status})</span>
        <span><strong>Mix:</strong> {cars} cars · {motos} bikes · {heavy} buses/trucks</span>
      </div>
      <p class="ai-traffic-disclaimer">{note}</p>
    </div>"""


def short_clock_sgt(value):
    if not value:
        return "recently"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        singapore_time = timezone(timedelta(hours=8))
        parsed = parsed.astimezone(singapore_time)
        hour = int(parsed.strftime("%I"))
        return f"{hour}:{parsed.strftime('%M')} {parsed.strftime('%p').lower()}"
    except ValueError:
        return "recently"


def psi_band(val):
    if not isinstance(val, (int, float)):
        return "—"
    if val <= 50:
        return "Good"
    if val <= 100:
        return "Moderate"
    if val <= 200:
        return "Unhealthy"
    return "Very Unhealthy"


def pm25_band(val):
    if not isinstance(val, (int, float)):
        return "—"
    if val <= 55:
        return "Normal"
    if val <= 150:
        return "Elevated"
    return "High"


def render_travel_briefing(checkpoints, traffic, weather):
    sg_rain = ((weather or {}).get("sg_rain") or {}).get("data") or {}
    forecasts = {
        str(r.get("area") or ""): str(r.get("forecast") or "Cloudy").lower()
        for r in (sg_rain.get("forecasts") or [])
    }
    sg_psi = (((weather or {}).get("sg_psi") or {}).get("data") or {})
    psi_readings = (sg_psi.get("readings") or {}).get("psi_twenty_four_hourly") or {}
    sg_pm25 = (((weather or {}).get("sg_pm25") or {}).get("data") or {})
    pm25_readings = (sg_pm25.get("readings") or {}).get("pm25_one_hourly") or {}
    air_time = short_clock_sgt(sg_psi.get("timestamp") or sg_pm25.get("timestamp"))

    now_sgt = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    holiday_windows = [
        ("2026-12-31", 'Year-end school holidays, Sat 21 Nov – Thu 31 Dec 2026: typically busiest towards JB Friday afternoons as the holidays begin, and coming back Sunday evenings throughout the holidays. <a href="/guides/causeway-year-end-school-holidays.html">Holiday peaks →</a>'),
        ("2027-02-15", 'New Year &amp; Chinese New Year 2027 (6–9 Feb 2027 long weekend): heavy outbound queues towards JB expected Thu/Fri before CNY and return surges Sun/Mon into Singapore. <a href="/guides/cny-2027-causeway-jb-traffic.html">CNY 2027 peaks →</a>'),
        ("2027-03-22", 'March school holidays &amp; Hari Raya Puasa (13–21 Mar 2027): expect heavy SG → JB queues on Friday 12 March and return congestion Sunday evenings. <a href="/guides/singapore-public-holidays-2027-long-weekends.html">2027 holiday calendar →</a>'),
        ("2027-05-03", 'Good Friday (26 Mar) &amp; Labour Day (1 May 2027) long weekends: cross before 6:30 am or after 10:30 pm on long-weekend Fridays to avoid peak Causeway queues. <a href="/guides/singapore-public-holidays-2027-long-weekends.html">Long weekends →</a>'),
        ("2027-06-28", 'Vesak Day &amp; June school holidays (29 May – 27 Jun 2027): family road trips peak Friday afternoons and Saturday mornings towards JB, returning Sunday evenings. <a href="/guides/singapore-public-holidays-2027-long-weekends.html">Holiday peaks →</a>'),
        ("2027-09-13", 'National Day (9 Aug) &amp; September school holidays (4–12 Sep 2027): expect elevated weekend and school-break queues at both Woodlands and Tuas. <a href="/guides/singapore-public-holidays-2027-long-weekends.html">Holiday peaks →</a>'),
        ("2027-12-31", 'Deepavali &amp; Year-end school holidays (Nov – Dec 2027): heaviest outbound traffic Friday afternoons and Saturday mornings, returning Sunday evenings. <a href="/guides/causeway-year-end-school-holidays.html">Holiday peaks →</a>'),
    ]
    holiday_html = next((html_str for until, html_str in holiday_windows if now_sgt <= until), holiday_windows[-1][1])

    def build_card(loc_key, title, approach_road, area_name, air_region, air_label, gmaps_url, extra_label, extra_html):
        cams = (checkpoints or {}).get(loc_key) or []
        cam_time = short_clock_sgt(cams[0].get("timestamp") if cams else (checkpoints or {}).get("last_updated"))
        loc_t = (traffic or {}).get(loc_key) or {}
        to_jb = int(loc_t.get("towards_jb") or 0)
        to_sg = int(loc_t.get("towards_sg") or 0)
        total = int(loc_t.get("total_vehicles") or 0)
        status = html.escape(str(loc_t.get("status") or "Smooth"))
        jb_st = html.escape(str(loc_t.get("towards_jb_status") or "Smooth"))
        sg_st = html.escape(str(loc_t.get("towards_sg_status") or "Smooth"))
        fc = html.escape(forecasts.get(area_name, "partly cloudy"))
        psi_val = psi_readings.get(air_region)
        pm25_val = pm25_readings.get(air_region)
        psi_str = f"{psi_val} ({psi_band(psi_val)})" if isinstance(psi_val, (int, float)) else "—"
        pm25_str = f"{pm25_val} µg/m³ ({pm25_band(pm25_val)})" if isinstance(pm25_val, (int, float)) else "—"

        return f"""<article class="cp-briefing-card" data-briefing-card="{loc_key}">
          <h3>{html.escape(title)}</h3>
          <ul class="cp-briefing-list">
            <li class="cp-briefing-row">
              <span class="cp-briefing-label">Cameras</span>
              <p class="cp-briefing-val" data-briefing-cam="{loc_key}">Both {html.escape(area_name)} cameras were last captured at {html.escape(cam_time)}.</p>
            </li>
            <li class="cp-briefing-row">
              <span class="cp-briefing-label">Expressway &amp; AI Traffic</span>
              <p class="cp-briefing-val" data-briefing-road="{loc_key}">YOLOX AI detects <strong>{total} vehicles</strong> ({status}) across {html.escape(approach_road)} — {to_jb} towards JB ({jb_st}) and {to_sg} into Singapore ({sg_st}). Road camera density only, not customs queue. <a href="{html.escape(gmaps_url, quote=True)}" target="_blank" rel="noopener noreferrer">Google Maps Live Traffic →</a></p>
            </li>
            <li class="cp-briefing-row">
              <span class="cp-briefing-label">Rain</span>
              <p class="cp-briefing-val" data-briefing-rain="{loc_key}">{html.escape(area_name)}: <span data-rain-gauge="{loc_key}">no rain on the nearest gauge now</span>; next two hours {fc}. <a href="/weather/">Rain map →</a></p>
            </li>
            <li class="cp-briefing-row">
              <span class="cp-briefing-label">Air</span>
              <p class="cp-briefing-val" data-briefing-air="{loc_key}">{html.escape(air_label)}: 24-hour PSI {html.escape(psi_str)}; 1-hour PM2.5 {html.escape(pm25_str)}, NEA at {html.escape(air_time)}. <a href="/singapore/haze/">PSI by region →</a></p>
            </li>
            <li class="cp-briefing-row">
              <span class="cp-briefing-label">Holiday</span>
              <p class="cp-briefing-val" data-briefing-holiday>{holiday_html}</p>
            </li>
            <li class="cp-briefing-row">
              <span class="cp-briefing-label">{html.escape(extra_label)}</span>
              <p class="cp-briefing-val">{extra_html}</p>
            </li>
          </ul>
        </article>"""

    w_card = build_card(
        "woodlands",
        "Woodlands Checkpoint · Causeway",
        " the BKE approach & Causeway",
        "Woodlands",
        "north",
        "North Singapore",
        "https://www.google.com/maps/@1.4485,103.769,15z/data=!5m1!1e1",
        "RTS Link & Checklist",
        'RTS Link, Woodlands North to Bukit Chagar: target passenger service end-2026. <a href="/guides/jb-causeway-vep-autopass-tng-checklist.html">VEP &amp; QR checklist →</a>',
    )
    t_card = build_card(
        "tuas",
        "Tuas Checkpoint · Second Link",
        " the AYE approach & Second Link",
        "Tuas",
        "west",
        "West Singapore",
        "https://www.google.com/maps/@1.3475,103.6365,14z/data=!5m1!1e1",
        "Route Comparison",
        'Tuas Second Link connects AYE directly to Gelang Patah CIQ, Iskandar Puteri &amp; Bukit Indah. <a href="/guides/woodlands-vs-tuas-checkpoint.html">Woodlands vs Tuas →</a>',
    )
    return f'<div class="cp-briefing-grid">{w_card}{t_card}</div>'


def render_travel_advisor(traffic):
    if not traffic or "woodlands" not in traffic or "tuas" not in traffic:
        return '<p class="loading-state">Comparing Woodlands &amp; Tuas traffic…</p>'
    w = traffic["woodlands"]
    t = traffic["tuas"]
    w_jb = int(w.get("towards_jb") or 0)
    t_jb = int(t.get("towards_jb") or 0)
    rec = "Tuas Second Link" if t_jb < w_jb else "Woodlands Causeway" if w_jb < t_jb else "Tie — check both cameras"
    w_cls = " is-recommended" if w_jb <= t_jb else ""
    t_cls = " is-recommended" if t_jb < w_jb else ""
    checked = html.escape(updated_label(traffic.get("last_updated")))
    return f"""<div class="ai-traffic-head">
      <div>
        <span class="ai-traffic-kicker">AI Crossing Advisor · Towards JB &amp; Return</span>
        <strong>Lighter SG → JB approach now: {html.escape(rec)}</strong>
      </div>
      <span class="ai-traffic-time">{checked}</span>
    </div>
    <div class="travel-advisor-grid">
      <div class="travel-route-box{w_cls}">
        <strong>Woodlands Causeway (Cam 2701 &amp; 2702)</strong>
        <span>Status: <strong>{html.escape(str(w.get("status") or "—"))}</strong> ({int(w.get("total_vehicles") or 0)} vehicles detected)</span>
        <span>Towards JB: {w_jb} ({html.escape(str(w.get("towards_jb_status") or "—"))}) · Towards SG: {int(w.get("towards_sg") or 0)} ({html.escape(str(w.get("towards_sg_status") or "—"))})</span>
        <a class="detail-link" href="/woodlands-checkpoint.html">All Woodlands cameras →</a>
      </div>
      <div class="travel-route-box{t_cls}">
        <strong>Tuas Second Link (Cam 4703 &amp; 4712)</strong>
        <span>Status: <strong>{html.escape(str(t.get("status") or "—"))}</strong> ({int(t.get("total_vehicles") or 0)} vehicles detected)</span>
        <span>Towards JB: {t_jb} ({html.escape(str(t.get("towards_jb_status") or "—"))}) · Towards SG: {int(t.get("towards_sg") or 0)} ({html.escape(str(t.get("towards_sg_status") or "—"))})</span>
        <a class="detail-link" href="/tuas-checkpoint.html">All Tuas cameras →</a>
      </div>
    </div>
    <p class="ai-traffic-disclaimer">Comparison uses live YOLOX road-camera vehicle density. Indoor immigration hall queues and JB CIQ counters can still vary independently.</p>"""


def render_news_static(news_data):
    items = (news_data or {}).get("headlines") or []
    if not items:
        return '<p class="loading-state">No headlines are currently available.</p>'
    hero_idx = next(
        (i for i, item in enumerate(items[:36]) if str(item.get("image") or "").startswith(("https://", "http://"))),
        -1,
    )
    hero_html = ""
    if hero_idx >= 0:
        hero = items[hero_idx]
        h_cat = str(hero.get("category") or "General")
        h_slug = re.sub(r"[^a-z0-9]+", "-", h_cat.lower()).strip("-") or "general"
        h_pub = f" · {html.escape(str(hero.get('published')))}" if hero.get("published") else ""
        h_sum = f'<p>{html.escape(hero.get("summary") or "")}</p>' if hero.get("summary") else ""
        hero_url = html.escape(str(hero.get("url", "#")), quote=True)
        hero_html = f"""<article class="news-hero-card">
          <a class="news-hero-media" href="{hero_url}" target="_blank" rel="noopener noreferrer"><img src="{html.escape(str(hero.get("image", "")), quote=True)}" alt="" fetchpriority="high" decoding="async"></a>
          <div class="news-hero-body">
            <a class="news-card-link" href="{hero_url}" target="_blank" rel="noopener noreferrer">
              <div><span class="news-tag news-{h_slug}">{html.escape(h_cat)}</span></div>
              <h2>{html.escape(str(hero.get("title", "")))}</h2>
              {h_sum}
            </a>
            <div class="news-card-footer"><small>{html.escape(str(hero.get("source", "")))}{h_pub}</small></div>
          </div>
        </article>"""

    cards = []
    for idx, item in enumerate(items[:36]):
        if idx == hero_idx:
            continue
        cat = str(item.get("category") or "General")
        slug = re.sub(r"[^a-z0-9]+", "-", cat.lower()).strip("-") or "general"
        img_url = str(item.get("image") or "")
        img_html = (
            f'<div class="news-thumb-wrap"><img class="news-thumb" src="{html.escape(img_url, quote=True)}" alt="" loading="lazy" decoding="async"></div>'
            if img_url.startswith(("https://", "http://"))
            else ""
        )
        cls_extra = "" if img_url.startswith(("https://", "http://")) else " news-card-textonly"
        summary = item.get("summary") or ""
        summary_html = f'<p class="news-summary">{html.escape(summary)}</p>' if summary else ""
        published = f" · {html.escape(str(item.get('published')))}" if item.get("published") else ""
        item_url = html.escape(str(item.get("url", "#")), quote=True)
        cards.append(
            f"""<article class="news-card-item{cls_extra}">
          <a class="news-card-link" href="{item_url}" target="_blank" rel="noopener noreferrer">
            {img_html}
            <span class="news-tag news-{slug}">{html.escape(cat)}</span>
            <strong>{html.escape(str(item.get("title", "")))}</strong>
            {summary_html}
          </a>
          <div class="news-card-footer"><small>{html.escape(str(item.get("source", "")))}{published}</small></div>
        </article>"""
        )
    return (
        f'<div class="news-topbar"><span class="news-meta">{len(items)} curated stories · {html.escape(updated_label(news_data.get("last_updated")))}</span></div>'
        + hero_html
        + f'<div class="news-grid">{"".join(cards)}</div>'
    )


def render_checkpoint(data, location_key, title, source_url=None, traffic=None):
    cameras = data.get(location_key, [])[:4]
    if cameras:
        cards = []
        fallback = []
        for index, camera in enumerate(cameras):
            camera_id = html.escape(str(camera.get("camera_id", "")))
            image_url = html.escape(str(camera.get("image", "")), quote=True)
            caption = html.escape(f"{title} - Camera {camera_id}", quote=True)
            stamp = html.escape(str(camera.get("timestamp", "")), quote=True)
            priority = ' fetchpriority="high"' if index == 0 else ' loading="lazy"'
            cards.append(
                f"""<button class="checkpoint-camera" type="button" data-camera-id="{camera_id}"
                           onclick="openImageModal('{image_url}', '{caption}', this)"
                           aria-label="Enlarge {html.escape(title)} traffic camera {camera_id}">
                    <img src="{image_url}" data-src="{image_url}" alt="{html.escape(title)} traffic camera {camera_id}" width="1920" height="1069" data-timestamp="{stamp}"{priority} decoding="async">
                    <span>Camera {camera_id}</span>
                  </button>"""
            )
            fallback.append(
                f"""<button class="checkpoint-camera" type="button">
                    <img src="{image_url}" alt="{html.escape(title)} traffic camera {camera_id}" width="1920" height="1069">
                    <span>Camera {camera_id}</span>
                  </button>"""
            )
        content = (
            f'<div class="checkpoint-grid checkpoint-live">{"".join(cards)}</div>'
            f'<noscript><style>.checkpoint-live{{display:none}}</style>'
            f'<div class="checkpoint-grid">{"".join(fallback)}</div></noscript>'
        )
    else:
        content = '<p class="checkpoint-empty">No camera images are currently available.</p>'

    href = source_url or data.get("source_url") or "https://datamall.lta.gov.sg/content/datamall/en.html"
    ai_panel = render_checkpoint_ai(traffic, location_key)
    return freshness_chip(data.get("last_updated"), href) + ai_panel + f"""<div class="checkpoint-layout single-location">
      <div class="checkpoint-group">
        <h3>{html.escape(title)}</h3>
        {content}
      </div>
    </div>
    <div class="note">Source: {html.escape(data.get("source_name", "LTA / data.gov.sg"))}. Last updated: {timestamp(data.get("last_updated"))}.</div>"""


def render_petrol(prices):
    fuel_keys = ["ron92", "ron95", "ron98", "premium", "diesel"]
    cheapest = {}
    for key in fuel_keys:
        values = [parse_number(item.get(key)) for item in prices.get("brands", [])]
        valid = [value for value in values if value is not None]
        cheapest[key] = min(valid) if valid else None

    rows = []
    for item in prices.get("brands", []):
        cells = []
        for key in fuel_keys:
            value = item.get(key, "N/A")
            current = parse_number(value)
            if current is None:
                cells.append('<span class="na">N/A</span>')
                continue
            is_cheapest = current == cheapest[key]
            cells.append(
                f'<span class="{"cheapest" if is_cheapest else ""}">'
                f'{html.escape(str(value))}'
                f'{"<small>Cheapest</small>" if is_cheapest else ""}'
                f'</span>'
            )
        rows.append(
            f"""<div class="petrol-row">
          <div class="brand-cell">
            <img src="{html.escape(str(item.get("logo", "")), quote=True)}" alt="{html.escape(str(item.get("brand", "")))} logo">
            <strong>{html.escape(str(item.get("brand", "")))}</strong>
          </div>
          {"".join(cells)}
        </div>"""
        )

    return freshness_chip(prices.get("last_updated"), prices.get("source_url") or "https://petrolprice.sg/") + f"""<div class="petrol-table" aria-label="Current Singapore petrol pump prices">
      <div class="petrol-header">
        <span>Brand</span><span>92</span><span>95</span><span>98</span><span>Premium</span><span>Diesel</span>
      </div>
      {"".join(rows)}
    </div>
    <div class="note">Source: {html.escape(prices.get("source_name", ""))}. Last updated: {timestamp(prices.get("last_updated"))}. Listed pump prices in SGD per litre.</div>"""


def render_coe(data):
    category_names = {
        "Category A": "Cat A - Cars up to 1600cc / 130bhp",
        "Category B": "Cat B - Cars above 1600cc / 130bhp",
        "Category C": "Cat C - Goods Vehicle & Bus",
        "Category D": "Cat D - Motorcycle",
        "Category E": "Cat E - Open Category",
    }
    rows = [
        freshness_chip(data.get("last_updated"), data.get("source_url") or "https://data.gov.sg/"),
        f"""<div class="row">
      <span>Latest bidding</span>
      <strong>{html.escape(str(data.get("latest_month", "")))} - {html.escape(str(data.get("latest_bidding_label", "")))}</strong>
    </div>"""
    ]
    for item in data.get("latest", []):
        change = item.get("change", 0) or 0
        arrow = "▲" if change > 0 else "▼" if change < 0 else "—"
        trend = "up" if change > 0 else "down" if change < 0 else ""
        percent = abs(item.get("change_percent", 0) or 0)
        rows.append(
            f"""<div class="row">
      <span>{html.escape(category_names.get(item.get("category"), str(item.get("category", ""))))}</span>
      <strong>{money(item.get("premium", 0))}<br>
        <small class="{trend}">{arrow} {money(abs(change))} ({percent:g}%)</small>
      </strong>
    </div>"""
        )
    rows.append(
        f'<div class="note">Source: {html.escape(data.get("source_name", ""))}. Last updated: {timestamp(data.get("last_updated"))}.</div>'
    )
    return "\n".join(rows)


def render_bto(data):
    grouped = {}
    for item in data.get("projects", []):
        town = item.get("town", "Unknown")
        entry = grouped.setdefault(
            town,
            {"stage": item.get("stage", "Upcoming"), "types": set(), "projects": 0},
        )
        entry["projects"] += 1
        entry["types"].update(
            part.strip()
            for part in str(item.get("flat_types", "")).split(",")
            if part.strip()
        )

    tiles = []
    for town, item in grouped.items():
        types = ", ".join(sorted(item["types"]))
        count = item["projects"]
        tiles.append(
            f"""<div class="bto-tile">
        <div>
          <span class="bto-town">{html.escape(town)}</span>
          <p>{html.escape(types)}</p>
          <small>{count} project{"s" if count != 1 else ""} available</small>
        </div>
        <div class="bto-status"><strong>{html.escape(str(item["stage"]))}</strong></div>
      </div>"""
        )

    return f"""<div class="row">
      <span>Latest HDB portal data</span>
      <strong>{len(data.get("projects", []))} upcoming project entries</strong>
    </div>
    <div class="bto-grid">{"".join(tiles)}</div>
    <div class="note">Source: {html.escape(data.get("source_name", ""))}. Last updated: {timestamp(data.get("last_updated"))}. {html.escape(data.get("note", ""))}</div>"""


def draw_day(value):
    try:
        return datetime.strptime(str(value), "%a, %d %b %Y").date()
    except (ValueError, TypeError):
        return None


def set_date_modified(filename, value):
    path = ROOT / filename
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r'("dateModified":\s*")[0-9]{4}-[0-9]{2}-[0-9]{2}(")')
    updated, count = pattern.subn(rf"\g<1>{value}\g<2>", text, count=1)
    if count:
        path.write_text(updated, encoding="utf-8")


def render_sgpools(data, kind):
    entry = data.get(kind) or {}
    draw_date = entry.get("draw_date")
    draw_no = entry.get("draw_no")
    day = draw_day(draw_date)
    source = html.escape(str(data.get("source_name") or "Singapore Pools"))

    updated = ""
    if day:
        updated = (
            '<p class="note pool-updated">Last updated: '
            f'<time datetime="{day.isoformat()}">{day.day} {day.strftime("%b %Y")}</time></p>'
        )

    if not draw_date or not draw_no:
        return updated + '\n<p class="note">Results are unavailable right now. Check the official Singapore Pools result.</p>'

    heading = "Latest 4D Result" if kind == "four_d" else "Latest TOTO Result"
    title = f"<h3>{heading}</h3><span>{html.escape(str(draw_date))} · Draw {html.escape(str(draw_no))}</span>"

    if kind == "four_d":
        starter = [html.escape(str(value)) for value in entry.get("starter") or []]
        consolation = [html.escape(str(value)) for value in entry.get("consolation") or []]
        prizes = []
        for css, label, value in (
            (" first", "1st Prize", entry.get("first_prize")),
            ("", "2nd Prize", entry.get("second_prize")),
            ("", "3rd Prize", entry.get("third_prize")),
        ):
            if value is None:
                continue
            prizes.append(
                f'<div class="sgpools-prize{css}"><span>{label}</span>'
                f"<strong>{html.escape(str(value))}</strong></div>"
            )
        panel = f"""<div class="pool-panel pool-panel-main">
  <div class="pool-panel-title">{title}</div>
  <div class="pool-summary-strip">
    <span>Top prize: <strong>{html.escape(str(entry.get("first_prize", "")))}</strong></span>
    <span>Starter: <strong>{len(starter)}</strong></span>
    <span>Consolation: <strong>{len(consolation)}</strong></span>
  </div>
  <div class="sgpools-prizes">{"".join(prizes)}</div>
  <div class="pool-number-section">
    <div><h4>Starter Prizes</h4><div class="number-grid">{"".join(f"<span>{number}</span>" for number in starter)}</div></div>
    <div><h4>Consolation Prizes</h4><div class="number-grid">{"".join(f"<span>{number}</span>" for number in consolation)}</div></div>
  </div>
</div>"""
    else:
        numbers = [html.escape(str(value)) for value in entry.get("winning_numbers") or []]
        panel = f"""<div class="pool-panel">
  <div class="pool-panel-title">{title}</div>
  <div class="toto-numbers">{"".join(f"<span>{number}</span>" for number in numbers)}</div>
  <div class="toto-additional compact"><span>Additional Number</span><strong>{html.escape(str(entry.get("additional_number", "")))}</strong></div>
</div>"""

    return f"""{updated}
{panel}
<div class="note">Source: {source}.</div>"""


def sitemap_entry(url, lastmod=None):
    lastmod_line = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""
    return f"""  <url>
    <loc>{url}</loc>{lastmod_line}
  </url>"""


def page_is_noindex(text):
    for tag in re.findall(r"<meta\b[^>]*>", text, flags=re.I):
        if re.search(r"\bname\s*=\s*['\"]robots['\"]", tag, flags=re.I) and re.search(r"noindex", tag, flags=re.I):
            return True
    return False


def guide_page_url(path):
    if path.name == "index.html":
        return "https://sgalerts.com/guides/"
    return f"https://sgalerts.com/guides/{path.name}"


def existing_sitemap_lastmods(path=None):
    sitemap = path or (ROOT / "sitemap.xml")
    if not sitemap.exists():
        return {}
    found = {}
    for block in re.findall(r"<url>(.*?)</url>", sitemap.read_text(encoding="utf-8"), flags=re.S):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block)
        lastmod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block)
        if loc:
            found[loc.group(1)] = lastmod.group(1) if lastmod else None
    return found


def guide_sitemap_urls(preserved=None):
    """Every indexable guides/*.html page. lastmod stays with the page."""
    preserved = existing_sitemap_lastmods() if preserved is None else preserved
    pages = []
    index = ROOT / "guides" / "index.html"
    if index.exists():
        pages.append(index)
    pages.extend(path for path in sorted((ROOT / "guides").glob("*.html")) if path.name != "index.html")
    urls = []
    for path in pages:
        text = path.read_text(encoding="utf-8")
        if page_is_noindex(text):
            continue
        url = guide_page_url(path)
        lastmod = preserved.get(url)
        if not lastmod:
            match = re.search(r'"dateModified"\s*:\s*["\'](\d{4}-\d{2}-\d{2})', text)
            lastmod = match.group(1) if match else None
        urls.append((url, lastmod))
    return urls


def render_sitemap(dates, preserved=None):
    urls = [
        ("https://sgalerts.com/", dates.get("home")),
        ("https://sgalerts.com/travel.html", dates.get("checkpoints")),
        ("https://sgalerts.com/woodlands-checkpoint.html", dates.get("checkpoints")),
        ("https://sgalerts.com/tuas-checkpoint.html", dates.get("checkpoints")),
        ("https://sgalerts.com/housing.html", dates.get("bto")),
        ("https://sgalerts.com/bto-launches.html", dates.get("bto")),
        ("https://sgalerts.com/bto-mortgage-calculator.html", dates.get("bto")),
        ("https://sgalerts.com/singapore-petrol-prices.html", dates.get("petrol")),
        ("https://sgalerts.com/petrol-discount-calculator.html", dates.get("petrol")),
        ("https://sgalerts.com/latest-coe-prices.html", dates.get("coe")),
        ("https://sgalerts.com/coe-calculator.html", dates.get("coe")),
        ("https://sgalerts.com/4d-results.html", dates.get("pools")),
        ("https://sgalerts.com/toto-results.html", dates.get("pools")),
        ("https://sgalerts.com/weather/", dates.get("weather")),
        ("https://sgalerts.com/singapore/rain-forecast/", dates.get("weather")),
        ("https://sgalerts.com/malaysia/rain-forecast/", dates.get("weather")),
        ("https://sgalerts.com/singapore/haze/", dates.get("weather")),
        ("https://sgalerts.com/malaysia/haze/", dates.get("weather")),
        *guide_sitemap_urls(preserved),
        ("https://sgalerts.com/about.html", "2026-09-17"),
        ("https://sgalerts.com/contact.html", "2026-09-17"),
        ("https://sgalerts.com/privacy-policy.html", "2026-11-06"),
        ("https://sgalerts.com/terms.html", "2026-09-17"),
    ]
    body = "\n\n".join(sitemap_entry(url, lastmod) for url, lastmod in urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>
"""


def main():
    checkpoints = load_json("checkpoints.json")
    petrol = load_json("petrol-prices.json")
    coe = load_json("coe-prices.json")
    bto = load_json("bto-projects.json")

    try:
        traffic = load_json("checkpoint-traffic.json")
    except FileNotFoundError:
        traffic = None

    replace_static_block(
        "woodlands-checkpoint.html",
        "WOODLANDS",
        render_checkpoint(
            checkpoints,
            "woodlands",
            "Woodlands Checkpoint",
            "https://onemotoring.lta.gov.sg/content/onemotoring/home/driving/traffic_information/traffic-cameras/woodlands.html",
            traffic=traffic,
        ),
    )
    replace_static_block(
        "tuas-checkpoint.html",
        "TUAS",
        render_checkpoint(
            checkpoints,
            "tuas",
            "Tuas Checkpoint",
            "https://onemotoring.lta.gov.sg/content/onemotoring/home/driving/traffic_information/traffic-cameras/tuas.html",
            traffic=traffic,
        ),
    )
    for filename, location_key in (("woodlands-checkpoint.html", "woodlands"), ("tuas-checkpoint.html", "tuas")):
        cameras = checkpoints.get(location_key) or []
        set_camera_preload(filename, cameras[0].get("image") if cameras else "")
    if traffic:
        replace_static_block("travel.html", "AI-WOODLANDS", render_checkpoint_ai(traffic, "woodlands"))
        replace_static_block("travel.html", "AI-TUAS", render_checkpoint_ai(traffic, "tuas"))
        replace_static_block("travel.html", "TRAVEL-ADVISOR", render_travel_advisor(traffic))
    replace_static_block("singapore-petrol-prices.html", "PETROL", render_petrol(petrol))
    replace_static_block("latest-coe-prices.html", "COE", render_coe(coe))
    replace_static_block("bto-launches.html", "BTO", render_bto(bto))
    replace_static_block("housing.html", "BTO", render_bto(bto))

    optional = {}
    for key, filename in {
        "news": "news.json",
        "quick": "quick-info.json",
        "pools": "sgpools-results.json",
    }.items():
        try:
            optional[key] = load_json(filename)
        except FileNotFoundError:
            optional[key] = {}

    if optional.get("news"):
        news_html = render_news_static(optional["news"])
        replace_static_block("news.html", "NEWS", news_html)
        replace_static_block("index.html", "NEWS", news_html)

    pools = optional["pools"]
    if pools:
        for filename, kind, marker in (
            ("4d-results.html", "four_d", "FOURD"),
            ("toto-results.html", "toto", "TOTO"),
        ):
            replace_static_block(filename, marker, render_sgpools(pools, kind))
            day = draw_day((pools.get(kind) or {}).get("draw_date"))
            if day:
                set_date_modified(filename, day.isoformat())

    dynamic_dates = {
        "checkpoints": date_only(checkpoints.get("last_updated")),
        "petrol": date_only(petrol.get("last_updated")),
        "coe": date_only(coe.get("last_updated")),
        "bto": date_only(bto.get("last_updated")),
        "news": date_only(optional["news"].get("last_updated")),
        "pools": date_only(optional["pools"].get("last_updated")),
    }
    weather_path = DATA / "weather.json"
    weather = json.loads(weather_path.read_text(encoding="utf-8")) if weather_path.exists() else {}
    replace_static_block("travel.html", "TRAVEL-BRIEFING", render_travel_briefing(checkpoints, traffic, weather))
    dynamic_dates["weather"] = max((date_only(feed.get("attempted_at")) for feed in weather.values() if feed.get("attempted_at")), default=None)
    home_dates = [
        *dynamic_dates.values(),
        date_only(optional["news"].get("last_updated")),
        date_only(optional["quick"].get("last_updated")),
    ]
    dynamic_dates["home"] = max((date for date in home_dates if date), default=None)
    # Read lastmods before overwriting so guide dates are not reset on each data run.
    (ROOT / "sitemap.xml").write_text(render_sitemap(dynamic_dates, existing_sitemap_lastmods()), encoding="utf-8")
    print("Rendered specialist HTML pages and sitemap.")


if __name__ == "__main__":
    main()
