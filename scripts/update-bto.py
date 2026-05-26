import json
import pathlib
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

SOURCE_NAME = "HDB Flat Portal"
SOURCE_URL = "https://homes.hdb.gov.sg/"
API_URL = "https://api.homes.hdb.gov.sg/flatback/public/v1/launch/getUpcomingProjects"
OUTPUT_FILE = pathlib.Path("data/bto-projects.json")


def format_exercise(ballot_qtr):
    if not ballot_qtr or "-" not in ballot_qtr:
        return "TBC"

    year, month = ballot_qtr.split("-")

    month_name = {
        "02": "February",
        "06": "June",
        "10": "October"
    }.get(month, month)

    return f"{month_name} {year} BTO"


def clean_text(value):
    if not value:
        return "TBC"

    return str(value).strip()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        print("Opening HDB Flat Portal...")

        page.goto(
            SOURCE_URL,
            wait_until="networkidle",
            timeout=60000
        )

        page.wait_for_timeout(5000)

        xsrf_token = None

        for cookie in context.cookies():
            if cookie["name"] == "XSRF-TOKEN":
                xsrf_token = cookie["value"]
                break

        print(f"XSRF token found: {bool(xsrf_token)}")

        result = page.evaluate(
            """
            async (xsrfToken) => {
              const response = await fetch(
                "https://api.homes.hdb.gov.sg/flatback/public/v1/launch/getUpcomingProjects",
                {
                  method: "POST",
                  credentials: "include",
                  headers: {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "X-XSRF-TOKEN": xsrfToken || ""
                  },
                  body: "{}"
                }
              );

              if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
              }

              return await response.json();
            }
            """,
            xsrf_token
        )

        browser.close()

    if not isinstance(result, list):
        raise RuntimeError("Unexpected BTO API response format.")

    projects = []

    for item in result:
        ballot_qtr = clean_text(
            item.get("ballotQtr")
        )

        projects.append({
            "town": clean_text(
                item.get("town")
            ),
            "project": clean_text(
                item.get("town")
            ),
            "flat_types": clean_text(
                item.get("flatType")
            ),
            "stage": clean_text(
                item.get("stage")
            ),
            "ballot_qtr": ballot_qtr,
            "exercise": format_exercise(
                ballot_qtr
            ),
            "price_range": "TBC",
            "classification": "TBC",
            "waiting_time": "TBC",
            "project_id": clean_text(
                item.get("projectId")
            ),
            "listing_type": clean_text(
                item.get("listingType")
            ),
            "url": SOURCE_URL
        })

    upcoming_exercise = (
        projects[0]["exercise"]
        if projects
        else "TBC"
    )

    output = {
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "api_url": API_URL,
        "last_updated": datetime.now(
            timezone.utc
        ).isoformat(),
        "note": (
            "BTO project prices, classification and waiting time "
            "are usually confirmed closer to launch."
        ),
        "upcoming": {
            "exercise": upcoming_exercise,
            "status": "Upcoming"
        },
        "projects": projects
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(f"Updated {OUTPUT_FILE}")
    print(f"Projects found: {len(projects)}")
    print(f"Upcoming exercise: {upcoming_exercise}")


if __name__ == "__main__":
    main()