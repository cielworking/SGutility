"""Submit all URLs in sitemap.xml to IndexNow (Bing, DuckDuckGo, Yandex, ChatGPT Search)."""

from __future__ import annotations

import json
import pathlib
import xml.etree.ElementTree as ET

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST = "sgalerts.com"
KEY = "9d4bf338071e0780508ef81ce5f5baf2"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
SITEMAP = ROOT / "sitemap.xml"


def main() -> None:
    if not SITEMAP.exists():
        print("sitemap.xml not found; skipping IndexNow.")
        return
    tree = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    urls = [el.text.strip() for el in tree.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if el.text]
    if not urls:
        return
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }
    try:
        resp = requests.post(
            "https://api.indexnow.org/indexnow",
            headers={"Content-Type": "application/json; charset=utf-8"},
            data=json.dumps(payload),
            timeout=20,
        )
        print(f"IndexNow submitted {len(urls)} URLs -> HTTP {resp.status_code}")
    except Exception as exc:
        print(f"IndexNow warning: {exc}")


if __name__ == "__main__":
    main()
