from pathlib import Path

shopify_sync_code = """
# shopify_sync.py (15-min auto sync from Google Sheets to Shopify)
import os
import time
import json
import logging
import requests
import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# ──────── 🔧 CONFIG ────────
INVENTORY_SHEET = "Kit BOMs"
SLEEP_INTERVAL = 15 * 60  # 15 minutes

# ──────── 🪪 AUTH ────────
load_dotenv()
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_PASSWORD = os.getenv("SHOPIFY_API_PASSWORD")
SHOPIFY_STORE_DOMAIN = os.getenv("SHOPIFY_STORE_DOMAIN")  # e.g., 'mystore.myshopify.com'

if not all([SHOPIFY_API_KEY, SHOPIFY_API_PASSWORD, SHOPIFY_STORE_DOMAIN]):
    raise EnvironmentError("Missing Shopify credentials or domain in .env")

# ──────── 📝 LOGGING ────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# ──────── 📊 SHEETS ────────
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("gspread_key.json", scope)
    return gspread.authorize(creds)

def fetch_inventory_data():
    client = get_gspread_client()
    inventory = client.open(INVENTORY_SHEET).worksheet("inventory").get_all_records()
    kits = client.open(INVENTORY_SHEET).worksheet("kits").get_all_records()
    return inventory, kits

# ──────── 🧠 LOGIC ────────
def calculate_virtual_kit_stock(kit_sku, components, inventory_lookup):
    try:
        return min(inventory_lookup[c["Component SKU"]] // c["Quantity"] for c in components)
    except Exception:
        return 0

def prepare_updates(inventory, kits):
    kit_map = {}
    for row in kits:
        sku = row["Kit SKU"].strip().upper()
        comp_sku = row["Component SKU"].strip().upper()
        qty = int(row["Quantity"])
        if sku not in kit_map:
            kit_map[sku] = []
        kit_map[sku].append({"Component SKU": comp_sku, "Quantity": qty})

    inventory_lookup = {row["SKU"].strip().upper(): int(row["Stock On Hand"]) for row in inventory}
    result = {}

    for row in inventory:
        sku = row["SKU"].strip().upper()
        result[sku] = inventory_lookup[sku]  # normal or prepacked kits

    for kit_sku, components in kit_map.items():
        if kit_sku not in inventory_lookup:
            qty = calculate_virtual_kit_stock(kit_sku, components, inventory_lookup)
            result[kit_sku] = qty

    return result

# ──────── 🚚 SHOPIFY ────────
def update_shopify_inventory(sku, quantity):
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_STORE_DOMAIN}/admin/api/2023-10/inventory_levels/adjust.json"
    try:
        # Find inventory item ID and location ID
        variant_res = requests.get(
            f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_STORE_DOMAIN}/admin/api/2023-10/variants.json?sku={sku}"
        )
        variant_res.raise_for_status()
        variants = variant_res.json().get("variants", [])
        if not variants:
            logging.warning(f"SKU '{sku}' not found on Shopify.")
            return
        variant = variants[0]
        inventory_item_id = variant["inventory_item_id"]

        # Fetch location ID
        loc_res = requests.get(
            f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_STORE_DOMAIN}/admin/api/2023-10/locations.json"
        )
        loc_res.raise_for_status()
        location_id = loc_res.json()["locations"][0]["id"]

        # Adjust inventory
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": quantity
        }
        put_url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_STORE_DOMAIN}/admin/api/2023-10/inventory_levels/set.json"
        put_res = requests.post(put_url, json=payload)
        put_res.raise_for_status()
        logging.info(f"[SYNC] {sku}: set to {quantity} units on Shopify.")
    except Exception as e:
        logging.error(f"[ERROR] Failed to sync SKU {sku}: {e}")

# ──────── 🕒 LOOP ────────
if __name__ == "__main__":
    logging.info("🟢 Shopify Inventory Sync Started")
    while True:
        try:
            inv, kits = fetch_inventory_data()
            updates = prepare_updates(inv, kits)
            for sku, qty in updates.items():
                update_shopify_inventory(sku, qty)
        except Exception as e:
            logging.error(f"[FATAL] Unexpected error: {e}")

        logging.info(f"⏱ Waiting {SLEEP_INTERVAL // 60} minutes for next sync...")
        time.sleep(SLEEP_INTERVAL)
"""

# Save to file
file_path = Path("/mnt/data/shopify_sync.py")
file_path.write_text(shopify_sync_code)
file_path.name
