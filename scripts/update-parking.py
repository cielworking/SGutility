"""Fetch Singapore HDB carpark info + live lot-type availability and write data/carparks.json."""

from __future__ import annotations

import html
import json
import math
import re
import subprocess
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "carparks.json"
COMMERCIAL_CACHE = ROOT / "data" / "commercial-carparks-cache.json"
DIRECTORY_CACHE = ROOT / "data" / "commercial-directory-cache.json"
MOTORIST_CACHE = ROOT / "data" / "motorist-rates-cache.json"
BIKEPARKING_CACHE = ROOT / "data" / "bikeparking-cache.json"
DIRECTORY_URL = "https://www.sgcarmart.com/news/carpark_index.php?TYP=carpark&LOC=all"
ONEMOTORING_URLS = [
    f"https://onemotoring.lta.gov.sg/content/onemotoring/home/owning/ongoing-car-costs/parking/parking_rates.{i}.html"
    for i in range(1, 7)
]
HDB_RESOURCE = "d_23f946fa557947f93a8043bbef41dd09"
HDB_INFO_URL = "https://data.gov.sg/api/action/datastore_search"
AVAILABILITY_URL = "https://api.data.gov.sg/v1/transport/carpark-availability"
SGT = timezone(timedelta(hours=8), name="SGT")

# Verified 9% GST overrides & malls where community directories lag GST updates.
# Tuple: (rate_text, free_bike_bool)
COMMERCIAL_BIKE_RATES: dict[str, tuple[str, bool]] = {
    "ionorchard": ("$4.36 / entry (8am–7:59am next day, Mon–Sun & PH)", False),
    "citysquaremall": ("$2.18 / entry (20 mins grace)", False),
    "theadelphi": ("$1.02 / entry (6am–6am next day, 10m grace)", False),
    "sunteccity": ("Free motorcycle parking (designated basement lots)", True),
    "sunteccitymall": ("Free motorcycle parking (designated basement lots)", True),
    "esplanade": ("Free all-day motorcycle parking (designated zone)", True),
    "theesplanade": ("Free all-day motorcycle parking (designated zone)", True),
    "esplanademall": ("Free all-day motorcycle parking (designated zone)", True),
    "concordehotel": ("Free motorcycle parking (designated bike zone)", True),
    "concordehotelshoppingmall": ("Free motorcycle parking (designated bike zone)", True),
    "kallangwavemall": ("Free motorcycle parking (Singapore Sports Hub)", True),
    "singaporesportshub": ("Free motorcycle parking (Singapore Sports Hub)", True),
    "ikeatampines": ("Free motorcycle parking (7am–11pm)", True),
    "ikeaalexandra": ("Free motorcycle parking (operating hours)", True),
    "singaporeexpo": ("Free motorcycle parking", True),
    "kinex": ("Free motorcycle parking", True),
    "ehubdowntowneast": ("Free motorcycle parking", True),
    "queenswayshoppingcentre": ("Free motorcycle parking", True),
    "vivocity": ("$1.31 / entry (dedicated bike zone)", False),
    "plazasingapura": ("$1.31 / entry (15 mins grace)", False),
    "ngeeanncity": ("$1.64 / entry", False),
    "singaporemarriotthotel": ("$3.27 / entry (Tang Plaza / Marriott gantry)", False),
    "tangs": ("$3.27 / entry (Tang Plaza / Marriott gantry)", False),
    "jewelchangiairport": ("$1.31 / day cap (designated airport bike bays)", False),
    "changiairport": ("$1.31 / day cap (designated airport bike bays)", False),
}

NAME_ALIASES = {
    "111somerset": "tripleonesomerset",
    "tripleonesomerset": "111somerset",
    "aperiamall": "aperia",
    "aperia": "aperiamall",
    "funanmall": "funan",
    "funan": "funanmall",
    "greatworldcity": "greatworld",
    "greatworld": "greatworldcity",
    "bugisplus": "bugis",
    "plqmall": "payalebarquarterplq1",
    "payalebarquarter": "payalebarquarterplq1",
    "ehub": "ehubdowntowneast",
    "theesplanade": "esplanade",
    "marinasquare": "marinasquares",
    "takashimayangeeanncity": "ngeeanncity",
    "sportsg": "singaporesportshub",
}

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
        "free_bike": True,
        "bike_friendly": True,
        "bike_rate": "Free motorcycle parking (designated basement lots)",
        "car_rate": "$2.40 / 1st hr, cheaper after 5pm (check gantry)",
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


