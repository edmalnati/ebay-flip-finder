#!/usr/bin/env python3
"""Fetch eBay broken-controller listings and write data/deals.json."""

import base64
import json
import os
import sys
from datetime import datetime, date, timezone

import requests

# ── Config ──────────────────────────────────────────────────────────────────

EBAY_APP_ID  = os.environ["EBAY_APP_ID"]   # eBay OAuth client_id
EBAY_CERT_ID = os.environ["EBAY_CERT_ID"]  # eBay OAuth client_secret

TOKEN_URL  = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE      = "https://api.ebay.com/oauth/api_scope"

MARKET_PRICES = {
    "PS4 DualShock 4":        40.00,
    "Xbox One/Series":        37.00,
    "Nintendo Switch Joy-Con": 47.00,
}

# One or more search queries per model (results are deduplicated by item ID)
SEARCH_QUERIES = {
    "PS4 DualShock 4": [
        "PS4 DualShock 4 controller broken for parts",
        "PlayStation 4 controller not working cracked damaged",
    ],
    "Xbox One/Series": [
        "Xbox One controller broken for parts not working",
        "Xbox Series X S wireless controller faulty damaged",
    ],
    "Nintendo Switch Joy-Con": [
        "Nintendo Switch Joy-Con pair broken for parts",
        "Joy-Con pair not working cracked damaged untested",
    ],
}

# Title must contain at least one of these keywords (case-insensitive)
TITLE_KEYWORDS = [
    "for parts", "broken", "not working", "dirty", "untested",
    "faulty", "cracked", "damaged",
]

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "deals.json")

# ── eBay OAuth ───────────────────────────────────────────────────────────────

def get_access_token() -> str:
    credentials = base64.b64encode(f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": SCOPE},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

# ── Deal math ────────────────────────────────────────────────────────────────

def calc_tier(buy_price: float, market_price: float) -> str:
    if buy_price >= market_price:
        return "unfair"
    discount = (market_price - buy_price) / market_price
    if discount >= 0.35:
        return "great"
    if discount >= 0.20:
        return "good"
    return "fair"


def calc_profit(buy_price: float, market_price: float) -> float:
    return round(market_price - buy_price - (buy_price * 0.13), 2)

# ── eBay Browse API ──────────────────────────────────────────────────────────

def fetch_listings(token: str, query: str) -> list:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }
    params = {
        "q": query,
        "filter": "conditions:{FOR_PARTS_OR_NOT_WORKING},buyingOptions:{FIXED_PRICE}",
        "limit": "50",
        "fieldgroups": "STANDARD",
    }
    resp = requests.get(BROWSE_URL, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("itemSummaries", [])


def parse_item(item: dict, model: str) -> dict | None:
    title = item.get("title", "")
    title_lower = title.lower()

    # Skip listings whose title doesn't signal a broken/parts item
    if not any(kw in title_lower for kw in TITLE_KEYWORDS):
        return None

    try:
        buy_price = float(item.get("price", {}).get("value", 0))
    except (ValueError, TypeError):
        return None

    if buy_price <= 0:
        return None

    market_price = MARKET_PRICES[model]
    image_url    = item.get("image", {}).get("imageUrl", "")
    listing_url  = item.get("itemWebUrl", "")
    raw_id       = item.get("itemId", "").replace("|", "-")
    item_id      = raw_id or f"{model.lower().replace(' ', '-')}-{abs(hash(title)) % 10_000_000}"

    # Derive status from condition or title
    condition = item.get("condition", "").lower()
    status = "broken" if (
        "parts" in condition or "not working" in condition
        or any(kw in title_lower for kw in ["broken", "not working", "cracked", "damaged", "faulty"])
    ) else "working"

    raw_date = item.get("itemCreationDate", "")
    date_posted = raw_date.split("T")[0] if raw_date else date.today().isoformat()

    return {
        "id":              item_id,
        "title":           title,
        "model":           model,
        "status":          status,
        "buy_price":       buy_price,
        "market_price":    market_price,
        "image_url":       image_url,
        "listing_url":     listing_url,
        "date_posted":     date_posted,
        "deal_tier":       calc_tier(buy_price, market_price),
        "profit_estimate": calc_profit(buy_price, market_price),
    }

# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Fetching eBay access token…")
    try:
        token = get_access_token()
    except Exception as exc:
        print(f"ERROR: Could not fetch token — {exc}", file=sys.stderr)
        sys.exit(1)

    all_deals: list[dict] = []
    seen_ids: set[str]    = set()

    for model, queries in SEARCH_QUERIES.items():
        print(f"\n[{model}]")
        for query in queries:
            print(f"  → {query}")
            try:
                items = fetch_listings(token, query)
            except Exception as exc:
                print(f"  WARNING: request failed — {exc}", file=sys.stderr)
                continue

            for item in items:
                deal = parse_item(item, model)
                if deal and deal["id"] not in seen_ids:
                    seen_ids.add(deal["id"])
                    all_deals.append(deal)

    # Sort by tier then by profit descending within tier
    tier_order = {"great": 0, "good": 1, "fair": 2, "unfair": 3}
    all_deals.sort(key=lambda d: (tier_order.get(d["deal_tier"], 9), -d["profit_estimate"]))

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    payload = {
        "refreshed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deals":        all_deals,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    # Summary
    counts = {t: 0 for t in tier_order}
    for d in all_deals:
        counts[d["deal_tier"]] += 1

    print(f"\n✅  {len(all_deals)} listings written to {OUTPUT_PATH}")
    print(f"   ⭐  {counts['great']}  great")
    print(f"   🟢  {counts['good']}  good")
    print(f"   🟡  {counts['fair']}  fair")
    print(f"   🔴  {counts['unfair']}  unfair")


if __name__ == "__main__":
    main()
