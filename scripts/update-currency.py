import json
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "data" / "currency-rates.json"
SGT = ZoneInfo("Asia/Singapore")

CURRENCIES = {
    "USD": "US Dollar ($)",
    "MYR": "Malaysian Ringgit (RM)",
    "AUD": "Australian Dollar (A$)",
    "GBP": "British Pound (£)",
    "EUR": "Euro (€)",
    "JPY": "Japanese Yen (¥)",
    "KRW": "South Korean Won (₩)",
    "THB": "Thai Baht (฿)",
    "IDR": "Indonesian Rupiah (Rp)",
    "CNY": "Chinese Yuan (¥)",
    "HKD": "Hong Kong Dollar (HK$)",
    "TWD": "New Taiwan Dollar (NT$)",
    "PHP": "Philippine Peso (₱)",
    "INR": "Indian Rupee (₹)",
    "NZD": "New Zealand Dollar (NZ$)",
}

ENDPOINTS = [
    ("Open Exchange Rates", "https://open.er-api.com/v6/latest/SGD"),
    ("Frankfurter (ECB)", "https://api.frankfurter.app/latest?from=SGD"),
]


def fetch_rates():
    last_error = None
    for name, url in ENDPOINTS:
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "SGAlerts/1.0"})
            resp.raise_for_status()
            payload = resp.json()
            raw_rates = payload.get("rates") or {}
            if not raw_rates:
                raise ValueError(f"{name} returned empty rates")
            return name, url, raw_rates
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"All currency endpoints failed: {last_error}")


def main():
    existing = {}
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    existing_rates = existing.get("rates") or {}

    try:
        source_name, source_url, raw_rates = fetch_rates()
    except Exception as exc:
        print(f"Warning: currency update skipped ({exc}); retaining existing rates.")
        return

    merged_rates = {}
    for code in CURRENCIES:
        val = raw_rates.get(code)
        if isinstance(val, (int, float)) and val > 0:
            merged_rates[code] = round(float(val), 4)
        elif code in existing_rates:
            merged_rates[code] = existing_rates[code]

    output = {
        "source_name": source_name,
        "source_url": source_url,
        "last_updated": datetime.now(SGT).isoformat(),
        "base": "SGD",
        "rates": merged_rates,
        "names": CURRENCIES,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Updated {OUTPUT_FILE} with {len(merged_rates)} currencies from {source_name}")


if __name__ == "__main__":
    main()
