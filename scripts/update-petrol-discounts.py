import json
import pathlib
from datetime import datetime, timezone

OUTPUT_FILE = pathlib.Path("data/petrol-discounts.json")

SOURCE_NAME = "Manual verified petrol promo links"

DISCOUNTS = [
    {
        "brand": "Shell",
        "card": "UOB One Card",
        "discount_percent": 21.15,
        "promo_url": "https://www.shell.com.sg/rewards-and-savings/greater-credit-cards-savings-at-shell.html",
        "note": "Up to 21.15% fuel savings with UOB One Card."
    },
    {
        "brand": "SPC",
        "card": "POSB Everyday Card",
        "discount_percent": 20.1,
        "promo_url": "https://www.posb.com.sg/personal/promotion/spc-savings",
        "note": "Up to 20.1% fuel savings at SPC."
    },
    {
        "brand": "Esso",
        "card": "DBS Esso Card",
        "discount_percent": 24.2,
        "promo_url": "https://www.dbs.com.sg/personal/cards/credit-cards/dbs-esso-platinum-card",
        "note": "Up to 24.2% fuel savings for regular Synergy fuels."
    },
    {
        "brand": "Caltex",
        "card": "OCBC 365 Card",
        "discount_percent": 22.92,
        "promo_url": "https://www.caltex.com/sg/rewards-and-offers/promotions/ocbc-cards-offer.html",
        "note": "Up to 22.92% fuel savings with OCBC 365 Card."
    },
    {
        "brand": "Sinopec",
        "card": "OCBC 365 Card",
        "discount_percent": 24,
        "promo_url": "https://www.ocbc.com/personal-banking/cards/365-cashback-credit-card",
        "note": "Up to 24% fuel savings at Sinopec."
    },
    {
        "brand": "Smart Energy",
        "card": "Smart Member Price",
        "promo_url": "https://www.smartenergy.sg/",
        "effective_prices": {
            "ron95": 2.57,
            "ron98": 2.90,
            "diesel": 2.62
        },
        "note": "Uses Smart Member published prices instead of percentage discount."
    }
]


def main():
    output = {
        "source_name": SOURCE_NAME,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "fuel_type": "ron95",
        "note": "Discounts may include instant discounts, rebates, cashback, membership savings, member prices, and/or minimum spend requirements. Always verify terms before use.",
        "discounts": DISCOUNTS
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"Updated {OUTPUT_FILE}")


if __name__ == "__main__":
    main()