class _OneMotoringTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_td = False
        self.rows: list[list[str]] = []
        self.current_row: list[str] = []
        self.current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t == "tr":
            self.current_row = []
        elif t in ("td", "th"):
            self.in_td = True
            self.current_cell = []
        elif t == "br" and self.in_td:
            self.current_cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self.in_td:
            text = re.sub(r"\s+", " ", html.unescape("".join(self.current_cell))).strip()
            self.current_row.append(text)
            self.in_td = False
        elif t == "tr" and self.current_row:
            self.rows.append(self.current_row)
            self.current_row = []

    def handle_data(self, data: str) -> None:
        if self.in_td:
            self.current_cell.append(data)


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _tok_key(name: str) -> str:
    return "".join(sorted(re.findall(r"[a-z0-9]+", str(name or "").lower())))


def _candidate_keys(name: str) -> list[str]:
    clean = str(name or "").strip()
    no_paren = re.sub(r"\([^)]*\)", "", clean).strip()
    k1 = _norm_key(clean)
    k2 = _norm_key(no_paren)
    keys = []
    for k in (k1, k2, NAME_ALIASES.get(k1, ""), NAME_ALIASES.get(k2, "")):
        if k and k not in keys:
            keys.append(k)
    return keys


def fetch_sgbikeparking_rates() -> dict[str, dict]:
    """Fetch commercial motorcycle parking rates & no-motorcycle lists from sgbikeparking.com WP REST API via curl."""
    try:
        from bs4 import BeautifulSoup
        all_pages = []
        for page_num in (1, 2, 3):
            res = subprocess.run(
                [
                    "curl", "-s", "-L", "--max-time", "20",
                    "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    f"https://www.sgbikeparking.com/wp-json/wp/v2/pages?per_page=100&page={page_num}&_fields=id,slug,title,modified,content",
                ],
                capture_output=True, text=True, encoding="utf-8", errors="ignore",
            )
            if res.stdout.strip().startswith("["):
                all_pages.extend(json.loads(res.stdout))

        if len(all_pages) >= 50:
            entries: dict[str, dict] = {}
            free_list, no_list = [], []
            for p in all_pages:
                slug = p.get("slug", "")
                soup = BeautifulSoup(p["content"]["rendered"], "html.parser")
                if slug == "free-motorcycle-parking-in-singapore":
                    free_list = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in soup.find_all("td") if td.get_text(strip=True)]
                    continue
                if slug == "no-motorcycle-parking-in-singapore":
                    no_list = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in soup.find_all("td") if td.get_text(strip=True)]
                    continue
                if not slug.endswith("-motorcycle-parking"):
                    continue
                raw_title = re.sub(r"\s*Motorcycle Parking.*$", "", soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else p["title"]["rendered"], flags=re.I)
                name = re.sub(r"\s*\([^)]*\)$", "", raw_title).strip()
                rows = []
                for tr in soup.find_all("tr"):
                    cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
                    if cells and not any("motorcycle parking rate" in c.lower() for c in cells):
                        rows.append(cells)
                full_txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
                is_no = "no motorcycle parking" in full_txt.lower()
                is_free = (not is_no) and ("free motorcycle parking" in full_txt.lower())
                entries[_norm_key(name)] = {
                    "name": name,
                    "slug": slug,
                    "modified": p.get("modified", "")[:10],
                    "no_moto": is_no,
                    "free_bike": is_free,
                    "rows": rows,
                }
            for n in free_list:
                clean_n = re.sub(r"\s*\([^)]*\)", "", n).strip()
                k = _norm_key(clean_n)
                if k not in entries:
                    entries[k] = {"name": clean_n, "slug": "", "modified": "2025-05-28", "no_moto": False, "free_bike": True, "rows": [["All Days", "Free Motorcycle Parking"]]}
                else:
                    entries[k]["free_bike"] = True
            for n in no_list:
                clean_n = re.sub(r"\s*\([^)]*\)", "", n).strip()
                k = _norm_key(clean_n)
                if k not in entries:
                    entries[k] = {"name": clean_n, "slug": "", "modified": "2025-05-28", "no_moto": True, "free_bike": False, "rows": [["Status", "No Motorcycle Parking"]]}
                else:
                    entries[k]["no_moto"] = True
            BIKEPARKING_CACHE.write_text(json.dumps({"entries": entries}, separators=(",", ":")), encoding="utf-8")
            print(f"Refreshed {len(entries)} live sgbikeparking.com entries.")
            return entries
    except Exception as exc:
        print(f"Warning: sgbikeparking live fetch skipped ({exc}); using cache.")

    if BIKEPARKING_CACHE.exists():
        try:
            return json.loads(BIKEPARKING_CACHE.read_text(encoding="utf-8")).get("entries") or {}
        except Exception:
            return {}
    return {}


