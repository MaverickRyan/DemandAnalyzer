import os
import time
import json
import logging
import requests
import sys
from dotenv import load_dotenv
from sheet_loader import (
    load_inventory_from_sheets,
    load_kits_from_sheets,
    load_inflation_rules
)

# --- Setup ---
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/shopify_sync.log", encoding="utf-8")
    ]
)

load_dotenv()
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
logging.info(f"[DEBUG] DRY_RUN = {DRY_RUN}")

# --- Shopify store configurations ---
STORES = []
for n in ["", "_STORE2"]:
    url = os.getenv(f"SHOPIFY_SHOP_URL{n}")
    token = os.getenv(f"SHOPIFY_ACCESS_TOKEN{n}")
    location_id = os.getenv(f"SHOPIFY_LOCATION_ID{n}")
    if url and token and location_id:
        STORES.append({
            "name": f"Store{n or '1'}",
            "shop_url": url,
            "access_token": token,
            "location_id": location_id
        })

if not STORES:
    logging.error("[ERROR] No valid Shopify store credentials found in .env")
    sys.exit(1)

# --- Helpers ---
def get_inventory_items(store):
    endpoint = f"https://{store['shop_url']}/admin/api/2023-10/products.json?limit=250"
    headers = {
        "X-Shopify-Access-Token": store["access_token"],
        "Content-Type": "application/json"
    }
    sku_to_inventory_id = {}

    while endpoint:
        resp = requests.get(endpoint, headers=headers)
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

def update_inventory_level(store, sku, inventory_item_id, available, name=None):
    label = f"SKU {sku}" + (f" ({name})" if name else "")

    if DRY_RUN:
        logging.info(f"[DRY-RUN] Would update {label} → {available} on {store['name']}")
        return

    endpoint = f"https://{store['shop_url']}/admin/api/2023-10/inventory_levels/set.json"
    headers = {
        "X-Shopify-Access-Token": store["access_token"],
        "Content-Type": "application/json"
    }
    payload = {
        "location_id": store["location_id"],
        "inventory_item_id": inventory_item_id,
        "available": available
    }
    response = requests.post(endpoint, headers=headers, json=payload)
    if response.status_code == 200:
        logging.info(f"[OK] Updated {label} to {available} on {store['name']}")
    else:
        logging.error(f"[ERROR] Failed to update {label} on {store['name']}: {response.text}")

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("[START] Shopify Inventory Sync" + (" [DRY-RUN]" if DRY_RUN else ""))

    inv_data = load_inventory_from_sheets()
    kits = load_kits_from_sheets()
    inflated_skus_store2 = load_inflation_rules()

    all_skus = set(inv_data.keys()) | set(kits.keys())
    logging.info(f"[CALC] Processing {len(all_skus)} total SKUs")

    for store in STORES:
        logging.info(f"[STORE SYNC] Syncing with {store['name']}")
        sku_map = get_inventory_items(store)

        for sku in all_skus:
            norm_sku = sku.strip().upper()
            stock = inv_data.get(norm_sku, {}).get("stock", 0)

            if norm_sku in kits:
                logging.debug(f"[DEBUG] {norm_sku} is in kits")
                if norm_sku not in inv_data:
                    logging.debug(f"[DEBUG] {norm_sku} is not in inventory (candidate for virtual kit)")

            # --- Virtual Kit Logic ---
            if norm_sku in kits and norm_sku not in inv_data:
                logging.info(f"[INFO] Virtual kit condition met for {norm_sku}")
                components = kits[norm_sku]
                try:
                    component_stocks = []
                    calculated_quantities = []

                    for comp in components:
                        comp_sku = comp["sku"].strip().upper()
                        qty_per_kit = comp["qty"]
                        stock_qty = inv_data.get(comp_sku, {}).get("stock", 0)

                        if qty_per_kit <= 0:
                            logging.warning(f"[WARN] Invalid quantity in kit: {norm_sku} requires {qty_per_kit} of {comp_sku}")
                            continue

                        if stock_qty is None:
                            logging.warning(f"[WARN] Missing stock data for component {comp_sku} in kit {norm_sku}")
                            stock_qty = 0

                        calculated_quantity = stock_qty // qty_per_kit
                        component_stocks.append((comp_sku, stock_qty, qty_per_kit, calculated_quantity))
                        calculated_quantities.append(calculated_quantity)

                    if not calculated_quantities:
                        logging.warning(f"[WARN] No valid components for virtual kit {norm_sku}. Skipping.")
                        continue

                    stock = min(calculated_quantities)
                    breakdown = ", ".join(f"{sku}: {stock_qty}/{qty_per_kit} → {possible}" 
                                          for sku, stock_qty, qty_per_kit, possible in component_stocks)
                    logging.info(f"[DETAIL] Entered virtual kit block for {norm_sku}")
                    logging.info(f"[KIT CALC] {norm_sku}: available = {stock} (based on: {breakdown})")
                except Exception as e:
                    logging.warning(f"[WARN] Error calculating virtual kit {norm_sku}: {e}")
                    continue

                # Inflate virtual kits for Store2
                if store['name'] == "Store2" and norm_sku in inflated_skus_store2:
                    stock += 1000
                    logging.info(f"[INFLATED] Virtual kit {norm_sku} for Store2 by +1000 → {stock}")

            # --- Inflate standalone SKUs ---
            if store['name'] == "Store2" and norm_sku in inflated_skus_store2:
                stock += 1000
                logging.info(f"[INFLATED] Standalone SKU {norm_sku} for Store2 by +1000 → {stock}")

            entry = sku_map.get(norm_sku)
            if entry:
                available = int(stock)  # Floor to int
                update_inventory_level(store, norm_sku, entry["inventory_item_id"], available, name=entry["name"])
            else:
                logging.warning(f"[WARN] SKU {norm_sku} not found in {store['name']}")

    logging.info(f"[SUMMARY] Total SKUs processed: {len(all_skus)}")
    logging.info(f"[SUMMARY] Total kits detected: {len(kits)}")
    logging.info("[COMPLETE] Shopify sync finished")
