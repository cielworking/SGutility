import json
import pathlib
import re
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SOURCE_NAME = "Singapore Pools"

FOUR_D_SOURCE_URL = "https://www.singaporepools.com.sg/en/product/pages/4d_results.aspx"
FOUR_D_DATA_URL = "https://www.singaporepools.com.sg/DataFileArchive/Lottery/Output/fourd_result_top_draws_en.html"

TOTO_SOURCE_URL = "https://www.singaporepools.com.sg/en/product/pages/toto_results.aspx"
TOTO_DATA_URL = "https://www.singaporepools.com.sg/DataFileArchive/Lottery/Output/toto_result_top_draws_en.html"

OUTPUT_FILE = pathlib.Path("data/sgpools-results.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 SGUtilityDashboard/1.0"
}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get_4d_numbers(block):
    numbers = []

    for row in block.find_all("tr"):
        cells = [clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]

        for cell in cells:
            if re.fullmatch(r"\d{4}", cell):
                numbers.append(cell)

    return numbers


def get_first_li(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
        verify=False
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    first_draw = soup.find("li")

    if not first_draw:
        raise RuntimeError(f"Could not find draw block from {url}")

    return first_draw


def fetch_4d():
    block = get_first_li(FOUR_D_DATA_URL)

    text = clean(block.get_text(" ", strip=True))
    numbers = get_4d_numbers(block)

    if len(numbers) < 23:
        raise RuntimeError(f"Could not find enough 4D numbers. Found {len(numbers)}.")

    date_match = re.search(
        r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+\w+\s+\d{4}",
        text
    )

    draw_no_match = re.search(
        r"Draw\s*No\.?\s*(\d+)",
        text,
        re.IGNORECASE
    )

    return {
        "source_url": FOUR_D_SOURCE_URL,
        "data_url": FOUR_D_DATA_URL,
        "draw_date": date_match.group(0) if date_match else "TBC",
        "draw_no": draw_no_match.group(1) if draw_no_match else "TBC",
        "first_prize": numbers[0],
        "second_prize": numbers[1],
        "third_prize": numbers[2],
        "starter": numbers[3:13],
        "consolation": numbers[13:23]
    }


def fetch_toto():
    block = get_first_li(TOTO_DATA_URL)

    text = clean(block.get_text(" ", strip=True))

    all_numbers = re.findall(r"\b\d{1,2}\b", text)

    date_match = re.search(
        r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+\w+\s+\d{4}",
        text
    )

    draw_no_match = re.search(
        r"Draw\s*No\.?\s*(\d+)",
        text,
        re.IGNORECASE
    )

    # TOTO winning numbers are usually 6 numbers + 1 additional number
    winning_numbers = all_numbers[:6]
    additional_number = all_numbers[6] if len(all_numbers) >= 7 else "TBC"

    return {
        "source_url": TOTO_SOURCE_URL,
        "data_url": TOTO_DATA_URL,
        "draw_date": date_match.group(0) if date_match else "TBC",
        "draw_no": draw_no_match.group(1) if draw_no_match else "TBC",
        "winning_numbers": winning_numbers,
        "additional_number": additional_number
    }


def main():
    four_d = fetch_4d()
    toto = fetch_toto()

    output = {
        "source_name": SOURCE_NAME,
        "source_url": FOUR_D_SOURCE_URL,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "four_d": four_d,
        "toto": toto
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"Updated {OUTPUT_FILE}")
    print(f"4D: {four_d['draw_date']} Draw {four_d['draw_no']} 1st Prize {four_d['first_prize']}")
    print(f"TOTO: {toto['draw_date']} Draw {toto['draw_no']} Numbers {', '.join(toto['winning_numbers'])} + {toto['additional_number']}")


if __name__ == "__main__":
    main()