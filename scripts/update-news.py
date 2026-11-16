from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import json
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

try:
    import feedparser
except ImportError:
    feedparser = None

SGT = ZoneInfo("Asia/Singapore")
OUTPUT_FILE = Path("data/news.json")
USER_AGENT = "SGAlertsBot/1.0 (+https://sgalerts.com/news.html)"

NEWS_FEEDS = [
    {
        "source": "CNA Singapore",
        "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416",
    },
    {
        "source": "CNA",
        "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml",
    },
    {
        "source": "Mothership",
        "url": "https://mothership.sg/feed/",
    },
    {
        "source": "Straits Times",
        "url": "https://www.straitstimes.com/news/singapore/rss.xml",
    },
    {
        "source": "Vulcan Post",
        "url": "https://vulcanpost.com/feed/",
        "default_category": "IT & Gadgets",
    },
    {
        "source": "SoyaCincau",
        "url": "https://soyacincau.com/feed/",
        "default_category": "IT & Gadgets",
    },
    {
        "source": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "default_category": "IT & Gadgets",
    },
    {
        "source": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "default_category": "IT & Gadgets",
    },
]

KEYWORDS = {
    "Crime": [
        "arrest", "arrested", "jail", "jailed", "charged", "charge",
        "court", "robbery", "rape", "molest", "sexual", "voyeur",
        "assault", "knife", "stab", "stabbing", "murder", "scam", "scammer",
        "cheat", "fraud", "police", "cnb", "trafficking", "sentence",
    ],
    "IT & Gadgets": [
        "iphone", "ipad", "macbook", "apple", "android", "pixel", "samsung",
        "galaxy", "xiaomi", "oppo", "huawei", "laptop", "gpu", "nvidia",
        "amd", "intel", "processor", "chip", "gadget", "smartwatch",
        "earbuds", "headphones", "router", "wifi", "wi-fi", "cybersecurity",
        "ransomware", "data breach", "malware", "chatgpt", "openai", "gemini",
        "anthropic", "ai", "smartphone", "camera", "tech", "software", "app",
        "fintech", "ev", "tesla", "byd",
    ],
    "Transport": [
        "mrt", "train", "bus", "smrt", "sbs", "lrt", "delay", "disruption",
        "lta", "causeway", "checkpoint", "woodlands", "tuas", "rts link",
    ],
    "Traffic": [
        "accident", "crash", "collision", "expressway", "pie", "cte",
        "aye", "sle", "tpe", "bke", "mce", "traffic", "lorry",
        "motorcycle", "Motorcyclist", "erp",
    ],
    "Fire": [
        "fire", "scdf", "burn", "smoke", "evacuated", "blaze",
    ],
    "Housing": [
        "bto", "hdb", "flat", "resale", "property", "housing", "condo",
        "mortgage", "hfe", "cov",
    ],
    "Money": [
        "coe", "petrol", "gst", "voucher", "cost", "price", "inflation",
        "cpf", "mas", "bank", "sgd", "myr", "interest rate", "cdc",
    ],
}

CATEGORY_PATTERNS = {
    category: [re.compile(rf"\b{re.escape(word.lower())}\b") for word in words]
    for category, words in KEYWORDS.items()
}


def clean_text(text):
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def trim_summary(text, limit=180):
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) <= limit:
        return cleaned
    cut = cleaned[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:-")
    return f"{cut}..."


def classify(title, summary="", default_category="General"):
    text = f"{title} {summary}".lower()
    for category, patterns in CATEGORY_PATTERNS.items():
        if any(pattern.search(text) for pattern in patterns):
            return category
    return default_category


def format_sgt(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SGT).strftime("%Y-%m-%d %H:%M")


def get_published_time(entry):
    parsed_time = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed_time:
        return format_sgt(datetime(*parsed_time[:6], tzinfo=timezone.utc))
    raw = getattr(entry, "published", "") or getattr(entry, "updated", "")
    if raw:
        try:
            return format_sgt(parsedate_to_datetime(raw))
        except (TypeError, ValueError):
            try:
                return format_sgt(datetime.fromisoformat(raw.replace("Z", "+00:00")))
            except ValueError:
                pass
    return ""


def parse_xml_fallback(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read(500_000).decode("utf-8", errors="replace")
    # Strip invalid XML control characters so WordPress/quirky feeds parse cleanly.
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    root = ET.fromstring(raw)

    class SimpleEntry:
        pass

    entries = []
    rss_items = root.findall(".//item")
    if rss_items:
        for item in rss_items[:40]:
            e = SimpleEntry()
            e.title = item.findtext("title", "")
            e.link = item.findtext("link", "")
            e.summary = item.findtext("description", "")
            e.published = item.findtext("pubDate", "")
            e.published_parsed = None
            e.updated_parsed = None
            entries.append(e)
        return entries

    atom_ns = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(f".//{atom_ns}entry")[:40]:
        e = SimpleEntry()
        e.title = item.findtext(f"{atom_ns}title", "")
        link_el = item.find(f"{atom_ns}link")
        e.link = link_el.attrib.get("href", "") if link_el is not None else ""
        e.summary = item.findtext(f"{atom_ns}summary", "") or item.findtext(f"{atom_ns}content", "")
        e.published = item.findtext(f"{atom_ns}updated", "") or item.findtext(f"{atom_ns}published", "")
        e.published_parsed = None
        e.updated_parsed = None
        entries.append(e)
    return entries


def read_feed_entries(url):
    if feedparser is not None:
        feed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
        if getattr(feed, "entries", None):
            return feed.entries[:40]
    return parse_xml_fallback(url)


def fetch_news():
    headlines = []
    seen_urls = set()
    seen_titles = set()

    for feed_info in NEWS_FEEDS:
        source = feed_info["source"]
        url = feed_info["url"]
        default_category = feed_info.get("default_category", "General")

        try:
            entries = read_feed_entries(url)
        except Exception as exc:
            print(f"Skipping {source} ({url}): {exc}")
            continue

        for entry in entries[:40]:
            title = clean_text(getattr(entry, "title", ""))
            link = str(getattr(entry, "link", "")).strip()
            raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            summary = trim_summary(raw_summary)

            if not title or not link:
                continue

            title_key = title.lower()
            if link in seen_urls or title_key in seen_titles:
                continue

            seen_urls.add(link)
            seen_titles.add(title_key)

            category = classify(title, summary, default_category=default_category)
            headlines.append({
                "category": category,
                "title": title,
                "summary": "" if summary.lower() == title_key else summary,
                "source": source,
                "url": link,
                "published": get_published_time(entry),
            })

    # Keep categories balanced and fresh so Crime, IT & Gadgets, and SG news are all represented.
    priority = {
        "Crime": 1,
        "IT & Gadgets": 2,
        "Transport": 3,
        "Traffic": 4,
        "Housing": 5,
        "Money": 6,
        "Fire": 7,
        "General": 8,
    }
    headlines.sort(key=lambda x: (priority.get(x["category"], 99), x.get("published") or ""), reverse=False)
    # Within each category, sort newest first.
    grouped = {}
    for item in headlines:
        grouped.setdefault(item["category"], []).append(item)

    ordered = []
    for cat in sorted(grouped.keys(), key=lambda c: priority.get(c, 99)):
        items = sorted(grouped[cat], key=lambda x: x.get("published") or "", reverse=True)
        ordered.extend(items[:12])

    return ordered[:64]


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "last_updated": datetime.now(SGT).isoformat(),
        "headlines": fetch_news(),
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Updated {OUTPUT_FILE} with {len(data['headlines'])} headlines")


if __name__ == "__main__":
    main()
