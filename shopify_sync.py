# shopify_sync.py (sync inventory to Shopify with dry-run support + variant & virtual kit handling)
import os
import time
import json
import logging
import requests
import sys
from dotenv import load_dotenv
from sheet_loader import load_inventory_from_sheets, load_kits_from_sheets

# --- Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler()]
)

load_dotenv()
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
SHOP_URL = os.getenv("SHOPIFY_SHOP_URL")
ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
logging.info(f"[DEBUG] DRY_RUN = {DRY_RUN}")

if not SHOP_URL or not ACCESS_TOKEN:
    raise ValueError("Missing SHOPIFY_SHOP_URL or SHOPIFY_ACCESS_TOKEN in .env")

HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

SHOPIFY_LOCATION_ID = os.getenv("SHOPIFY_LOCATION_ID")
if not SHOPIFY_LOCATION_ID:
    logging.error("❌ SHOPIFY_LOCATION_ID is missing from your .env file")
    sys.exit(1)

# --- Helpers ---
def get_inventory_items():
    """Fetch all product variants with SKU, inventory_item_id, and name."""
    endpoint = f"https://{SHOP_URL}/admin/api/2023-10/products.json?limit=250"
    sku_to_inventory_id = {}

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
                    sku_to_inventory_id[sku] = {
                        "inventory_item_id": inv_id,
                        "name": name
                    }

        # Handle pagination
        link_header = resp.headers.get("Link", "")
        next_link = None
        for link in link_header.split(","):
            if 'rel="next"' in link:
                next_link = link[link.find("<")+1:link.find(">")]
                break
        endpoint = next_link

    return sku_to_inventory_id

def update_inventory_level(sku, inventory_item_id, available, name=None):
    """Push inventory to Shopify for a given inventory item ID."""
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
    norm_sku = sku.strip().upper()
    stock = info.get("stock", 0)

    if norm_sku in kits and norm_sku not in sku_map:
        components = kits[norm_sku]
        try:
            stock = min(inv_data.get(comp["sku"].strip().upper(), {}).get("stock", 0) // comp["qty"] for comp in components)
        except Exception as e:
            logging.warning(f"⚠️ Error calculating virtual kit {norm_sku}: {e}")
            continue

    entry = sku_map.get(norm_sku)
    if entry:
        available = int(stock)  # ✅ Floor to nearest integer before sync
        update_inventory_level(norm_sku, entry["inventory_item_id"], available, name=entry["name"])
    else:
        logging.warning(f"⚠️ SKU {norm_sku} not found in Shopify")


    logging.info("✅ Shopify sync completed")
