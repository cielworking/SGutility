"""Cache official public feeds. Each source fails independently; retain last good data."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
SGT = timezone(timedelta(hours=8))
BASE_SG = "https://api-open.data.gov.sg/v2/real-time/api/"
APIMS = "https://eqms.doe.gov.my/api3/publicmapproxy/PUBLIC_DISPLAY/CAQM_MCAQM_Current_Reading/MapServer/0/query"
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))


def get(url, **params):
    r = session.get(url, params=params, timeout=35)
    r.raise_for_status()
    return r.json()


def sg(endpoint):
    data = get(BASE_SG + endpoint)
    if data.get("code") != 0 or not data.get("data", {}).get("items"):
        raise ValueError("Missing Singapore readings")
    item = data["data"]["items"][-1]
    if endpoint == "two-hr-forecast":
        if not item.get("forecasts") or not item.get("valid_period", {}).get("end"):
            raise ValueError("Invalid Singapore forecast")
    else:
        field = "psi_twenty_four_hourly" if endpoint == "psi" else "pm25_one_hourly"
        if not item.get("readings", {}).get(field):
            raise ValueError("Invalid Singapore air-quality readings")
    return item


def malaysia_rain():
    rows = get("https://api.data.gov.my/weather/forecast", limit=10000)
    if not isinstance(rows, list) or not rows or len(rows) >= 10000:
        raise ValueError("Missing or truncated Malaysia forecast")
    for row in rows:
        if not row.get("location", {}).get("location_id") or not row.get("date"):
            raise ValueError("Invalid Malaysia forecast")
    return rows


def singapore_outlook():
    payload = get(BASE_SG + "twenty-four-hr-forecast")
    rows = payload.get("data", {}).get("records", [])
    if payload.get("code") != 0 or not rows or not rows[0].get("periods"):
        raise ValueError("Missing regional outlook")
    return rows[0]


def singapore_air_history(endpoint):
    rows = []
    today = datetime.now(SGT).date()
    for day in [today - timedelta(days=1), today]:
        payload = get(BASE_SG + endpoint, date=day.isoformat())
        if payload.get("code") != 0 or not payload.get("data", {}).get("items"):
            raise ValueError("Missing air-quality history")
        rows.extend(payload["data"]["items"])
    unique = {r["timestamp"]: r for r in rows if r.get("timestamp") and r.get("readings")}
    return sorted(unique.values(), key=lambda r: r["timestamp"])[-24:]


def malaysia_haze():
    payload = get(APIMS, f="json", outFields="STATION_ID,DATETIME,API,CLASS,STATION_LOCATION,STATE_NAME,PARAM_SELECTED,LATITUDE,LONGITUDE", returnGeometry="false", where="1=1")
    if not payload.get("features") or payload.get("exceededTransferLimit"):
        raise ValueError("Missing or truncated APIMS readings")
    result = []
    for item in payload["features"]:
        a = item["attributes"]
        # This legacy APIMS layer encodes Malaysia wall time in epoch milliseconds.
        # Match the official portal's legacy getUTC* display, then attach UTC+08.
        stamp = a.get("DATETIME")
        reported = datetime.fromtimestamp(stamp / 1000, timezone.utc).replace(tzinfo=SGT).isoformat() if stamp else None
        # Whitelist public display fields; never persist the upstream full attributes.
        result.append({"id": a["STATION_ID"], "location": a["STATION_LOCATION"], "state": a["STATE_NAME"], "api": a.get("API"), "category": a.get("CLASS"), "dominant": a.get("PARAM_SELECTED"), "reported_at": reported, "latitude": a.get("LATITUDE"), "longitude": a.get("LONGITUDE")})
    return sorted(result, key=lambda x: (x["state"], x["location"]))


def main():
    path = ROOT / "data/weather.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    sources = {
        "sg_outlook": singapore_outlook,
        "sg_rain": lambda: sg("two-hr-forecast"),
        "sg_psi": lambda: sg("psi"),
        "sg_pm25": lambda: sg("pm25"),
        "sg_psi_history": lambda: singapore_air_history("psi"),
        "sg_pm25_history": lambda: singapore_air_history("pm25"),
        "my_rain": malaysia_rain,
        "my_warnings": lambda: get("https://api.data.gov.my/weather/warning", limit=1000),
        "my_haze": malaysia_haze,
    }
    for key, fetch in sources.items():
        now = datetime.now(SGT).isoformat()
        previous = cache.get(key, {})
        try:
            data = fetch()
            if key == "my_warnings" and not isinstance(data, list):
                raise ValueError("Invalid warnings response")
            cache[key] = {"fetched_at": now, "attempted_at": now, "ok": True, "data": data}
            print(f"Updated {key}")
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            cache[key] = {**previous, "attempted_at": now, "ok": False}
            print(f"Warning: {key} unavailable ({type(error).__name__}); retaining last successful data")
    haze = cache.get("my_haze", {})
    history = cache.get("my_haze_history", {}).get("data", {})
    cutoff = (datetime.now(SGT) - timedelta(hours=48)).isoformat()
    for row in haze.get("data", []):
        value, stamp = row.get("api"), row.get("reported_at")
        if not stamp or not isinstance(value, (int, float)) or value < 0:
            continue
        readings = {r["timestamp"]: r for r in history.get(row["id"], []) if r["timestamp"] >= cutoff}
        readings[stamp] = {"timestamp": stamp, "value": value}
        history[row["id"]] = sorted(readings.values(), key=lambda r: r["timestamp"])[-49:]
    cache["my_haze_history"] = {"ok": haze.get("ok", False), "fetched_at": haze.get("fetched_at"), "data": history}
    path.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
