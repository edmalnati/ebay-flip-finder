import os
import sys
import json
import base64
import requests
from datetime import datetime, timezone

# --- Config ---
APP_ID = os.environ.get("EBAY_APP_ID")
CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")

MARKET_PRICES = {
    "PS4 DualShock 4": 40.00,
    "Xbox One/Series": 37.00,
    "Joy-Con": 47.00,
}

SEARCH_QUERIES = [
    {"model": "PS4 DualShock 4", "query": "PS4 DualShock 4 controller broken parts not working"},
    {"model": "PS4 DualShock 4", "query": "PS4 DualShock 4 controller dirty untested faulty"},
    {"model": "Xbox One/Series", "query": "Xbox One controller broken parts not working"},
    {"model": "Xbox One/Series", "query": "Xbox Series controller broken parts faulty untested"},
    {"model": "Joy-Con", "query": "Nintendo Switch Joy-Con broken drift parts not working"},
    {"model": "Joy-Con", "query": "Nintendo Switch Joy-Con faulty untested for parts"},
]

CONDITION_KEYWORDS = [
    "for parts", "not working", "broken", "dirty", "untested",
    "faulty", "cracked", "damaged", "drift", "repair"
]

STATUS_BROKEN_KEYWORDS = [
    "for parts", "not working", "broken", "faulty", "cracked",
    "damaged", "repair", "drift", "untested"
]

def get_access_token():
    credentials = f"{APP_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    print("Fetching eBay access token...")
    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers=headers,
        data=data
    )
    if response.status_code != 200:
        print(f"ERROR: Could not fetch token - {response.status_code} {response.text}")
        sys.exit(1)
    token = response.json().get("access_token")
    print("Access token obtained.")
    return token

def get_deal_tier(discount_pct):
    if discount_pct >= 35:
        return "great"
    elif discount_pct >= 20:
        return "good"
    elif discount_pct > 0:
        return "fair"
    else:
        return "unfair"

def get_status(title):
    title_lower = title.lower()
    for kw in STATUS_BROKEN_KEYWORDS:
        if kw in title_lower:
            return "broken"
    return "working"

def calc_profit(market_price, buy_price, shipping):
    total_cost = buy_price + shipping
    ebay_fee = market_price * 0.13
    return round(market_price - total_cost - ebay_fee, 2)

def search_listings(token, query, model):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }
    params = {
        "q": query,
        "limit": 20,
        "filter": "conditionIds:{7000|3000}",  # For parts or not working + Used
        "sort": "newlyListed",
    }
    response = requests.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        headers=headers,
        params=params
    )
    if response.status_code != 200:
        print(f"  Warning: Search failed for '{query}': {response.status_code}")
        return []
    items = response.json().get("itemSummaries", [])
    print(f"  Found {len(items)} results for: {query}")
    return items

def process_item(item, model):
    try:
        title = item.get("title", "")
        title_lower = title.lower()

        # Only include listings with relevant condition keywords
        if not any(kw in title_lower for kw in CONDITION_KEYWORDS):
            return None

        price_info = item.get("price", {})
        buy_price = float(price_info.get("value", 0))
        if buy_price <= 0:
            return None

        # Shipping cost
        shipping_options = item.get("shippingOptions", [])
        if shipping_options:
            ship_cost = shipping_options[0].get("shippingCost", {})
            shipping = float(ship_cost.get("value", 0))
        else:
            shipping = 0.0

        market_price = MARKET_PRICES.get(model, 40.00)
        total_cost = buy_price + shipping
        discount_pct = ((market_price - total_cost) / market_price) * 100
        deal_tier = get_deal_tier(discount_pct)
        profit = calc_profit(market_price, buy_price, shipping)
        status = get_status(title)

        # Date posted
        date_str = item.get("itemCreationDate", "")
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_posted = dt.strftime("%Y-%m-%d")
            except Exception:
                date_posted = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        else:
            date_posted = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        image = item.get("image", {}).get("imageUrl", "")
        listing_url = item.get("itemWebUrl", "")
        item_id = item.get("itemId", "")

        return {
            "id": item_id,
            "title": title,
            "model": model,
            "status": status,
            "buy_price": round(buy_price, 2),
            "shipping_price": round(shipping, 2),
            "market_price": round(market_price, 2),
            "profit_estimate": profit,
            "deal_tier": deal_tier,
            "discount_pct": round(discount_pct, 1),
            "image_url": image,
            "listing_url": listing_url,
            "date_posted": date_posted,
        }
    except Exception as e:
        print(f"  Skipping item due to error: {e}")
        return None

def main():
    if not APP_ID or not CLIENT_SECRET:
        print("ERROR: EBAY_APP_ID and EBAY_CLIENT_SECRET environment variables are required.")
        sys.exit(1)

    token = get_access_token()
    all_deals = []
    seen_ids = set()

    for search in SEARCH_QUERIES:
        model = search["model"]
        query = search["query"]
        print(f"\nSearching [{model}]: {query}")
        items = search_listings(token, query, model)
        for item in items:
            item_id = item.get("itemId", "")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            deal = process_item(item, model)
            if deal:
                all_deals.append(deal)

    # Sort: great first, then good, then fair, then unfair
    tier_order = {"great": 0, "good": 1, "fair": 2, "unfair": 3}
    all_deals.sort(key=lambda d: (tier_order.get(d["deal_tier"], 4), d["buy_price"]))

    # Summary
    counts = {"great": 0, "good": 0, "fair": 0, "unfair": 0}
    for d in all_deals:
        counts[d["deal_tier"]] = counts.get(d["deal_tier"], 0) + 1

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "deals": all_deals
    }

    os.makedirs("data", exist_ok=True)
    with open("data/deals.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n--- Summary ---")
    print(f"Total deals written: {len(all_deals)}")
    print(f"  Great : {counts['great']}")
    print(f"  Good  : {counts['good']}")
    print(f"  Fair  : {counts['fair']}")
    print(f"  Unfair: {counts['unfair']}")
    print(f"Output written to data/deals.json")

if __name__ == "__main__":
    main()
