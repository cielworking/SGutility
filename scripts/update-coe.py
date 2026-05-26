import json
import pathlib
import requests
from datetime import datetime, timezone

DATASET_ID = "d_69b3380ad7e51aff3a7dcc84eba52b8a"
API_URL = "https://data.gov.sg/api/action/datastore_search"
OUTPUT_FILE = pathlib.Path("data/coe-prices.json")

SOURCE_NAME = "data.gov.sg / LTA COE Bidding Results"
SOURCE_URL = "https://data.gov.sg/datasets/d_69b3380ad7e51aff3a7dcc84eba52b8a/view"

CATEGORY_MAP = {
    "Category A": "Cat A - Cars up to 1600cc / 130bhp",
    "Category B": "Cat B - Cars above 1600cc / 130bhp",
    "Category C": "Cat C - Goods Vehicle & Bus",
    "Category D": "Cat D - Motorcycle",
    "Category E": "Cat E - Open Category",
}


def clean_number(value):
    if value is None or value == "":
        return 0

    return int(float(str(value).replace(",", "").strip()))


def fetch_all_records():
    all_records = []
    offset = 0
    limit = 5000

    while True:
        params = {
            "resource_id": DATASET_ID,
            "limit": limit,
            "offset": offset,
        }

        response = requests.get(API_URL, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        records = data["result"]["records"]

        all_records.extend(records)

        if len(records) < limit:
            break

        offset += limit

    return all_records


def format_record(record):
    category = record["vehicle_class"]

    return {
        "month": record["month"],
        "bidding_no": int(record["bidding_no"]),
        "category": category,
        "category_label": CATEGORY_MAP.get(category, category),
        "quota": clean_number(record.get("quota")),
        "bids_success": clean_number(record.get("bids_success")),
        "bids_received": clean_number(record.get("bids_received")),
        "premium": clean_number(record.get("premium")),
    }


def bidding_label(bidding_no):
    if bidding_no == 1:
        return "1st Bidding Exercise"
    if bidding_no == 2:
        return "2nd Bidding Exercise"
    return f"Round {bidding_no}"


def main():
    raw_records = fetch_all_records()
    records = [format_record(record) for record in raw_records]

    rounds = sorted(
        set((record["month"], record["bidding_no"]) for record in records),
        key=lambda item: (item[0], item[1]),
    )

    if len(rounds) < 2:
        raise RuntimeError("Not enough COE rounds found to compare trend.")

    latest_month, latest_bidding_no = rounds[-1]
    previous_month, previous_bidding_no = rounds[-2]

    latest_records = [
        record
        for record in records
        if record["month"] == latest_month
        and record["bidding_no"] == latest_bidding_no
    ]

    previous_records = [
        record
        for record in records
        if record["month"] == previous_month
        and record["bidding_no"] == previous_bidding_no
    ]

    previous_map = {
        record["category"]: record
        for record in previous_records
    }

    latest_with_trend = []

    for item in latest_records:
        previous = previous_map.get(item["category"])
        previous_premium = previous["premium"] if previous else None

        change = 0
        change_percent = 0

        if previous_premium:
            change = item["premium"] - previous_premium
            change_percent = round((change / previous_premium) * 100, 2)

        latest_with_trend.append({
            **item,
            "previous_premium": previous_premium,
            "change": change,
            "change_percent": change_percent,
        })

    output = {
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "dataset_id": DATASET_ID,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "latest_month": latest_month,
        "latest_bidding_no": latest_bidding_no,
        "latest_bidding_label": bidding_label(latest_bidding_no),
        "previous_month": previous_month,
        "previous_bidding_no": previous_bidding_no,
        "previous_bidding_label": bidding_label(previous_bidding_no),
        "latest": latest_with_trend,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Updated {OUTPUT_FILE}")
    print(f"Latest: {latest_month}, {bidding_label(latest_bidding_no)}")


if __name__ == "__main__":
    main()