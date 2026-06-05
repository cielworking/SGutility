import json
import pathlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

SOURCE_NAME = "PetrolPrice.sg"
SOURCE_URL = "https://petrolprice.sg/"
OUTPUT_FILE = pathlib.Path("data/petrol-prices.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 SGUtilityDashboard/1.0"
}

BRANDS = ["Esso", "Shell", "SPC", "Caltex", "Sinopec", "Smart Energy"]

LOGOS = {
    "Esso": "./assets/petrol/esso.png",
    "Shell": "./assets/petrol/shell.png",
    "SPC": "./assets/petrol/spc.png",
    "Caltex": "./assets/petrol/caltex.png",
    "Sinopec": "./assets/petrol/sinopec.png",
    "Smart Energy": "./assets/petrol/smart-energy.png"
}

FUEL_KEY_MAP = {
    "92 Petrol": "ron92",
    "95 Petrol": "ron95",
    "98 Petrol": "ron98",
    "Premium Petrol": "premium",
    "Diesel": "diesel"
}

FUEL_KEYS = ["ron92", "ron95", "ron98", "premium", "diesel"]


def clean_value(value):
    value = value.strip()

    if not value or value.upper() in ["N/A", "-", "—"]:
        return "N/A"

    return value.replace(" ", "")


def parse_price(value):
    if not value or value == "N/A":
        return None

    try:
        return float(value.replace("$", "").strip())
    except ValueError:
        return None


def calculate_change(current, previous):
    current_num = parse_price(current)
    previous_num = parse_price(previous)

    if current_num is None or previous_num is None:
        return None

    change = round(current_num - previous_num, 2)

    percent = 0
    if previous_num > 0:
        percent = round((change / previous_num) * 100, 2)

    return {
        "previous": previous_num,
        "change": change,
        "percent": percent
    }


def load_old_brands():
    if not OUTPUT_FILE.exists():
        return {}

    try:
        old_data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    return {
        item.get("brand"): item
        for item in old_data.get("brands", [])
        if item.get("brand")
    }


def main():
    old_brands = load_old_brands()

    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"id": "price-table"})

    if not table:
        raise RuntimeError("Could not find petrol price table with id='price-table'.")

    tbody = table.find("tbody")

    if not tbody:
        raise RuntimeError("Could not find table body.")

    rows = tbody.find_all("tr")
    fuel_rows = {}

    for row in rows:
        cells = row.find_all("td")

        if len(cells) < 7:
            continue

        fuel_type = cells[0].get_text(" ", strip=True)
        fuel_key = FUEL_KEY_MAP.get(fuel_type)

        if not fuel_key:
            continue

        fuel_rows[fuel_key] = {
            "Esso": clean_value(cells[1].get_text(" ", strip=True)),
            "Shell": clean_value(cells[2].get_text(" ", strip=True)),
            "SPC": clean_value(cells[3].get_text(" ", strip=True)),
            "Caltex": clean_value(cells[4].get_text(" ", strip=True)),
            "Sinopec": clean_value(cells[5].get_text(" ", strip=True)),
            "Smart Energy": clean_value(cells[6].get_text(" ", strip=True))
        }

    brands = []

    for brand in BRANDS:
        previous_brand = old_brands.get(brand, {})
        changes = {}

        brand_data = {
            "brand": brand,
            "logo": LOGOS.get(brand, ""),
            "url": SOURCE_URL
        }

        for fuel_key in FUEL_KEYS:
            current_value = fuel_rows.get(fuel_key, {}).get(brand, "N/A")
            previous_value = previous_brand.get(fuel_key, "N/A")

            brand_data[fuel_key] = current_value

            change_result = calculate_change(current_value, previous_value)

            if change_result:
                changes[fuel_key] = change_result

        brand_data["changes"] = changes
        brands.append(brand_data)

    output = {
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "note": "Listed pump prices in SGD per litre. Discounts and card promotions are not included.",
        "brands": brands
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"Updated {OUTPUT_FILE}")
    print(f"Source: {SOURCE_URL}")


if __name__ == "__main__":
    main()