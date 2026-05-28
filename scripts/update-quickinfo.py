import json
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

OUTPUT_FILE = pathlib.Path("data/quick-info.json")
HOLIDAY_FILE = pathlib.Path("data/public-holidays.json")
CDC_FILE = pathlib.Path("data/cdc-vouchers.json")

MOM_URL = "https://www.mom.gov.sg/employment-practices/public-holidays"
CDC_URL = "https://vouchers.cdc.gov.sg/"

SGT = ZoneInfo("Asia/Singapore")


def get_next_holiday():
    today = datetime.now(SGT).date()

    holidays = json.loads(HOLIDAY_FILE.read_text(encoding="utf-8"))

    upcoming = []

    for item in holidays:
        holiday_date = datetime.strptime(item["date"], "%Y-%m-%d").date()

        if holiday_date >= today:
            upcoming.append({
                "name": item["name"],
                "date": holiday_date
            })

    upcoming.sort(key=lambda x: x["date"])

    if not upcoming:
        return {
            "name": "To be updated",
            "detail": "Next year's public holidays have not been configured yet."
        }

    next_holiday = upcoming[0]

    return {
        "name": next_holiday["name"],
        "detail": next_holiday["date"].strftime("%d %b %Y, %A")
    }


def main():
    next_holiday = get_next_holiday()
    cdc = json.loads(CDC_FILE.read_text(encoding="utf-8"))

    output = {
        "source_name": "Official Singapore sources",
        "source_url": MOM_URL,
        "last_updated": datetime.now(SGT).isoformat(),
        "items": [
            {
                "label": "Next Public Holiday",
                "value": next_holiday["name"],
                "detail": next_holiday["detail"],
                "url": MOM_URL
            },
            {
                "label": cdc["label"],
                "value": cdc["value"],
                "detail": cdc["detail"],
                "url": cdc["url"]
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