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


def normalize_location_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" |-")
    if cleaned.isupper():
        cleaned = cleaned.title()
        for abbr in ("Pie", "Aye", "Cte", "Ecp", "Bke", "Sle", "Kje", "Tpe", "Mce", "L/P"):
            cleaned = re.sub(rf"\b{re.escape(abbr)}\b", abbr.upper(), cleaned)
    return cleaned


def parse_cameras(html_text: str, updated_at: str | None = None) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    stamp = updated_at or date.today().isoformat()
    cameras: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    category = "Speed enforcement camera"
    rowspan_loc = ""
    rowspan_left = 0
    pending_loc = ""

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
            pending_loc = ""
            rowspan_left = 0
            continue

        cells = element.find_all(["th", "td"])
        if not cells or all(c.name == "th" for c in cells):
            continue
        cell_texts = [c.get_text(" ", strip=True) for c in cells]
        row_text = " ".join(cell_texts)
        coordinates = COORDINATE.findall(row_text)

        # Check for rowspan parent location (e.g., Tanah Merah Coast Road Average Speed Zones)
        for c in cells:
            rs = c.get("rowspan")
            if rs and str(rs).isdigit() and int(rs) > 1:
                txt = c.get_text(" ", strip=True)
                if not COORDINATE.search(txt) and not txt.isdigit():
                    rowspan_loc = txt
                    rowspan_left = int(rs)
                    break

        if not coordinates:
            # Handle header/descriptor row right above coordinate pairs (e.g., MCE Camera A / Camera B)
            desc_parts = [t for t in cell_texts if t and not t.isdigit() and t.lower() not in {"no.", "location", "coordinates", "gps coordinates", "camera a", "camera b"}]
            if desc_parts:
                pending_loc = max(desc_parts, key=len)
            continue

        # Extract human road name cleanly from non-coordinate cells
        location = ""
        sub_index = ""
        if rowspan_left > 0 and rowspan_loc:
            location = rowspan_loc
            for t in cell_texts:
                if t.isdigit():
                    sub_index = t
                    break
            rowspan_left -= 1
        else:
            candidates = []
            for t in cell_texts:
                stripped = COORDINATE.sub("", t).strip(" |-")
                if not stripped or stripped.isdigit():
                    continue
                candidates.append(stripped)
            if candidates:
                location = max(candidates, key=len)
            elif pending_loc:
                location = pending_loc
                pending_loc = ""

        location = normalize_location_text(location or "Published camera location")
        road_group = classify_road_group(location)

        for idx, (latitude, longitude) in enumerate(coordinates, start=1):
            label = location
            if sub_index:
                label = f"{location} (Zone {sub_index})"
            elif len(coordinates) > 1:
                label = f"{location} (Camera {'AB'[idx - 1] if idx <= 2 else idx})"

            key = (category, label, latitude, longitude)
            if key in seen:
                continue
            seen.add(key)
            cameras.append(
                {
                    "id": f"{category.lower().replace(' ', '-')}-{len(cameras) + 1}",
                    "category": category,
                    "road_group": road_group,
                    "location": label,
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
