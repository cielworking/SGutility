import json
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = BASE_DIR / "data" / "checkpoints.json"

API_URL = "https://api.data.gov.sg/v1/transport/traffic-images"

WOODLANDS_BOX = {
    "min_lat": 1.42,
    "max_lat": 1.48,
    "min_lon": 103.74,
    "max_lon": 103.80,
}

TUAS_BOX = {
    "min_lat": 1.30,
    "max_lat": 1.37,
    "min_lon": 103.62,
    "max_lon": 103.68,
}


def in_box(location, box):
    lat = location.get("latitude")
    lon = location.get("longitude")

    return (
        lat is not None
        and lon is not None
        and box["min_lat"] <= lat <= box["max_lat"]
        and box["min_lon"] <= lon <= box["max_lon"]
    )


def main():
    res = requests.get(API_URL, timeout=20)
    res.raise_for_status()

    payload = res.json()
    cameras = payload["items"][0]["cameras"]

    woodlands = []
    tuas = []

    for cam in cameras:
        item = {
            "camera_id": cam.get("camera_id"),
            "image": cam.get("image"),
            "timestamp": cam.get("timestamp"),
            "latitude": cam.get("location", {}).get("latitude"),
            "longitude": cam.get("location", {}).get("longitude"),
        }

        if in_box(cam.get("location", {}), WOODLANDS_BOX):
            woodlands.append(item)

        if in_box(cam.get("location", {}), TUAS_BOX):
            tuas.append(item)

    data = {
        "source_name": "LTA / data.gov.sg",
        "source_url": "https://onemotoring.lta.gov.sg/content/onemotoring/home/driving/traffic_information/traffic-cameras/woodlands.html",
        "last_updated": datetime.now().isoformat(),
        "woodlands": woodlands,
        "tuas": tuas,
        "note": "Images are from official LTA traffic cameras. Jam level is visually estimated by users."
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Updated {OUTPUT_FILE}")
    print(f"Woodlands cameras: {len(woodlands)}")
    print(f"Tuas cameras: {len(tuas)}")


if __name__ == "__main__":
    main()