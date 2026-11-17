"""Fetch SPF speed-enforcement camera locations and write data/speed-cameras.json."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE = "https://www.police.gov.sg/Knowledge-Hub/Traffic/Traffic-Matters/Speed-Enforcement-Camera-Locations"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "speed-cameras.json"
COORDINATE = re.compile(r"(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)")

EXPRESSWAY_CODES = [
    ("Pan Island Expressway", "PIE"),
    ("Pan-Island Expressway", "PIE"),
    ("Ayer Rajah Expressway", "AYE"),
    ("Central Expressway", "CTE"),
    ("East Coast Parkway", "ECP"),
    ("Bukit Timah Expressway", "BKE"),
    ("Seletar Expressway", "SLE"),
    ("Kranji Expressway", "KJE"),
    ("Tampines Expressway", "TPE"),
    ("Marina Coastal Expressway", "MCE"),
]


def classify_road_group(location: str) -> str:
    lower = location.lower()
    for phrase, code in EXPRESSWAY_CODES:
        if phrase.lower() in lower or re.search(rf"\b{code.lower()}\b", lower):
            return code
    return "Arterial"


def parse_cameras(html_text: str, updated_at: str | None = None) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    stamp = updated_at or date.today().isoformat()
    cameras: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    category = "Speed enforcement camera"

    for element in soup.find_all(["h2", "h3", "h4", "tr"]):
        if element.name != "tr":
            heading = element.get_text(" ", strip=True).lower()
            if "fixed speed" in heading:
                category = "Fixed speed camera"
            elif "mobile speed" in heading:
                category = "Mobile speed camera"
            elif "average speed" in heading:
                category = "Average speed camera"
            elif "laser camera" in heading:
                category = "Police speed laser camera"
            continue

        row = element.get_text(" ", strip=True)
        coordinates = COORDINATE.findall(row)
        if not coordinates:
            continue
        location = COORDINATE.sub("", row).strip(" |-") or "Published camera location"
        road_group = classify_road_group(location)
        for latitude, longitude in coordinates:
            key = (category, location, latitude, longitude)
            if key in seen:
                continue
            seen.add(key)
            cameras.append(
                {
                    "id": f"{category.lower().replace(' ', '-')}-{len(cameras) + 1}",
                    "category": category,
                    "road_group": road_group,
                    "location": location,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "source": SOURCE,
                    "source_updated_at": stamp,
                }
            )
    return cameras


def main() -> None:
    response = requests.get(SOURCE, timeout=30)
    response.raise_for_status()
    stamp = date.today().isoformat()
    cameras = parse_cameras(response.text, stamp)
    if not cameras:
        raise RuntimeError("No camera coordinates were found; refusing to overwrite feed")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "source": SOURCE,
                "source_updated_at": stamp,
                "count": len(cameras),
                "cameras": cameras,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cameras)} speed camera coordinates to {OUTPUT}")


if __name__ == "__main__":
    main()
