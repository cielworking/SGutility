import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import feedparser


OUTPUT_FILE = Path("data/news.json")

NEWS_FEEDS = [
    {
        "source": "CNA",
        "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml",
    },
    {
        "source": "Mothership",
        "url": "https://mothership.sg/feed/",
    },
]

KEYWORDS = {
    "Crime": [
        "arrest", "arrested", "jail", "jailed", "charged", "charge",
        "court", "robbery", "rape", "molest", "sexual", "voyeur",
        "assault", "knife", "stab", "stabbing", "murder", "scam",
        "cheat", "fraud", "police", "cnb"
    ],
    "Traffic": [
        "accident", "crash", "collision", "expressway", "pie", "cte",
        "aye", "sle", "tpe", "bke", "mce", "road", "traffic", "lorry",
        "car", "motorcycle", "bike"
    ],
    "Transport": [
        "mrt", "train", "bus", "smrt", "sbs", "lrt", "delay", "disruption"
    ],
    "Fire": [
        "fire", "scdf", "burn", "smoke", "evacuated", "blaze"
    ],
    "Housing": [
        "bto", "hdb", "flat", "resale", "property", "housing"
    ],
    "Money": [
        "coe", "petrol", "gst", "voucher", "cost", "price", "inflation"
    ],
}


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<.*?>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def classify(title):
    text = title.lower()

    for category, words in KEYWORDS.items():
        for word in words:
            if word in text:
                return category

    return "General"


def get_published_time(entry):
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M")

    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6]).strftime("%Y-%m-%d %H:%M")

    return ""


def fetch_news():
    headlines = []
    seen_urls = set()
    seen_titles = set()

    for feed_info in NEWS_FEEDS:
        source = feed_info["source"]
        url = feed_info["url"]

        feed = feedparser.parse(url)

        for entry in feed.entries[:20]:
            title = clean_text(getattr(entry, "title", ""))
            link = getattr(entry, "link", "")

            if not title or not link:
                continue

            title_key = title.lower()

            if link in seen_urls or title_key in seen_titles:
                continue

            seen_urls.add(link)
            seen_titles.add(title_key)

            headlines.append({
                "category": classify(title),
                "title": title,
                "source": source,
                "url": link,
                "published": get_published_time(entry),
            })

    crime_first = {
        "Crime": 1,
        "Traffic": 2,
        "Transport": 3,
        "Fire": 4,
        "Money": 5,
        "Housing": 6,
        "General": 7,
    }

    headlines.sort(key=lambda x: crime_first.get(x["category"], 99))

    return headlines[:20]


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "last_updated": datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M"),
        "headlines": fetch_news(),
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Updated {OUTPUT_FILE} with {len(data['headlines'])} headlines")


if __name__ == "__main__":
    main()