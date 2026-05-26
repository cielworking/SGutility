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


def clean_value(value):
    value = value.strip()

    if not value or value.upper() in ["N/A", "-", "—"]:
        return "N/A"

    return value.replace(" ", "")


def main():
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
        brands.append({
            "brand": brand,
            "logo": LOGOS.get(brand, ""),
            "ron92": fuel_rows.get("ron92", {}).get(brand, "N/A"),
            "ron95": fuel_rows.get("ron95", {}).get(brand, "N/A"),
            "ron98": fuel_rows.get("ron98", {}).get(brand, "N/A"),
            "premium": fuel_rows.get("premium", {}).get(brand, "N/A"),
            "diesel": fuel_rows.get("diesel", {}).get(brand, "N/A"),
            "url": SOURCE_URL
        })

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