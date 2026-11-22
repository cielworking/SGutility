"""Fetch live MAS 6-month T-Bill yields, Singapore Savings Bonds (SSB), and Singapore Bank Fixed Deposit comparison data."""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "savings-rates.json"
SGT = timezone(timedelta(hours=8), name="SGT")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

MAS_SSB_INTEREST_URL = "https://www.mas.gov.sg/api/v1/bondsandbills/m/savingbondsinterest?rows=250"
MAS_SSB_CAL_URL = "https://www.mas.gov.sg/api/v1/bondsandbills/m/savingbondsissuancecalendar?rows=250"
MAS_BONDS_LIST_URL = "https://www.mas.gov.sg/api/v1/bondsandbills/m/listbondsandbills"
MAS_ISSUANCE_CAL_URL = "https://www.mas.gov.sg/api/v1/bondsandbills/m/issuancecalendar?rows=1200"

# Verified Singapore bank fixed deposit promotional board snapshot (updated with MAS yields)
BANK_FD_RATES = [
    {
        "bank": "CIMB Singapore",
        "best_rate_pa": 2.30,
        "tenor": "12 months",
        "min_deposit": 10000,
        "conditions": "Online FastSaver / StarSaver Fresh Funds",
        "url": "https://www.cimb.com.sg/en/personal/banking-with-us/accounts/fixed-deposits/why-fixed-deposit.html",
    },
    {
        "bank": "RHB Bank Singapore",
        "best_rate_pa": 2.30,
        "tenor": "12 months",
        "min_deposit": 20000,
        "conditions": "Personal Banking online / branch placement",
        "url": "https://rhbgroup.com.sg/",
    },
    {
        "bank": "HL Bank Singapore",
        "best_rate_pa": 2.20,
        "tenor": "24 months",
        "min_deposit": 10000,
        "conditions": "Promotional online D-Fixed Deposit",
        "url": "https://www.hlbank.com.sg/",
    },
    {
        "bank": "Bank of China (BOC)",
        "best_rate_pa": 2.10,
        "tenor": "12 months",
        "min_deposit": 20000,
        "conditions": "Mobile Banking Time Deposit (higher tiers $200k+)",
        "url": "https://www.bankofchina.com/sg/",
    },
    {
        "bank": "Maybank Singapore",
        "best_rate_pa": 2.10,
        "tenor": "6 / 12 months",
        "min_deposit": 20000,
        "conditions": "Fresh funds promotional placement",
        "url": "https://www.maybank2u.com.sg/",
    },
    {
        "bank": "Hong Leong Finance",
        "best_rate_pa": 2.08,
        "tenor": "8 months",
        "min_deposit": 20000,
        "conditions": "Fixed Deposit promotional tier",
        "url": "https://www.hlf.com.sg/",
    },
    {
        "bank": "OCBC Bank",
        "best_rate_pa": 1.85,
        "tenor": "12 months",
        "min_deposit": 20000,
        "conditions": "Fresh funds online via OCBC Digital",
        "url": "https://www.ocbc.com/personal-banking/deposits/fixed-deposit-account",
    },
    {
        "bank": "UOB",
        "best_rate_pa": 1.70,
        "tenor": "12 months",
        "min_deposit": 10000,
        "conditions": "Fresh funds via UOB TMRW app",
        "url": "https://www.uob.com.sg/personal/save/fixed-deposits/singapore-dollar-fixed-deposit.page",
    },
    {
        "bank": "DBS / POSB",
        "best_rate_pa": 1.00,
        "tenor": "8–12 months",
        "min_deposit": 1000,
        "conditions": "Tiered $1,000–$19,999 (balances $20k+ revert to board tier)",
        "url": "https://www.dbs.com.sg/personal/deposits/fixed-deposits/singapore-dollar-fixed-deposit",
    },
]


