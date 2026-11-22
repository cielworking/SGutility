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
TOTO_NEXT_URL = "https://www.singaporepools.com.sg/DataFileArchive/Lottery/Output/toto_next_draw_estimate_en.html"

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


def toto_number(value):
    text = clean(value)
    if not re.fullmatch(r"\d{1,2}", text):
        raise RuntimeError("Unexpected TOTO number token")
    number = int(text)
    if number < 1 or number > 49:
        raise RuntimeError(f"TOTO number out of range: {text}")
    return text


def parse_toto_block(block):
    winning_numbers = [
        toto_number(td.get_text())
        for td in block.select("td.win1, td.win2, td.win3, td.win4, td.win5, td.win6")
    ]
    additional_tag = block.select_one("td.additional")
    if additional_tag is None:
        raise RuntimeError("Unexpected TOTO layout: missing additional number")
    additional_number = toto_number(additional_tag.get_text())

    if len(winning_numbers) != 6 or len(set(winning_numbers)) != 6:
        raise RuntimeError("Unexpected TOTO layout: expected six distinct winning numbers")
    if additional_number in winning_numbers:
        raise RuntimeError("Unexpected TOTO layout: additional number repeats a winning number")

    return winning_numbers, additional_number


def fetch_toto_next_draw():
    try:
        resp = requests.get(TOTO_NEXT_URL, headers=HEADERS, timeout=20, verify=False)
        resp.raise_for_status()
        txt = clean(BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True))
        m_jackpot = re.search(r"Next Jackpot\s*(\$[0-9,]+(?:\s*est)?)", txt, re.I)
        m_date = re.search(r"Next Draw\s*((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+\w+\s+\d{4}[^<]*)", txt, re.I)
        jackpot_str = clean(m_jackpot.group(1)) if m_jackpot else ""
        digits = re.sub(r"[^0-9]", "", jackpot_str)
        jackpot_num = int(digits) if digits else 0
        next_date = clean(m_date.group(1)).replace(" , ", ", ") if m_date else ""
        return {
            "next_jackpot": jackpot_str,
            "next_jackpot_amount": jackpot_num,
            "next_draw_date": next_date,
            "is_snowball": jackpot_num >= 1_500_000,
        }
    except Exception as exc:
        print(f"Warning: TOTO next draw fetch failed ({exc})")
        return {}


def fetch_toto():
    block = get_first_li(TOTO_DATA_URL)

    text = clean(block.get_text(" ", strip=True))

    date_match = re.search(
        r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+\w+\s+\d{4}",
        text
    )

    draw_no_match = re.search(
        r"Draw\s*No\.?\s*(\d+)",
        text,
        re.IGNORECASE
    )

    winning_numbers, additional_number = parse_toto_block(block)

    g1_prize_match = re.search(r"Group 1 Prize\s*(\$[0-9,]+|-)", text, re.I)
    g1_share_match = re.search(r"Group 1\s+\$[0-9,]+\s+(\d+|-)", text, re.I)
    next_info = fetch_toto_next_draw()

    result = {
        "source_url": TOTO_SOURCE_URL,
        "data_url": TOTO_DATA_URL,
        "draw_date": date_match.group(0) if date_match else "TBC",
        "draw_no": draw_no_match.group(1) if draw_no_match else "TBC",
        "winning_numbers": winning_numbers,
        "additional_number": additional_number,
        "group1_prize": g1_prize_match.group(1) if g1_prize_match else "",
        "group1_winners": g1_share_match.group(1) if g1_share_match else "",
    }
    result.update(next_info)
    return result


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