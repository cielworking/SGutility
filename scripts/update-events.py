import email.utils
import json
import pathlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "data" / "sg-events.json"
SGT = ZoneInfo("Asia/Singapore")

FEEDS = [
    (
        "Concerts & Shows",
        "https://news.google.com/rss/search?q=Singapore+concerts+OR+live+show+tickets&hl=en-SG&gl=SG&ceid=SG:en",
    ),
    (
        "Events & Festivals",
        "https://news.google.com/rss/search?q=Singapore+things+to+do+festival+exhibition+this+weekend&hl=en-SG&gl=SG&ceid=SG:en",
    ),
    (
        "Sales & Deals",
        "https://news.google.com/rss/search?q=Singapore+sale+shopping+promotion+deals&hl=en-SG&gl=SG&ceid=SG:en",
    ),
]


def clean_title_and_source(raw_title):
    text = re.sub(r"\s+", " ", (raw_title or "")).strip()
    if " - " in text:
        title, source = text.rsplit(" - ", 1)
        return title.strip(), source.strip()
    return text, "Singapore News"


def parse_pubdate(raw_date):
    if not raw_date:
        return None, ""
    try:
        dt = email.utils.parsedate_to_datetime(raw_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SGT)
        dt_sgt = dt.astimezone(SGT)
        return dt_sgt.isoformat(), dt_sgt.strftime("%d %b %Y")
    except Exception:
        return None, ""


def fetch_category(category, url, limit=4):
    resp = requests.get(url, timeout=15, headers={"User-Agent": "SGAlerts/1.0"})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    seen = set()
    for node in root.findall(".//item"):
        raw_title = node.findtext("title") or ""
        link = (node.findtext("link") or "").strip()
        pub_raw = node.findtext("pubDate") or ""
        title, source = clean_title_and_source(raw_title)
        if not title or not link:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        iso_date, display_date = parse_pubdate(pub_raw)
        items.append(
            {
                "category": category,
                "title": title,
                "source": source,
                "url": link,
                "published_at": iso_date,
                "date_label": display_date,
            }
        )
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return items[:limit]


def main():
    existing = {}
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    existing_by_cat = {}
    for item in existing.get("items") or []:
        existing_by_cat.setdefault(item.get("category"), []).append(item)

    collected = []
    for category, url in FEEDS:
        try:
            items = fetch_category(category, url, limit=4)
            collected.extend(items)
        except Exception as exc:
            print(f"Warning: events feed '{category}' failed ({exc}); retaining previous items.")
            collected.extend(existing_by_cat.get(category, [])[:4])

    if not collected:
        print("Warning: no events collected; skipping write.")
        return

    output = {
        "source_name": "Singapore Official & News Event Feeds",
        "last_updated": datetime.now(SGT).isoformat(),
        "items": collected,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Updated {OUTPUT_FILE} with {len(collected)} Singapore event/concert/sale items")


if __name__ == "__main__":
    main()
