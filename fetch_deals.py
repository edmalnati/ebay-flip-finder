import os
import sys
import json
import base64
import requests
from datetime import datetime, timezone

APP_ID = os.environ.get("EBAY_APP_ID")
CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")

FALLBACK_PRICES = {
    "PS4 DualShock 4": 40.00,
    "PS5 DualSense": 60.00,
    "Xbox One/Series": 37.00,
    "Xbox Series X/S": 55.00,
    "Joy-Con": 47.00,
}

MARKET_QUERIES = {
    "PS4 DualShock 4": "PS4 DualShock 4 controller working",
    "PS5 DualSense": "PS5 DualSense controller working",
    "Xbox One/Series": "Xbox One wireless controller working",
    "Xbox Series X/S": "Xbox Series X S controller working",
    "Joy-Con": "Nintendo Switch Joy-Con pair working",
}

SEARCH_QUERIES = [
    {"model": "PS4 DualShock 4", "query": "PS4 DualShock 4 controller broken parts not working"},
    {"model": "PS4 DualShock 4", "query": "PS4 DualShock 4 controller dirty untested faulty"},
    {"model": "PS4 DualShock 4", "query": "PS4 DualShock 4 controller used working"},
    {"model": "PS5 DualSense", "query": "PS5 DualSense controller broken parts not working"},
    {"model": "PS5 DualSense", "query": "PS5 DualSense controller drift faulty untested"},
    {"model": "PS5 DualSense", "query": "PS5 DualSense controller used working"},
    {"model": "Xbox One/Series", "query": "Xbox One controller broken parts not working"},
    {"model": "Xbox One/Series", "query": "Xbox One controller used working untested"},
    {"model": "Xbox Series X/S", "query": "Xbox Series X S controller broken parts not working"},
    {"model": "Xbox Series X/S", "query": "Xbox Series X S controller used working faulty"},
    {"model": "Joy-Con", "query": "Nintendo Switch Joy-Con broken drift parts not working"},
    {"model": "Joy-Con", "query": "Nintendo Switch Joy-Con faulty untested for parts"},
    {"model": "Joy-Con", "query": "Nintendo Switch Joy-Con used working pair"},
]

STATUS_BROKEN_KEYWORDS = [
    "for parts", "not working", "broken", "faulty", "cracked",
    "damaged", "repair", "drift", "untested"
]

def get_access_token():
    credentials = f"{APP_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    headers = {"Authorization": f"Basic {encoded}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    print("Fetching eBay access token...")
    response = requests.post("https://api.ebay.com/identity/v1/oauth2/token", headers=headers, data=data)
    if response.status_code != 200:
        print(f"ERROR: Could not fetch token - {response.status_code} {response.text}")
        sys.exit(1)
    print("Access token obtained.")
    return response.json().get("access_token")

def get_market_price(token, model):
    query = MARKET_QUERIES.get(model)
    if not query:
        return FALLBACK_PRICES.get(model, 40.00), "fallback"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }
    params = {
        "q": query,
        "limit": 50,
        "filter": "conditionIds:{1000|1500|2000|2500|3000}",
    }
    try:
        response = requests.get(
            "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search",
            headers=headers,
            params=params
        )
        if response.status_code == 200:
            items = response.json().get("itemSales", [])
            if items:
                prices = []
                for item in items:
                    try:
                        price = float(item.get("lastSoldPrice", {}).get("value", 0))
                        if price > 5:
                            prices.append(price)
                    except Exception:
                        continue
                if prices:
                    prices.sort()
                    mid = len(prices) // 2
                    median = prices[mid] if len(prices) % 2 != 0 else (prices[mid - 1] + prices[mid]) / 2
                    avg = sum(prices) / len(prices)
                    market_price = round((median + avg) / 2, 2)
                    print(f"  [{model}] Live market price: ${market_price} ({len(prices)} sold listings)")
                    return market_price, "live"
            print(f"  [{model}] No sold data returned, using fallback")
        elif response.status_code == 403:
            print(f"  [{model}] Marketplace Insights not authorized, using fallback")
        else:
            print(f"  [{model}] Insights API {response.status_code}, using fallback")
    except Exception as e:
        print(f"  [{model}] Error: {e}, using fallback")
    return FALLBACK_PRICES.get(model, 40.00), "fallback"