def _format_bikeparking_rows(entry: dict) -> str:
    rows = entry.get("rows") or []
    parts = []
    skip_next_remark = False
    for r in rows:
        txt = " · ".join(r).strip()
        low = txt.lower()
        if not txt:
            continue
        if low == "remarks":
            skip_next_remark = True
            continue
        if skip_next_remark:
            if "grace" in low:
                m_g = re.search(r"grace period:\s*([^\n]+)", txt, re.I)
                if m_g:
                    parts.append(f"Grace: {m_g.group(1).strip()}")
            skip_next_remark = False
            continue
        if any(k in low for k in ("s$", "$", "free", "hdb", "no motorcycle", "entry", "hour", "min")):
            clean = re.sub(r"\bS\$", "$", txt).replace("Mondays – Sundays & Public Holidays", "").replace("Monday – Sunday & Public Holiday", "").strip(" ·")
            if clean:
                parts.append(clean)
    return " · ".join(parts[:2]) or "Commercial bike rate (check signage)"


def lookup_bike_info(name: str, bike_entries: dict[str, dict], mot_entry: dict | None) -> tuple[str | None, bool, bool]:
    """Return (bike_rate_str, is_free_bike, no_moto_parking)."""
    keys = _candidate_keys(name)
    for k in keys:
        if k in COMMERCIAL_BIKE_RATES:
            rate, is_free = COMMERCIAL_BIKE_RATES[k]
            return rate, is_free, False

    for k in keys:
        if k in bike_entries:
            ent = bike_entries[k]
            if ent.get("no_moto"):
                return "No Motorcycle Parking (try nearby HDB/URA lots)", False, True
            if ent.get("free_bike"):
                return "Free Motorcycle Parking", True, False
            return _format_bikeparking_rows(ent), False, False

    if mot_entry and mot_entry.get("moto_rows"):
        formatted = _format_motorist_rows(mot_entry["moto_rows"])
        if formatted.get("weekdays_rate_1") and formatted["weekdays_rate_1"] != "-":
            r = formatted["weekdays_rate_1"]
            is_free = "free" in r.lower() and "$" not in r
            return r, is_free, False

    return None, False, False


