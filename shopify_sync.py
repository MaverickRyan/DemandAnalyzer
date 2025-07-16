# shopify_sync.py (sync inventory to Shopify with dry-run support & safer .env handling)

import os
import json
import logging
import requests
import sys
from dotenv import load_dotenv
from sheet_loader import load_inventory_from_sheets, load_kits_from_sheets

# --- Setup logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler()]
)

# --- Load environment ---
load_dotenv()

# ✅ Enforce DRY_RUN logic
if "DRY_RUN" not in os.environ:
    logging.warning("⚠️ DRY_RUN was not explicitly set in .env — defaulting to LIVE mode.")

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
logging.info(f"[DEBUG] DRY_RUN = {DRY_RUN}")

SHOP_URL = os.getenv("SHOPIFY_SHOP_URL")
ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_LOCATION_ID = os.getenv("SHOPIFY_LOCATION_ID")

if not SHOP_URL or not ACCESS_TOKEN or not SHOPIFY_LOCATION_ID:
    raise ValueError("Missing SHOPIFY_SHOP_URL, SHOPIFY_ACCESS_TOKEN, or SHOPIFY_LOCATION_ID in .env")

HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

# --- Helpers ---
def get_inventory_items():
    """Fetch all product variants with SKU, inventory_item_id, and readable name."""
    endpoint = f"https://{SHOP_URL}/admin/api/2023-10/products.json?limit=250"
    sku_map = {}

    while endpoint:
        resp = requests.get(endpoint, headers=HEADERS)
        resp.raise_for_status()
        products = resp.json().get("products", [])

        for product in products:
            product_title = product.get("title", "")
            for variant in product.get("variants", []):
                sku = (variant.get("sku") or "").strip().upper()
                inv_id = variant.get("inventory_item_id")
                variant_title = variant.get("title", "")
                name = f"{product_title} - {variant_title}".strip(" -")
                if sku:
                    sku_map[sku] = {
                        "inventory_item_id": inv_id,
                        "name": name
                    }

        # Handle pagination
        next_link = None
        link_header = resp.headers.get("Link", "")
        for link in link_header.split(","):
            if 'rel="next"' in link:
                next_link = link[link.find("<")+1:link.find(">")]
                break
        endpoint = next_link

    return sku_map

def update_inventory_level(sku, inventory_item_id, available, name=None):
    """Push inventory level to Shopify (unless dry-run)."""
    label = f"SKU {sku}" + (f" ({name})" if name else "")
    
    if DRY_RUN:
        logging.info(f"[DRY-RUN] Would update {label} → {available}")
        return

    endpoint = f"https://{SHOP_URL}/admin/api/2023-10/inventory_levels/set.json"
    payload = {
        "location_id": SHOPIFY_LOCATION_ID,
        "inventory_item_id": inventory_item_id,
        "available": available
    }
    response = requests.post(endpoint, headers=HEADERS, json=payload)
    if response.status_code == 200:
        logging.info(f"✅ Updated {label} to {available}")
    else:
        logging.error(f"❌ Failed to update {label}: {response.text}")

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("🚀 Starting Shopify Inventory Sync" + (" [DRY-RUN]" if DRY_RUN else ""))

    inv_data = load_inventory_from_sheets()
    kits = load_kits_from_sheets()
    sku_map = get_inventory_items()

    for sku, info in inv_data.items():
        stock = info.get("stock", 0)

        # Virtual Kit Calculation
        if sku in kits and sku not in sku_map:
            try:
                components = kits[sku]
                stock = min(
                    inv_data.get(comp["sku"].upper(), {}).get("stock", 0) // comp["qty"]
                    for comp in components
                )
            except Exception as e:
                logging.warning(f"⚠️ Failed to compute virtual kit stock for {sku}: {e}")
                continue

        entry = sku_map.get(sku)
        if entry:
            update_inventory_level(sku, entry["inventory_item_id"], stock, name=entry["name"])
        else:
            logging.warning(f"⚠️ SKU {sku} not found in Shopify")

    logging.info("✅ Shopify sync completed")
