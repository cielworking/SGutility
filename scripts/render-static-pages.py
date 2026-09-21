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


def render_checkpoint(data, location_key, title):
    cameras = data.get(location_key, [])[:4]
    if cameras:
        cards = []
        for camera in cameras:
            camera_id = html.escape(str(camera.get("camera_id", "")))
            image_url = html.escape(str(camera.get("image", "")), quote=True)
            caption = html.escape(f"{title} - Camera {camera_id}", quote=True)
            cards.append(
                f"""<button class="checkpoint-camera" type="button"
                           onclick="openImageModal('{image_url}', '{caption}', this)"
                           aria-label="Enlarge {html.escape(title)} traffic camera {camera_id}">
                    <img src="{image_url}" alt="{html.escape(title)} traffic camera {camera_id}" loading="lazy" decoding="async">
                    <span>Camera {camera_id}</span>
                  </button>"""
            )
        content = f'<div class="checkpoint-grid">{"".join(cards)}</div>'
    else:
        content = '<p class="checkpoint-empty">No camera images are currently available.</p>'

    return f"""<div class="checkpoint-layout single-location">
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

    return f"""<div class="petrol-table" aria-label="Current Singapore petrol pump prices">
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


def sitemap_entry(url, lastmod=None):
    lastmod_line = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""
    return f"""  <url>
    <loc>{url}</loc>{lastmod_line}
  </url>"""


def render_sitemap(dates):
    urls = [
        ("https://sgalerts.com/", dates.get("home")),
        ("https://sgalerts.com/woodlands-checkpoint.html", dates.get("checkpoints")),
        ("https://sgalerts.com/tuas-checkpoint.html", dates.get("checkpoints")),
        ("https://sgalerts.com/singapore-petrol-prices.html", dates.get("petrol")),
        ("https://sgalerts.com/latest-coe-prices.html", dates.get("coe")),
        ("https://sgalerts.com/bto-launches.html", dates.get("bto")),
        ("https://sgalerts.com/4d-results.html", dates.get("pools")),
        ("https://sgalerts.com/toto-results.html", dates.get("pools")),
        ("https://sgalerts.com/about.html", "2026-09-17"),
        ("https://sgalerts.com/contact.html", "2026-09-17"),
        ("https://sgalerts.com/privacy-policy.html", "2026-09-17"),
        ("https://sgalerts.com/terms.html", "2026-09-17"),
        ("https://sgalerts.com/telex/", None),
        ("https://sgalerts.com/telex/download.html", None),
        ("https://sgalerts.com/telex/api-guide.html", None),
        ("https://sgalerts.com/telex/faq.html", None),
        ("https://sgalerts.com/telex/support.html", None),
        ("https://sgalerts.com/telex/privacy.html", None),
        ("https://sgalerts.com/telex/terms.html", None),
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

    replace_static_block(
        "woodlands-checkpoint.html",
        "WOODLANDS",
        render_checkpoint(checkpoints, "woodlands", "Woodlands Checkpoint"),
    )
    replace_static_block(
        "tuas-checkpoint.html",
        "TUAS",
        render_checkpoint(checkpoints, "tuas", "Tuas Checkpoint"),
    )
    replace_static_block("singapore-petrol-prices.html", "PETROL", render_petrol(petrol))
    replace_static_block("latest-coe-prices.html", "COE", render_coe(coe))
    replace_static_block("bto-launches.html", "BTO", render_bto(bto))

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

    dynamic_dates = {
        "checkpoints": date_only(checkpoints.get("last_updated")),
        "petrol": date_only(petrol.get("last_updated")),
        "coe": date_only(coe.get("last_updated")),
        "bto": date_only(bto.get("last_updated")),
        "pools": date_only(optional["pools"].get("last_updated")),
    }
    home_dates = [
        *dynamic_dates.values(),
        date_only(optional["news"].get("last_updated")),
        date_only(optional["quick"].get("last_updated")),
    ]
    dynamic_dates["home"] = max((date for date in home_dates if date), default=None)
    (ROOT / "sitemap.xml").write_text(render_sitemap(dynamic_dates), encoding="utf-8")
    print("Rendered specialist HTML pages and sitemap.")


if __name__ == "__main__":
    main()