def _format_motorist_rows(rows: list[list[str]]) -> dict[str, str]:
    """Convert Motorist [day, rate] rows into clean structured schedule fields."""
    wk_parts, sat_parts, sun_parts = [], [], []
    for day, rate in rows:
        d_low = day.lower()
        clean_r = re.sub(r"\b(\d+)\s*mins?\s*grace period;\s*", r"\1m grace · ", rate, flags=re.I)
        clean_r = re.sub(r"\b(\d+)\s*hours?\s*grace period;\s*", r"\1h grace · ", clean_r, flags=re.I)
        clean_r = re.sub(r"(?:^|;\s*)(?:mins?|hours?|hr)\s*grace period;\s*", "", clean_r, flags=re.I)
        clean_r = (
            clean_r.replace("12:00 AM - 12:00 AM ", "24h: ")
            .replace("07:00 AM - 06:59 AM ", "24h: ")
            .replace("First hour", "1st hr")
            .replace("First 30 mins", "1st 30m")
            .replace("Subsequent", "Sub.")
            .replace("per 30 mins", "/ 30m")
            .replace("Per 30 mins", "/ 30m")
            .replace("per hour", "/ hr")
            .replace("Per hour", "/ hr")
            .replace("per entry", "/ entry")
            .replace("Per entry", "/ entry")
            .replace("per min", "/ min")
            .replace("Per min", "/ min")
        )
        entry = f"{day}: {clean_r}" if any(x in d_low for x in ("mon - thu", "mon - fri", "fri - sun")) else clean_r
        if "mon - sun" in d_low or "daily" in d_low:
            if len(wk_parts) < 3:
                wk_parts.append(entry)
        elif "sat" in d_low and "mon" not in d_low:
            if len(sat_parts) < 2:
                sat_parts.append(entry)
        elif "sun" in d_low or "ph" in d_low:
            if len(sun_parts) < 2:
                sun_parts.append(entry)
        else:
            if len(wk_parts) < 3:
                wk_parts.append(entry)

    all_daily = any("mon - sun" in d.lower() or "fri - sun" in d.lower() for d, _ in rows)
    wk1 = "; ".join(wk_parts) if wk_parts else "-"
    sat = "; ".join(sat_parts) if sat_parts else ("Same as weekdays" if (all_daily or not sat_parts and wk_parts) else "-")
    sun = "; ".join(sun_parts) if sun_parts else ("Same as weekdays" if all_daily else ("Same as Saturday" if sat_parts else "-"))
    return {
        "weekdays_rate_1": wk1,
        "weekdays_rate_2": "-",
        "saturday_rate": sat,
        "sunday_publicholiday_rate": sun,
    }


def fetch_motorist_rates(refresh_budget: int = 25) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """Load Motorist.sg 9% GST commercial rates cache & gently refresh oldest entries."""
    items: dict[str, dict] = {}
    if MOTORIST_CACHE.exists():
        try:
            items = json.loads(MOTORIST_CACHE.read_text(encoding="utf-8")).get("items") or {}
        except Exception:
            items = {}

    # Refresh a small rolling slice on live runs if bs4 is available
    if refresh_budget > 0:
        try:
            from bs4 import BeautifulSoup
            h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            sess = requests.Session()
            sess.headers.update(h)
            stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            oldest = [v for v in sorted(items.values(), key=lambda x: x.get("fetched_at", "")) if v.get("fetched_at", "") < stale_cutoff][:refresh_budget]
            refreshed = 0
            for ent in oldest:
                url = ent.get("url")
                if not url:
                    continue
                resp = sess.get(url, timeout=10)
                if resp.status_code != 200:
                    continue
                sp = BeautifulSoup(resp.text, "html.parser")
                cur_sec = "car"
                saw_moto = False
                car_rows, moto_rows = [], []
                for el in sp.find_all(["h2", "h3", "table"]):
                    if el.name in ("h2", "h3"):
                        ht = el.get_text(" ", strip=True).lower()
                        if "motorcycle" in ht:
                            cur_sec = "motorcycle"
                        elif ht == "car":
                            cur_sec = "car"
                        else:
                            cur_sec = "other"
                    elif el.name == "table":
                        ths = [c.get_text(" ", strip=True) for c in el.find_all("th")]
                        if "Day" not in ths and "Rates" not in ths:
                            continue
                        cur_d, parsed = "", []
                        for tr in el.find_all("tr"):
                            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all("td")]
                            if len(cells) >= 2:
                                cur_d = cells[0]
                                parsed.append([cur_d, cells[1]])
                            elif len(cells) == 1 and cur_d:
                                parsed.append([cur_d, cells[0]])
                        if parsed and cur_sec == "car":
                            car_rows.extend(parsed)
                            cur_sec = "other"
                        elif parsed and cur_sec == "motorcycle" and not saw_moto:
                            moto_rows.extend(parsed)
                            saw_moto = True
                            cur_sec = "other"
                if car_rows:
                    ent["car_rows"] = car_rows
                if moto_rows:
                    ent["moto_rows"] = moto_rows
                ent["fetched_at"] = datetime.now(timezone.utc).isoformat()
                refreshed += 1
            if refreshed:
                MOTORIST_CACHE.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "items": items}, separators=(",", ":")), encoding="utf-8")
        except Exception as exc:
            print(f"Warning: Motorist incremental refresh skipped ({exc}).")

    by_norm: dict[str, dict] = {}
    by_tok: dict[str, dict] = {}
    by_postal: dict[str, dict] = {}
    for ent in items.values():
        n = ent.get("name") or ""
        nk = _norm_key(n)
        if nk:
            by_norm[nk] = ent
        tk = _tok_key(n)
        if tk and tk not in by_tok:
            by_tok[tk] = ent
        p = str(ent.get("postal") or "").strip()
        if p and p not in by_postal:
            by_postal[p] = ent
    return by_norm, by_tok, by_postal


