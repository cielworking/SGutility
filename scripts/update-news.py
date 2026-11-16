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
USER_AGENT = "SGAlertsBot/1.0 (+https://sgalerts.com/)"

NEWS_FEEDS = [
    {
        "source": "CNA Singapore",
        "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416",
        "default_category": "Singapore",
    },
    {
        "source": "Straits Times",
        "url": "https://www.straitstimes.com/news/singapore/rss.xml",
        "default_category": "Singapore",
    },
    {
        "source": "Mothership",
        "url": "https://mothership.sg/feed/",
        "default_category": "Singapore",
    },
    {
        "source": "CNA Business",
        "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936",
        "default_category": "Finance",
    },
    {
        "source": "Straits Times Business",
        "url": "https://www.straitstimes.com/news/business/rss.xml",
        "default_category": "Finance",
    },
    {
        "source": "DollarsAndSense",
        "url": "https://dollarsandsense.sg/feed/",
        "default_category": "Finance",
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
    "Finance": [
        "coe", "petrol", "gst", "voucher", "cost", "price", "inflation",
        "cpf", "mas", "bank", "sgd", "myr", "interest rate", "cdc",
        "t-bill", "t-bills", "ssb", "fixed deposit", "stocks", "reit", "sti",
        "economy", "gdp", "dividend", "investment", "credit card", "salary",
        "tax", "budget", "earnings", "profit", "fed", "tariff",
    ],
    "Transport": [
        "mrt", "train", "bus", "smrt", "sbs", "lrt", "delay", "disruption",
        "lta", "causeway", "checkpoint", "woodlands", "tuas", "rts link",
    ],
    "Traffic": [
        "accident", "crash", "collision", "expressway", "pie", "cte",
        "aye", "sle", "tpe", "bke", "mce", "traffic", "lorry",
        "motorcycle", "motorcyclist", "erp",
    ],
    "Fire": [
        "fire", "scdf", "burn", "smoke", "evacuated", "blaze",
    ],
    "Housing": [
        "bto", "hdb", "flat", "resale", "property", "housing", "condo",
        "mortgage", "hfe", "cov",
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


def classify(title, summary="", default_category="Singapore"):
    text = f"{title} {summary}".lower()
    for category, patterns in CATEGORY_PATTERNS.items():
        if default_category == "IT & Gadgets" and category in {"Traffic", "Transport", "Housing"}:
            continue
        if default_category == "Finance" and category in {"Traffic", "Transport", "Fire"}:
            continue
        if any(pattern.search(text) for pattern in patterns):
            return category
    return default_category


def valid_image_url(url):
    if not url or not isinstance(url, str):
        return ""
    url = html.unescape(url.strip())
    if not url.startswith(("https://", "http://")):
        return ""
    lower = url.lower()
    if any(bad in lower for bad in ("favicon", "cropped-", "s.w.org/images", "pixel", "1x1", "gravatar", "avatar", "/114/114/")):
        return ""
    return url


def extract_image(entry):
    for key in ("media_thumbnail", "media_content", "enclosures"):
        items = getattr(entry, key, None) or []
        if isinstance(items, list):
            for media in items:
                if isinstance(media, dict):
                    candidate = valid_image_url(media.get("url") or media.get("href"))
                    if candidate:
                        return candidate
    if getattr(entry, "image", None):
        candidate = valid_image_url(entry.image)
        if candidate:
            return candidate
    # Check HTML blocks (content, summary, description) for <img> src
    blobs = []
    for item in getattr(entry, "content", None) or []:
        if isinstance(item, dict) and item.get("value"):
            blobs.append(item["value"])
    for attr in ("summary", "description"):
        val = getattr(entry, attr, None)
        if val:
            blobs.append(val)
    for blob in blobs:
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', str(blob), re.I):
            candidate = valid_image_url(match.group(1))
            if candidate:
                return candidate
    return ""


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
        raw = resp.read(750_000).decode("utf-8", errors="replace")
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    raw = re.sub(r"&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)", "&amp;", raw)
    root = ET.fromstring(raw)

    class SimpleEntry:
        pass

    media_ns = "{http://search.yahoo.com/mrss/}"
    content_ns = "{http://purl.org/rss/1.0/modules/content/}"
    atom_ns = "{http://www.w3.org/2005/Atom}"

    entries = []
    rss_items = root.findall(".//item")
    if rss_items:
        for item in rss_items[:40]:
            e = SimpleEntry()
            e.title = item.findtext("title", "")
            e.link = item.findtext("link", "")
            encoded = item.findtext(f"{content_ns}encoded", "")
            desc = item.findtext("description", "")
            e.summary = desc or encoded
            e.content = [{"value": encoded}] if encoded else []
            e.published = item.findtext("pubDate", "")
            e.published_parsed = None
            e.updated_parsed = None
            thumb = item.find(f"{media_ns}thumbnail")
            mcontent = item.find(f"{media_ns}content")
            enclosure = item.find("enclosure")
            img_url = ""
            for el in (thumb, mcontent, enclosure):
                if el is not None and el.attrib.get("url"):
                    img_url = el.attrib["url"]
                    break
            e.image = img_url
            entries.append(e)
        return entries

    for item in root.findall(f".//{atom_ns}entry")[:40]:
        e = SimpleEntry()
        e.title = item.findtext(f"{atom_ns}title", "")
        link_el = item.find(f"{atom_ns}link")
        e.link = link_el.attrib.get("href", "") if link_el is not None else ""
        content_txt = item.findtext(f"{atom_ns}content", "")
        summary_txt = item.findtext(f"{atom_ns}summary", "")
        e.summary = summary_txt or content_txt
        e.content = [{"value": content_txt}] if content_txt else []
        e.published = item.findtext(f"{atom_ns}updated", "") or item.findtext(f"{atom_ns}published", "")
        e.published_parsed = None
        e.updated_parsed = None
        e.image = ""
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
        default_category = feed_info.get("default_category", "Singapore")

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
            image_url = extract_image(entry)
            headlines.append({
                "category": category,
                "title": title,
                "summary": "" if summary.lower() == title_key else summary,
                "image": image_url,
                "source": source,
                "url": link,
                "published": get_published_time(entry),
            })

    priority = {
        "Singapore": 1,
        "Crime": 2,
        "IT & Gadgets": 3,
        "Finance": 4,
        "Transport": 5,
        "Traffic": 6,
        "Housing": 7,
        "Fire": 8,
        "General": 9,
    }
    grouped = {}
    for item in headlines:
        grouped.setdefault(item["category"], []).append(item)

    ordered = []
    for cat in sorted(grouped.keys(), key=lambda c: priority.get(c, 99)):
        items = sorted(grouped[cat], key=lambda x: (1 if x.get("image") else 0, x.get("published") or ""), reverse=True)
        ordered.extend(items[:10])

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