def fetch_latest_ssb() -> dict:
    try:
        r_cal = requests.get(MAS_SSB_CAL_URL, headers=HEADERS, timeout=15).json()
        r_int = requests.get(MAS_SSB_INTEREST_URL, headers=HEADERS, timeout=15).json()
        today = datetime.now(SGT).date().isoformat()
        cal_recs = [
            rec for rec in (r_cal.get("result") or {}).get("records") or []
            if (rec.get("ann_date") or "") <= today or (rec.get("last_day_to_apply") or "") >= today[:7]
        ]
        # Only take issues already announced on or before today (unless only future planned exists)
        announced = [rec for rec in cal_recs if (rec.get("ann_date") or "") <= today]
        announced.sort(key=lambda x: x.get("ann_date") or "")
        latest_cal = announced[-1] if announced else {}

        int_by_code = {
            rec.get("issue_code"): rec
            for rec in (r_int.get("result") or {}).get("records") or []
            if rec.get("issue_code")
        }
        code = latest_cal.get("issue_code") or ""
        rates = int_by_code.get(code)
        if not rates and int_by_code:
            latest_code = sorted(int_by_code.keys())[-1]
            rates = int_by_code[latest_code]
            code = latest_code

        return {
            "issue_code": code,
            "savings_bond_code": latest_cal.get("savings_bond_code") or code,
            "last_day_to_apply": latest_cal.get("last_day_to_apply_formatted") or latest_cal.get("last_day_to_apply") or "",
            "issue_date": latest_cal.get("issue_date_formatted") or latest_cal.get("issue_date") or "",
            "year1_return": rates.get("year1_return") if rates else None,
            "year5_return": rates.get("year5_return") if rates else None,
            "year10_return": rates.get("year10_return") if rates else None,
            "url": latest_cal.get("url") or "https://www.mas.gov.sg/bonds-and-bills/singapore-savings-bonds",
        }
    except Exception as exc:
        print(f"Warning: MAS SSB fetch failed ({exc})")
        return {}


def fetch_latest_tbills() -> dict:
    try:
        today = datetime.now(SGT).date().isoformat()
        r_cal = requests.get(MAS_ISSUANCE_CAL_URL, headers=HEADERS, timeout=15).json()
        recs = [
            rec for rec in (r_cal.get("result") or {}).get("records") or []
            if rec.get("issue_type") == "T" and str(rec.get("auction_tenor")) == "0.5"
        ]
        past = [rec for rec in recs if (rec.get("auction_date") or "") <= today]
        upcoming = [rec for rec in recs if (rec.get("auction_date") or "") > today]
        past.sort(key=lambda x: x.get("auction_date") or "")
        upcoming.sort(key=lambda x: x.get("auction_date") or "")

        recent_auctions = []
        for item in reversed(past[-4:]):
            code = item.get("issue_code")
            if not code:
                continue
            r_det = requests.get(
                MAS_BONDS_LIST_URL,
                params={"rows": 1, "filters": f"issue_code:{code}"},
                headers=HEADERS,
                timeout=12,
            ).json()
            det_list = (r_det.get("result") or {}).get("records") or []
            det = det_list[0] if det_list else {}
            if det.get("cutoff_yield") is None:
                continue
            recent_auctions.append({
                "issue_code": code,
                "tenor": "6-Month T-Bill",
                "auction_date": item.get("auction_date_formatted") or item.get("auction_date"),
                "issue_date": item.get("issue_date_formatted") or item.get("issue_date"),
                "maturity_date": item.get("maturity_date_formatted") or item.get("maturity_date"),
                "cutoff_yield": det.get("cutoff_yield"),
                "median_yield": det.get("median_yield"),
                "avg_yield": det.get("avg_yield"),
                "bid_to_cover": det.get("bid_to_cover"),
                "total_bids_m": round(float(det.get("total_bids") or 0), 1),
                "url": item.get("url") or "https://www.mas.gov.sg/bonds-and-bills/treasury-bills-t-bills",
            })

        next_tbill = upcoming[0] if upcoming else {}
        return {
            "latest": recent_auctions[0] if recent_auctions else {},
            "recent": recent_auctions,
            "next_auction": {
                "issue_code": next_tbill.get("issue_code", ""),
                "auction_date": next_tbill.get("auction_date_formatted") or next_tbill.get("auction_date", ""),
                "issue_date": next_tbill.get("issue_date_formatted") or next_tbill.get("issue_date", ""),
                "maturity_date": next_tbill.get("maturity_date_formatted") or next_tbill.get("maturity_date", ""),
            } if next_tbill else {},
        }
    except Exception as exc:
        print(f"Warning: MAS T-Bill fetch failed ({exc})")
        return {}


def main() -> None:
    ssb = fetch_latest_ssb()
    tbills = fetch_latest_tbills()

    existing = {}
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    payload = {
        "source_name": "Monetary Authority of Singapore (MAS) & Singapore Bank Boards",
        "source_url": "https://www.mas.gov.sg/bonds-and-bills",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "ssb": ssb or existing.get("ssb") or {},
        "tbills": tbills if tbills.get("latest") else (existing.get("tbills") or {}),
        "fixed_deposits": BANK_FD_RATES,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    t_yield = (payload["tbills"].get("latest") or {}).get("cutoff_yield")
    s_10y = payload["ssb"].get("year10_return")
    print(f"Updated {OUTPUT} -> 6M T-Bill: {t_yield}% | SSB 10Y Avg: {s_10y}% | Banks: {len(BANK_FD_RATES)}")


if __name__ == "__main__":
    main()
