# eBay Flip Finder

Tracks underpriced broken gaming controller listings on eBay — PS4 DualShock 4, Xbox One/Series, and Nintendo Switch Joy-Con pairs — and scores each listing against market resale value so you can spot profitable flips at a glance.

---

## Setup

### Step 1 — Get a free eBay Developer account

1. Go to [developer.ebay.com](https://developer.ebay.com) and sign in with your eBay account (or create a free one).
2. Navigate to **My Account → Application Keysets** and click **Create a Keyset**.
3. Choose **Production** environment and give your app a name.
4. Copy the **App ID (Client ID)** and **Cert ID (Client Secret)** — you'll need both.

> eBay's Browse API requires OAuth application tokens, which need both the App ID and Cert ID to generate. Both values are free with a standard developer account.

---

### Step 2 — Add secrets to GitHub Actions

In your GitHub repo go to **Settings → Secrets and variables → Actions** and add two secrets:

| Secret name    | Value                          |
|----------------|-------------------------------|
| `EBAY_APP_ID`  | Your App ID (Client ID)       |
| `EBAY_CERT_ID` | Your Cert ID (Client Secret)  |

---

### Step 3 — Enable GitHub Pages

1. Go to **Settings → Pages**.
2. Under **Source**, select **Deploy from a branch**.
3. Choose **main** branch, **/ (root)** folder, and save.
4. Your site will be live at `https://<your-username>.github.io/<repo-name>/` within a minute.

---

### Step 4 — Run the workflow manually the first time

The daily schedule starts at 8:00 AM EST. To populate real data immediately:

1. Go to **Actions → Refresh Deals**.
2. Click **Run workflow → Run workflow**.
3. Wait ~30 seconds. The workflow fetches listings, writes `data/deals.json`, and commits it.
4. Reload your GitHub Pages URL to see live data.

---

## How deal tiers are calculated

Each listing's buy price is compared to the market resale value for that controller model (working condition):

| Tier       | Badge      | Condition                        |
|------------|------------|----------------------------------|
| Great      | ⭐         | 35%+ below market value          |
| Good       | 🟢         | 20–35% below market value        |
| Fair       | 🟡         | 0–20% below market value         |
| Unfair     | 🔴         | At or above market value         |

**Estimated profit** = `market_price − buy_price − (buy_price × 13%)`

The 13% covers approximate eBay selling fees and transaction costs.

---

## How to change market baseline prices

Open `fetch_deals.py` and edit the `MARKET_PRICES` dictionary near the top of the file:

```python
MARKET_PRICES = {
    "PS4 DualShock 4":         40.00,  # change this
    "Xbox One/Series":         37.00,  # change this
    "Nintendo Switch Joy-Con": 47.00,  # change this
}
```

Save the file, commit, and push. The next workflow run will use the new values.

---

## File structure

```
ebay-flip-finder/
├── index.html               # Dashboard (static, no build step)
├── fetch_deals.py           # eBay API fetch script
├── data/
│   └── deals.json           # Generated deal data (committed by workflow)
└── .github/
    └── workflows/
        └── refresh.yml      # Daily GitHub Actions schedule
```