def get_deal_tier(discount_pct):
    if discount_pct >= 35: return "great"
    elif discount_pct >= 20: return "good"
    elif discount_pct > 0: return "fair"
    else: return "unfair"

def get_status(title):
    title_lower = title.lower()
    for kw in STATUS_BROKEN_KEYWORDS:
        if kw in title_lower: return "broken"
    return "working"

def calc_profit(market_price, buy_price, shipping):
    return round(market_price - buy_price - shipping - (market_price * 0.13), 2)

def search_listings(token, query):
    headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    params = {"q": query, "limit": 25, "sort": "newlyListed"}
    response = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search", headers=headers, params=params)
    if response.status_code != 200:
        print(f"  Warning: {response.status_code} for '{query}'")
        return []
    items = response.json().get("itemSummaries", [])
    print(f"  Found {len(items)} listings for: {query}")
    return items

def process_item(item, model, market_price):
    try:
        title = item.get("title", "")
        buy_price = float(item.get("price", {}).get("value", 0))
        if buy_price <= 0: return None
        shipping_options = item.get("shippingOptions", [])
        shipping = float(shipping_options[0].get("shippingCost", {}).get("value", 0)) if shipping_options else 0.0
        discount_pct = ((market_price - buy_price - shipping) / market_price) * 100
        date_str = item.get("itemCreationDate", "")
        try:
            date_posted = datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%Y-%m-%d") if date_str else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            date_posted = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {
            "id": item.get("itemId", ""),
            "title": title,
            "model": model,
            "status": get_status(title),
            "buy_price": round(buy_price, 2),
            "shipping_price": round(shipping, 2),
            "market_price": round(market_price, 2),
            "profit_estimate": calc_profit(market_price, buy_price, shipping),
            "deal_tier": get_deal_tier(discount_pct),
            "discount_pct": round(discount_pct, 1),
            "image_url": item.get("image", {}).get("imageUrl", ""),
            "listing_url": item.get("itemWebUrl", ""),
            "date_posted": date_posted,
        }
    except Exception as e:
        print(f"  Skipping item: {e}")
        return None

def main():
    if not APP_ID or not CLIENT_SECRET:
        print("ERROR: EBAY_APP_ID and EBAY_CLIENT_SECRET environment variables are required.")
        sys.exit(1)
    token = get_access_token()

    print("\n=== Calibrating market prices from eBay sold listings ===")
    market_prices = {}
    price_sources = {}
    for model in FALLBACK_PRICES.keys():
        price, source = get_market_price(token, model)
        market_prices[model] = price
        price_sources[model] = source

    print("\n=== Market price summary ===")
    for model, price in market_prices.items():
        print(f"  {model}: ${price} ({price_sources[model]})")

    print("\n=== Fetching active listings ===")
    all_deals = []
    seen_ids = set()
    for search in SEARCH_QUERIES:
        model, query = search["model"], search["query"]
        market_price = market_prices.get(model, FALLBACK_PRICES.get(model, 40.00))
        print(f"\nSearching [{model}]: {query}")
        for item in search_listings(token, query):
            item_id = item.get("itemId", "")
            if item_id in seen_ids: continue
            seen_ids.add(item_id)
            deal = process_item(item, model, market_price)
            if deal: all_deals.append(deal)

    tier_order = {"great": 0, "good": 1, "fair": 2, "unfair": 3}
    all_deals.sort(key=lambda d: (tier_order.get(d["deal_tier"], 4), d["buy_price"]))
    counts = {"great": 0, "good": 0, "fair": 0, "unfair": 0}
    for d in all_deals:
        counts[d["deal_tier"]] = counts.get(d["deal_tier"], 0) + 1

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "market_prices": market_prices,
        "price_sources": price_sources,
        "deals": all_deals
    }
    os.makedirs("data", exist_ok=True)
    with open("data/deals.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n=== Final Summary ===")
    print(f"Total: {len(all_deals)} | Great: {counts['great']} | Good: {counts['good']} | Fair: {counts['fair']} | Unfair: {counts['unfair']}")

if __name__ == "__main__":
    main()
