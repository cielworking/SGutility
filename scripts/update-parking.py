"""Fetch Singapore HDB carpark info + live lot-type availability and write data/carparks.json."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "carparks.json"
COMMERCIAL_CACHE = ROOT / "data" / "commercial-carparks-cache.json"
DIRECTORY_CACHE = ROOT / "data" / "commercial-directory-cache.json"
DIRECTORY_URL = "https://www.sgcarmart.com/news/carpark_index.php?TYP=carpark&LOC=all"
HDB_RESOURCE = "d_23f946fa557947f93a8043bbef41dd09"
HDB_INFO_URL = "https://data.gov.sg/api/action/datastore_search"
AVAILABILITY_URL = "https://api.data.gov.sg/v1/transport/carpark-availability"
SGT = timezone(timedelta(hours=8), name="SGT")

# Central Area postal/road prefixes where HDB daytime short-term car rate is $1.20/30m instead of $0.60/30m
CENTRAL_AREA_KEYWORDS = (
    "ALBERT",
    "BEACH ROAD",
    "BENCOOLEN",
    "BRAS BASAH",
    "BUGIS",
    "CHINATOWN",
    "CHURCH STREET",
    "CROSS STREET",
    "Duxton",
    "DUXTON",
    "EU TONG SEN",
    "HONG LIM",
    "KEONG SAIK",
    "KRETA AYER",
    "LAVENDER",
    "NORTH BRIDGE",
    "OPAL CRESCENT",
    "ORCHARD",
    "OUTRAM",
    "ROCHOR",
    "SELEGIE",
    "SHENTON",
    "SHORT STREET",
    "SMITH STREET",
    "SOUTH BRIDGE",
    "TANJONG PAGAR",
    "VICTORIA STREET",
    "WATERLOO",
)

# Curated verified popular commercial / town / airport motorcycle & car parking references (supplements HDB data)
CURATED_SPOTS = [
    {
        "id": "CUR-ORCHARD-CENTRAL",
        "name": "Orchard Central & 313@somerset",
        "address": "181 Orchard Road, Singapore 238896",
        "lat": 1.3008,
        "lng": 103.8396,
        "type": "SHOPPING MALL / COMMERCIAL",
        "system": "ELECTRONIC PARKING",
        "area_tier": "central",
        "sheltered": True,
        "night_parking": True,
        "gantry_height": 2.1,
        "free_sun_ph": False,
        "free_bike": False,
        "bike_friendly": True,
        "bike_rate": "$1.30–$1.50 / entry or hourly",
        "car_rate": "$2.50+ / 1st hr (Central commercial)",
        "note": "Sheltered basement & multi-storey mall parking in central Orchard.",
        "source_type": "Commercial reference",
    },
    {
        "id": "CUR-CHANGI-T3",
        "name": "Changi Airport T1 / T2 / T3 Motorcycle Park",
        "address": "Airport Boulevard, Changi Airport, Singapore 819663",
        "lat": 1.3563,
        "lng": 103.9868,
        "type": "OPEN-AIR & SHELTERED AIRPORT",
        "system": "ELECTRONIC PARKING",
        "area_tier": "standard",
        "sheltered": True,
        "night_parking": True,
        "gantry_height": 2.2,
        "free_sun_ph": False,
        "free_bike": True,
        "bike_friendly": True,
        "bike_rate": "Designated motorcycle bays (~$1.30/day cap or free grace)",
        "car_rate": "$0.04 / min (10-min free grace)",
        "note": "Dedicated rider bays outside T1/T2/T3; check current airport gantry signage.",
        "source_type": "Commercial reference",
    },
    {
        "id": "CUR-SUNTEC",
        "name": "Suntec City Carpark (East / West Atrium)",
        "address": "3 Temasek Boulevard, Singapore 038983",
        "lat": 1.2935,
        "lng": 103.8572,
        "type": "COMMERCIAL BASEMENT",
        "system": "ELECTRONIC PARKING",
        "area_tier": "central",
        "sheltered": True,
        "night_parking": True,
        "gantry_height": 2.2,
        "free_sun_ph": False,
        "free_bike": False,
        "bike_friendly": True,
        "bike_rate": "~$1.30 / entry (check gantry board)",
        "car_rate": "~$2.40 / 1st hr, cheaper after 5pm",
        "note": "Wide basement lanes near Promenade MRT; popular CBD rider & driver option.",
        "source_type": "Commercial reference",
    },
    {
        "id": "CUR-VIVOCITY",
        "name": "VivoCity / HarbourFront",
        "address": "1 HarbourFront Walk, Singapore 098585",
        "lat": 1.2644,
        "lng": 103.8222,
        "type": "MALL / HARBOURFRONT",
        "system": "ELECTRONIC PARKING",
        "area_tier": "central",
        "sheltered": True,
        "night_parking": True,
        "gantry_height": 2.2,
        "free_sun_ph": False,
        "free_bike": False,
        "bike_friendly": True,
        "bike_rate": "~$1.30 / entry (dedicated bike zone)",
        "car_rate": "Per-hour / per-entry commercial mall rate",
        "note": "Large sheltered car & motorcycle zones; Sentosa gateway.",
        "source_type": "Commercial reference",
    },
    {
        "id": "CUR-ONENORTH-FUSIONOPOLIS",
        "name": "Fusionopolis / one-north",
        "address": "1 Fusionopolis Way, Singapore 138632",
        "lat": 1.2991,
        "lng": 103.7876,
        "type": "BUSINESS PARK BASEMENT",
        "system": "ELECTRONIC PARKING",
        "area_tier": "standard",
        "sheltered": True,
        "night_parking": True,
        "gantry_height": 2.2,
        "free_sun_ph": False,
        "free_bike": False,
        "bike_friendly": True,
        "bike_rate": "~$1.10–$1.30 / entry",
        "car_rate": "Commercial per-min / per-entry",
        "note": "Tech-hub parking with covered access to one-north MRT.",
        "source_type": "Commercial reference",
    },
    {
        "id": "CUR-JURONG-JEM-WESTGATE",
        "name": "Jurong East Mall Cluster (JEM / Westgate / IMM)",
        "address": "50 Jurong Gateway Road, Singapore 608549",
        "lat": 1.3332,
        "lng": 103.7431,
        "type": "REGIONAL MALL / HDB",
        "system": "ELECTRONIC PARKING",
        "area_tier": "standard",
        "sheltered": True,
        "night_parking": True,
        "gantry_height": 2.2,
        "free_sun_ph": False,
        "free_bike": False,
        "bike_friendly": True,
        "bike_rate": "~$1.30 / entry (IMM offers free 1st hr car promos)",
        "car_rate": "Regional mall rate (nearby HDB at $0.60/30m)",
        "note": "Compare mall rate against nearby HDB surface/MSCP lots before parking.",
        "source_type": "Commercial reference",
    },
    {
        "id": "CUR-AZ-PAYA-LEBAR",
        "name": "AZ @ Paya Lebar",
        "address": "140 Paya Lebar Road, Singapore 409015",
        "lat": 1.327314,
        "lng": 103.890849,
        "type": "COMMERCIAL / MULTI-STOREY CARPARK",
        "system": "ELECTRONIC PARKING",
        "area_tier": "standard",
        "sheltered": True,
        "night_parking": True,
        "gantry_height": 2.1,
        "free_sun_ph": False,
        "free_bike": False,
        "bike_friendly": True,
        "bike_rate": "Check gantry signage (nearby HDB bike lots at Blk 76A Circuit Rd)",
        "car_rate": "Commercial gantry rate (Levels 1–4; season parking Levels 2–3)",
        "note": "Multi-storey commercial carpark opposite MacPherson MRT near PIE.",
        "source_type": "Commercial reference",
    },
]


def svy21_to_wgs84(northing: float, easting: float) -> tuple[float, float]:
    """Convert Singapore SVY21 (Y=Northing, X=Easting) to WGS84 (lat, lng)."""
    a = 6378137.0
    f = 1.0 / 298.257223563
    o_lat = math.radians(1.366666)
    o_lon = math.radians(103.833333)
    no = 38744.572
    eo = 28001.642
    k = 1.0

    b = a * (1.0 - f)
    e2 = 2.0 * f - f * f
    e4 = e2 * e2
    e6 = e4 * e2
    n = (a - b) / (a + b)
    n2 = n * n
    n3 = n2 * n
    n4 = n2 * n2

    g_term = a * (1.0 - n) * (1.0 - n2) * (1.0 + (9.0 / 4.0) * n2 + (225.0 / 64.0) * n4)
    a0 = 1.0 - (e2 / 4.0) - (3.0 * e4 / 64.0) - (5.0 * e6 / 256.0)
    a2 = (3.0 / 8.0) * (e2 + (e4 / 4.0) + (15.0 * e6 / 128.0))
    a4 = (15.0 / 256.0) * (e4 + (3.0 * e6 / 4.0))
    a6 = (35.0 * e6) / 3072.0

    def meridian_arc(lat_rad: float) -> float:
        return a * (
            a0 * lat_rad
            - a2 * math.sin(2.0 * lat_rad)
            + a4 * math.sin(4.0 * lat_rad)
            - a6 * math.sin(6.0 * lat_rad)
        )

    m_o = meridian_arc(o_lat)
    dn = northing - no
    de = easting - eo
    m_prime = m_o + dn / k
    sigma = (m_prime * math.pi) / (180.0 * g_term) * (180.0 / math.pi)

    lat_prime = (
        sigma
        + ((3.0 * n / 2.0) - (27.0 * n3 / 32.0)) * math.sin(2.0 * sigma)
        + ((21.0 * n2 / 16.0) - (55.0 * n4 / 32.0)) * math.sin(4.0 * sigma)
        + (151.0 * n3 / 96.0) * math.sin(6.0 * sigma)
        + (1097.0 * n4 / 512.0) * math.sin(8.0 * sigma)
    )

    sin_l = math.sin(lat_prime)
    sin2_l = sin_l * sin_l
    cos_l = math.cos(lat_prime)
    tan_l = math.tan(lat_prime)
    tan2_l = tan_l * tan_l
    tan4_l = tan2_l * tan2_l
    tan6_l = tan4_l * tan2_l

    rho = a * (1.0 - e2) / math.pow(1.0 - e2 * sin2_l, 1.5)
    nu = a / math.sqrt(1.0 - e2 * sin2_l)
    psi = nu / rho
    psi2 = psi * psi
    psi3 = psi2 * psi
    psi4 = psi3 * psi

    t = de / (k * nu)
    t2 = t * t
    t3 = t2 * t
    t4 = t3 * t
    t5 = t4 * t
    t6 = t5 * t
    t7 = t6 * t

    lat_rad = (
        lat_prime
        - (tan_l / (k * rho)) * (t * de / 2.0)
        + (tan_l / (k * rho)) * (t3 * de / 24.0) * (-4.0 * psi2 + 9.0 * psi * (1.0 - tan2_l) + 12.0 * tan2_l)
        - (tan_l / (k * rho)) * (t5 * de / 720.0)
        * (
            8.0 * psi4 * (11.0 - 24.0 * tan2_l)
            - 12.0 * psi3 * (21.0 - 71.0 * tan2_l)
            + 15.0 * psi2 * (15.0 - 98.0 * tan2_l + 15.0 * tan4_l)
            + 180.0 * psi * (5.0 * tan2_l - 3.0 * tan4_l)
            + 360.0 * tan4_l
        )
        + (tan_l / (k * rho)) * (t7 * de / 40320.0) * (1385.0 + 3633.0 * tan2_l + 4095.0 * tan4_l + 1575.0 * tan6_l)
    )

    sec_l = 1.0 / cos_l
    lon_rad = (
        o_lon
        + t * sec_l
        - (t3 * sec_l / 6.0) * (psi + 2.0 * tan2_l)
        + (t5 * sec_l / 120.0) * (-4.0 * psi3 * (1.0 - 6.0 * tan2_l) + psi2 * (9.0 - 68.0 * tan2_l) + 72.0 * psi * tan2_l + 24.0 * tan4_l)
        - (t7 * sec_l / 5040.0) * (61.0 + 662.0 * tan2_l + 1320.0 * tan4_l + 720.0 * tan6_l)
    )

    return round(math.degrees(lat_rad), 6), round(math.degrees(lon_rad), 6)


def fetch_all_hdb_carparks() -> list[dict]:
    records: list[dict] = []
    offset = 0
    limit = 1000
    while True:
        resp = requests.get(
            HDB_INFO_URL,
            params={"resource_id": HDB_RESOURCE, "limit": limit, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()["result"]
        batch = payload.get("records") or []
        records.extend(batch)
        if len(batch) < limit or len(records) >= int(payload.get("total") or 0):
            break
        offset += limit
    return records


def fetch_live_availability() -> tuple[str, dict[str, dict]]:
    resp = requests.get(AVAILABILITY_URL, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("items") or []
    if not items:
        return datetime.now(SGT).isoformat(), {}
    item = items[0]
    ts = item.get("timestamp") or datetime.now(SGT).isoformat()
    by_no: dict[str, dict] = {}
    for entry in item.get("carpark_data") or []:
        cp_no = str(entry.get("carpark_number") or "").strip().upper()
        if not cp_no:
            continue
        lots: dict[str, dict[str, int]] = {}
        for info in entry.get("carpark_info") or []:
            lt = str(info.get("lot_type") or "").strip().upper()
            if lt:
                lots[lt] = {
                    "avail": int(info.get("lots_available") or 0),
                    "total": int(info.get("total_lots") or 0),
                }
        by_no[cp_no] = lots
    return ts, by_no


def fetch_commercial_directory() -> list[dict]:
    """Fetch 1,100+ Singapore commercial/mall/office/industrial carparks and cache locally."""
    try:
        resp = requests.get(DIRECTORY_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        m = re.search(r'(\[\{"id":\d+,"name":.*?\}\])', resp.text, re.S)
        if m:
            records = json.loads(m.group(1))
            if isinstance(records, list) and len(records) >= 500:
                DIRECTORY_CACHE.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")
                return records
    except Exception as exc:
        print(f"Warning: commercial directory fetch failed ({exc}); using cached copy.")

    if DIRECTORY_CACHE.exists():
        try:
            return json.loads(DIRECTORY_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def build_dataset() -> dict:
    hdb_rows = fetch_all_hdb_carparks()
    live_ts, live_map = fetch_live_availability()

    carparks: list[dict] = []
    for row in hdb_rows:
        code = str(row.get("car_park_no") or "").strip().upper()
        address = str(row.get("address") or "").strip()
        try:
            x = float(row["x_coord"])
            y = float(row["y_coord"])
            lat, lng = svy21_to_wgs84(y, x)
        except (KeyError, TypeError, ValueError):
            continue
        if not (1.15 <= lat <= 1.50 and 103.58 <= lng <= 104.10):
            continue

        cp_type = str(row.get("car_park_type") or "").strip()
        free_str = str(row.get("free_parking") or "").strip().upper()
        free_sun_ph = free_str != "NO" and bool(free_str)
        night_parking = str(row.get("night_parking") or "").strip().upper() == "YES"
        sheltered = ("MULTI-STOREY" in cp_type.upper()) or ("BASEMENT" in cp_type.upper())
        area_tier = "central" if any(k.upper() in address.upper() for k in CENTRAL_AREA_KEYWORDS) else "standard"
        try:
            gantry_h = round(float(row.get("gantry_height") or 0), 2)
        except (TypeError, ValueError):
            gantry_h = 0.0

        live_lots = live_map.get(code, {})
        has_car_live = "C" in live_lots
        has_bike_live = "Y" in live_lots

        carparks.append(
            {
                "id": code,
                "name": address,
                "address": address,
                "lat": lat,
                "lng": lng,
                "type": cp_type,
                "system": str(row.get("type_of_parking_system") or "").strip(),
                "short_term": str(row.get("short_term_parking") or "").strip(),
                "free_parking_raw": free_str or "NO",
                "free_sun_ph": free_sun_ph,
                "free_bike": False,
                "night_parking": night_parking,
                "sheltered": sheltered,
                "gantry_height": gantry_h,
                "area_tier": area_tier,
                "bike_rate": "$0.10 / 30 min ($0.65 cap/session · Free Sun & PH 7am–10:30pm)" if free_sun_ph else "$0.10 / 30 min ($0.65 cap/day or night session)",
                "car_rate": "$1.20 / 30m (Mon–Sat 7am–5pm), $0.60 / 30m off-peak" if area_tier == "central" else "$0.60 / 30m ($5 night cap 10:30pm–7am)",
                "has_car_live": has_car_live,
                "has_bike_live": has_bike_live,
                "live": live_lots,
                "source_type": "HDB / data.gov.sg",
            }
        )

    if COMMERCIAL_CACHE.exists():
        commercial = json.loads(COMMERCIAL_CACHE.read_text(encoding="utf-8"))
        for idx, (name, info) in enumerate(sorted(commercial.items()), start=1):
            lat = info.get("lat")
            lng = info.get("lng")
            if not (lat and lng):
                continue
            addr = str(info.get("address") or name)
            sun_rate = str(info.get("sunday_publicholiday_rate") or "-")
            sat_rate = str(info.get("saturday_rate") or "-")
            wk1 = str(info.get("weekdays_rate_1") or "-")
            wk2 = str(info.get("weekdays_rate_2") or "-")
            sun_free = "free" in sun_rate.lower()
            area_tier = "central" if ("central" in str(info.get("category") or "").lower() and any(k.upper() in addr.upper() for k in CENTRAL_AREA_KEYWORDS)) else "standard"
            carparks.append(
                {
                    "id": f"MALL-{idx}",
                    "name": name,
                    "address": addr,
                    "postal": str(info.get("postal") or ""),
                    "lat": lat,
                    "lng": lng,
                    "type": "COMMERCIAL / SHOPPING MALL",
                    "system": "ELECTRONIC PARKING",
                    "short_term": "COMMERCIAL SCHEDULE",
                    "free_parking_raw": "COMMERCIAL SUN FREE" if sun_free else "COMMERCIAL",
                    "free_sun_ph": sun_free,
                    "free_bike": False,
                    "night_parking": True,
                    "sheltered": True,
                    "gantry_height": 2.1,
                    "area_tier": area_tier,
                    "weekday_rate": wk1,
                    "weekday_rate_2": wk2,
                    "saturday_rate": sat_rate,
                    "sunday_rate": sun_rate,
                    "bike_rate": "Commercial gantry rate (check mall signage)",
                    "car_rate": wk1,
                    "has_car_live": False,
                    "has_bike_live": False,
                    "live": {},
                    "source_type": "LTA Commercial Rates",
                }
            )

    for spot in CURATED_SPOTS:
        carparks.append(
            {
                "id": spot["id"],
                "name": spot["name"],
                "address": spot["address"],
                "lat": spot["lat"],
                "lng": spot["lng"],
                "type": spot["type"],
                "system": spot["system"],
                "short_term": "WHOLE DAY",
                "free_parking_raw": "FREE BIKE / COMMERCIAL" if spot["free_bike"] else "COMMERCIAL",
                "free_sun_ph": spot["free_sun_ph"],
                "free_bike": spot["free_bike"],
                "night_parking": spot["night_parking"],
                "sheltered": spot["sheltered"],
                "gantry_height": spot["gantry_height"],
                "area_tier": spot["area_tier"],
                "bike_rate": spot["bike_rate"],
                "car_rate": spot["car_rate"],
                "has_car_live": False,
                "has_bike_live": False,
                "live": {},
                "note": spot["note"],
                "source_type": spot["source_type"],
            }
        )

    existing_names = {re.sub(r"[^a-z0-9]", "", str(c.get("name") or "").lower()) for c in carparks}
    for entry in fetch_commercial_directory():
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        norm = re.sub(r"[^a-z0-9]", "", name.lower())
        if not norm or norm in existing_names:
            continue
        try:
            lat = round(float(entry["latitude"]), 6)
            lng = round(float(entry["longitude"]), 6)
        except (KeyError, TypeError, ValueError):
            continue
        if not (1.15 <= lat <= 1.50 and 103.58 <= lng <= 104.10):
            continue
        existing_names.add(norm)
        road = str(entry.get("road") or "").strip()
        addr = f"{name}, {road}" if road and road.lower() not in name.lower() else name
        area_tier = "central" if any(k.upper() in addr.upper() for k in CENTRAL_AREA_KEYWORDS) else "standard"
        carparks.append(
            {
                "id": f"SGCM-{entry.get('id')}",
                "name": name,
                "address": addr,
                "lat": lat,
                "lng": lng,
                "type": "COMMERCIAL / BUILDING",
                "system": "ELECTRONIC PARKING",
                "short_term": "COMMERCIAL SCHEDULE",
                "free_parking_raw": "COMMERCIAL",
                "free_sun_ph": False,
                "free_bike": False,
                "night_parking": True,
                "sheltered": True,
                "gantry_height": 2.1,
                "area_tier": area_tier,
                "bike_rate": "Commercial gantry rate (check building signage)",
                "car_rate": "Commercial gantry rate (check building signage)",
                "has_car_live": False,
                "has_bike_live": False,
                "live": {},
                "source_type": "SG Commercial Directory",
            }
        )

    return {
        "source_name": "HDB, LTA & SG Commercial Directory",
        "last_updated": live_ts,
        "counts": {
            "total": len(carparks),
            "hdb": len(hdb_rows),
            "live_car_feeds": sum(1 for c in carparks if c["has_car_live"]),
            "live_bike_feeds": sum(1 for c in carparks if c["has_bike_live"]),
            "free_sun_ph": sum(1 for c in carparks if c["free_sun_ph"]),
        },
        "carparks": carparks,
    }


def main() -> None:
    payload = build_dataset()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {payload['counts']['total']} carparks to {OUTPUT}")


if __name__ == "__main__":
    main()
