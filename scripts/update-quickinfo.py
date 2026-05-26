import json
import pathlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, date

OUTPUT_FILE = pathlib.Path("data/quick-info.json")

MOM_URL = "https://www.mom.gov.sg/employment-practices/public-holidays"
CDC_URL = "https://vouchers.cdc.gov.sg/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 SGUtilityDashboard/1.0"
}

HOLIDAYS_2026 = [
    {"name": "New Year's Day", "date": "2026-01-01"},
    {"name": "Chinese New Year", "date": "2026-02-17"},
    {"name": "Chinese New Year Holiday", "date": "2026-02-18"},
    {"name": "Hari Raya Puasa", "date": "2026-03-20"},
    {"name": "Good Friday", "date": "2026-04-03"},
    {"name": "Labour Day", "date": "2026-05-01"},
    {"name": "Hari Raya Haji", "date": "2026-05-27"},
    {"name": "Vesak Day", "date": "2026-05-31"},
    {"name": "National Day", "date": "2026-08-09"},
    {"name": "Deepavali", "date": "2026-11-08"},
    {"name": "Christmas Day", "date": "2026-12-25"}
]


def get_next_holiday():
    today = date.today()

    upcoming = []

    for item in HOLIDAYS_2026:
        holiday_date = datetime.strptime(item["date"], "%Y-%m-%d").date()

        if holiday_date >= today:
            upcoming.append({
                "name": item["name"],
                "date": holiday_date
            })

    if not upcoming:
        return {
            "name": "To be updated",
            "detail": "Next year's public holidays have not been configured yet."
        }

    next_holiday = upcoming[0]

    readable_date = next_holiday["date"].strftime("%d %b %Y, %A")

    return {
        "name": next_holiday["name"],
        "detail": readable_date
    }


def main():
    next_holiday = get_next_holiday()

    output = {
        "source_name": "Official Singapore sources",
        "source_url": MOM_URL,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "items": [
            {
                "label": "Next Public Holiday",
                "value": next_holiday["name"],
                "detail": next_holiday["detail"],
                "url": MOM_URL
            },
            {
                "label": "CDC Vouchers 2026",
                "value": "$300",
                "detail": "Each Singaporean household can claim $300 CDC Vouchers for the 2026 tranche. Verify validity and eligibility from official CDC source.",
                "url": CDC_URL
            }
        ]
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"Updated {OUTPUT_FILE}")
    print(f"Next holiday: {next_holiday['name']} - {next_holiday['detail']}")


if __name__ == "__main__":
    main()