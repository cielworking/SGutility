"""One-time/incremental geocoder for LTA's 357 Commercial Carpark Rates -> data/commercial-carparks-cache.json."""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "commercial-carparks-cache.json"
LTA_RATES_URL = "https://data.gov.sg/api/action/datastore_search?resource_id=d_9f6056bdb6b1dfba57f063593e4f34ae&limit=500"
ONEMAP_URL = "https://www.onemap.gov.sg/api/common/elastic/search"


def main() -> None:
    existing: dict[str, dict] = {}
    if CACHE_PATH.exists():
        existing = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    records = requests.get(LTA_RATES_URL, timeout=30).json()["result"]["records"]
    updated = dict(existing)
    added = 0

    for rec in records:
        name = str(rec.get("carpark") or "").strip()
        if not name:
            continue
        entry = updated.get(name, {})
        if not (entry.get("lat") and entry.get("lng")):
            query = name.replace("Off-Street", "").strip()
            for attempt in range(4):
                try:
                    r = requests.get(
                        ONEMAP_URL,
                        params={"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1},
                        timeout=10,
                    )
                    if r.status_code == 429:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    if r.status_code == 200:
                        res = r.json().get("results") or []
                        if res:
                            lat = float(res[0]["LATITUDE"])
                            lng = float(res[0]["LONGITUDE"])
                            if 1.15 <= lat <= 1.50 and 103.58 <= lng <= 104.10:
                                entry = {
                                    "lat": round(lat, 6),
                                    "lng": round(lng, 6),
                                    "address": str(res[0].get("ADDRESS") or name),
                                    "postal": str(res[0].get("POSTAL") or ""),
                                }
                                added += 1
                    break
                except Exception:
                    time.sleep(1.0)
            time.sleep(0.55)

        if entry.get("lat") and entry.get("lng"):
            entry["category"] = str(rec.get("category") or "")
            entry["weekdays_rate_1"] = str(rec.get("weekdays_rate_1") or "-")
            entry["weekdays_rate_2"] = str(rec.get("weekdays_rate_2") or "-")
            entry["saturday_rate"] = str(rec.get("saturday_rate") or "-")
            entry["sunday_publicholiday_rate"] = str(rec.get("sunday_publicholiday_rate") or "-")
            updated[name] = entry

        if added and added % 25 == 0:
            CACHE_PATH.write_text(json.dumps(updated, indent=2), encoding="utf-8")

    CACHE_PATH.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    print(f"Commercial carparks cached: {len(updated)} (new geocoded: {added})")


if __name__ == "__main__":
    main()