def lookup_motorist_entry(name: str, postal: str, by_norm: dict, by_tok: dict, by_postal: dict) -> dict | None:
    p = str(postal or "").strip()
    if p and p in by_postal:
        return by_postal[p]
    for k in _candidate_keys(name):
        if k in by_norm:
            return by_norm[k]
    tk = _tok_key(re.sub(r"\([^)]*\)", "", str(name or "")))
    if tk and tk in by_tok:
        return by_tok[tk]
    return None


def fetch_onemotoring_rates() -> dict[str, dict[str, str]]:
    """Fetch live 9% GST commercial carpark rates from LTA OneMotoring's 6 regional tables."""
    rates_by_norm: dict[str, dict[str, str]] = {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SGAlertsBot/1.0; +https://sgalerts.com)"}
    for url in ONEMOTORING_URLS:
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            parser = _OneMotoringTableParser()
            parser.feed(resp.text)
            for row in parser.rows:
                if len(row) < 5:
                    continue
                cp_name = row[0].strip()
                if not cp_name or cp_name.lower() == "car park":
                    continue
                rec = {
                    "name": cp_name,
                    "weekdays_rate_1": row[1] or "-",
                    "weekdays_rate_2": row[2] or "-",
                    "saturday_rate": row[3] or "-",
                    "sunday_publicholiday_rate": row[4] or "-",
                }
                k_full = _norm_key(cp_name)
                if k_full:
                    rates_by_norm[k_full] = rec
                k_base = _norm_key(re.sub(r"\([^)]*\)", "", cp_name))
                if k_base and k_base not in rates_by_norm:
                    rates_by_norm[k_base] = rec
        except Exception as exc:
            print(f"Warning: OneMotoring fetch failed for {url} ({exc})")
    return rates_by_norm


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

    onemotoring_rates = fetch_onemotoring_rates()
    if onemotoring_rates:
        print(f"Fetched {len(onemotoring_rates)} live LTA OneMotoring commercial carpark rate entries.")
    mot_by_norm, mot_by_tok, mot_by_postal = fetch_motorist_rates(refresh_budget=25)
    print(f"Loaded {len(mot_by_norm)} Motorist.sg 9% GST commercial rate entries.")
    bike_entries = fetch_sgbikeparking_rates()
    print(f"Loaded {len(bike_entries)} sgbikeparking.com motorcycle rate entries.")

    if COMMERCIAL_CACHE.exists():
        commercial = json.loads(COMMERCIAL_CACHE.read_text(encoding="utf-8"))
        updated_cache = False
        for idx, (name, info) in enumerate(sorted(commercial.items()), start=1):
            lat = info.get("lat")
            lng = info.get("lng")
            if not (lat and lng):
                continue
            postal = str(info.get("postal") or "")
            live_om = onemotoring_rates.get(_norm_key(name)) or onemotoring_rates.get(_norm_key(re.sub(r"\([^)]*\)", "", name)))
            mot_ent = lookup_motorist_entry(name, postal, mot_by_norm, mot_by_tok, mot_by_postal)
            if live_om:
                for field in ("weekdays_rate_1", "weekdays_rate_2", "saturday_rate", "sunday_publicholiday_rate"):
                    if info.get(field) != live_om[field]:
                        info[field] = live_om[field]
                        updated_cache = True
            elif mot_ent and mot_ent.get("car_rows"):
                # Prefer Motorist 9% GST schedule over aging 7% GST data.gov.sg strings when LTA OneMotoring had no exact row match
                mot_sched = _format_motorist_rows(mot_ent["car_rows"])
                wk1 = mot_sched["weekdays_rate_1"]
                wk2 = mot_sched["weekdays_rate_2"]
                sat_rate = mot_sched["saturday_rate"]
                sun_rate = mot_sched["sunday_publicholiday_rate"]
            if live_om or not (mot_ent and mot_ent.get("car_rows")):
                sun_rate = str(info.get("sunday_publicholiday_rate") or "-")
                sat_rate = str(info.get("saturday_rate") or "-")
                wk1 = str(info.get("weekdays_rate_1") or "-")
                wk2 = str(info.get("weekdays_rate_2") or "-")
            addr = str(info.get("address") or name)
            sun_free = "free" in sun_rate.lower()
            area_tier = "central" if ("central" in str(info.get("category") or "").lower() and any(k.upper() in addr.upper() for k in CENTRAL_AREA_KEYWORDS)) else "standard"
            bike_rate_custom, is_free_bike, no_moto = lookup_bike_info(name, bike_entries, mot_ent)
            carparks.append(
                {
                    "id": f"MALL-{idx}",
                    "name": name,
                    "address": addr,
                    "postal": postal,
                    "lat": lat,
                    "lng": lng,
                    "type": "COMMERCIAL / SHOPPING MALL",
                    "system": "ELECTRONIC PARKING",
                    "short_term": "COMMERCIAL SCHEDULE",
                    "free_parking_raw": "FREE BIKE / COMMERCIAL" if is_free_bike else ("COMMERCIAL SUN FREE" if sun_free else "COMMERCIAL"),
                    "free_sun_ph": sun_free,
                    "free_bike": is_free_bike,
                    "no_moto": no_moto,
                    "night_parking": True,
                    "sheltered": True,
                    "gantry_height": 2.1,
                    "area_tier": area_tier,
                    "weekday_rate": wk1,
                    "weekday_rate_2": wk2,
                    "saturday_rate": sat_rate,
                    "sunday_rate": sun_rate,
                    "bike_rate": bike_rate_custom or "Commercial gantry rate (check mall signage)",
                    "car_rate": wk1,
                    "has_car_live": False,
                    "has_bike_live": False,
                    "live": {},
                    "source_type": "LTA Commercial Rates",
                }
            )
        if updated_cache:
            COMMERCIAL_CACHE.write_text(json.dumps(commercial, indent=2), encoding="utf-8")

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
                "no_moto": False,
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
        live_om = onemotoring_rates.get(norm) or onemotoring_rates.get(_norm_key(re.sub(r"\([^)]*\)", "", name)))
        mot_ent = lookup_motorist_entry(name, "", mot_by_norm, mot_by_tok, mot_by_postal)
        car_sched = None
        if live_om:
            car_sched = live_om
        elif mot_ent and mot_ent.get("car_rows"):
            car_sched = _format_motorist_rows(mot_ent["car_rows"])
        bike_rate_custom, is_free_bike, no_moto = lookup_bike_info(name, bike_entries, mot_ent)
        sun_rate = car_sched["sunday_publicholiday_rate"] if car_sched else "-"
        sun_free = bool(car_sched and "free" in sun_rate.lower())
        item = {
            "id": f"SGCM-{entry.get('id')}",
            "name": name,
            "address": addr,
            "postal": mot_ent.get("postal", "") if mot_ent else "",
            "lat": lat,
            "lng": lng,
            "type": "COMMERCIAL / BUILDING",
            "system": "ELECTRONIC PARKING",
            "short_term": "COMMERCIAL SCHEDULE",
            "free_parking_raw": "FREE BIKE / COMMERCIAL" if is_free_bike else ("COMMERCIAL SUN FREE" if sun_free else "COMMERCIAL"),
            "free_sun_ph": sun_free,
            "free_bike": is_free_bike,
            "no_moto": no_moto,
            "night_parking": True,
            "sheltered": True,
            "gantry_height": 2.1,
            "area_tier": area_tier,
            "bike_rate": bike_rate_custom or "Commercial gantry rate (check building signage)",
            "car_rate": car_sched["weekdays_rate_1"] if car_sched else "Commercial gantry rate (check building signage)",
            "has_car_live": False,
            "has_bike_live": False,
            "live": {},
            "source_type": "LTA Commercial Rates" if car_sched else "SG Commercial Directory",
        }
        if car_sched:
            item["weekday_rate"] = car_sched["weekdays_rate_1"]
            item["weekday_rate_2"] = car_sched["weekdays_rate_2"]
            item["saturday_rate"] = car_sched["saturday_rate"]
            item["sunday_rate"] = sun_rate
        carparks.append(item)

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
