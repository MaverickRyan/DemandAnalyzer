# shipstation_sync.py (3-day cutoff, live mode, logging, batch update, retry)
import requests
import base64
import sqlite3
from datetime import datetime, date, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from dotenv import load_dotenv
import os
import logging
import sys
import time
from gspread.exceptions import APIError
from sheet_loader import load_kits_from_sheets, load_inventory_from_sheets

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("shipstation_sync.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)

# 🔐 Load secrets from .env
load_dotenv()
API_KEY = os.getenv("SHIPSTATION_API_KEY")
API_SECRET = os.getenv("SHIPSTATION_API_SECRET")
if not API_KEY or not API_SECRET:
    raise ValueError("Missing SHIPSTATION_API_KEY or SHIPSTATION_API_SECRET in .env")

DB_PATH = "order_log.db"
SHIP_CUTOFF_DAYS = 3
ship_date_cutoff = date.today() - timedelta(days=SHIP_CUTOFF_DAYS)

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.load(open("gspread_key.json")), scope)
    return gspread.authorize(creds)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS processed_orders (
            order_id TEXT PRIMARY KEY,
            processed_at TEXT,
            sku_summary TEXT
        )
    """)
    conn.commit()
    return conn

def is_order_processed(conn, order_id):
    c = conn.cursor()
    c.execute("SELECT 1 FROM processed_orders WHERE order_id = ?", (order_id,))
    return c.fetchone() is not None

def log_processed_order(conn, order_id, sku_dict):
    c = conn.cursor()
    sku_summary = ", ".join(f"{sku}:{qty}" for sku, qty in sku_dict.items())
    c.execute("INSERT INTO processed_orders VALUES (?, ?, ?)", (
        order_id,
        datetime.now().isoformat(),
        sku_summary
    ))
    conn.commit()
    logging.info(f"✅ Logged order {order_id} → {sku_summary}")

def get_shipped_orders():
    url = 'https://ssapi.shipstation.com/orders'
    auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth}',
        'Content-Type': 'application/json'
    }

    all_orders = []
    page = 1
    MAX_PAGES = 100
    create_date_start = (datetime.today() - timedelta(days=SHIP_CUTOFF_DAYS)).strftime("%Y-%m-%d")

    while page <= MAX_PAGES:
        params = {
            'pageSize': 500,
            'page': page,
            'sortBy': 'createDate',
            'sortDir': 'DESC',
            'orderStatus': 'shipped',
            'createDateStart': create_date_start
        }

        try:
            logging.info(f"🔄 Requesting page {page} from ShipStation...")
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            orders = data.get('orders', [])
            all_orders.extend(orders)

            total_pages = data.get('pages') or 1
            logging.info(f"[PAGE] Page {page} of {total_pages} received")

            if page >= total_pages:
                break

            page += 1

        except requests.RequestException as e:
            logging.error(f"❌ Error fetching orders: {e}")
            break

    logging.info(f"📦 Total shipped orders received: {len(all_orders)}")
    return all_orders

def subtract_from_google_sheet(sheet, data, changes: dict):
    updates = []
    sku_to_row = {row["SKU"].strip().upper(): idx + 2 for idx, row in enumerate(data)}

    for sku, delta in changes.items():
        row_idx = sku_to_row.get(sku)
        if not row_idx:
            logging.warning(f"[WARN] SKU {sku} not found in inventory sheet")
            continue

        old_stock = int(data[row_idx - 2].get("Stock On Hand", 0))
        new_stock = max(old_stock - delta, 0)

        updates.append({
            "range": f"C{row_idx}",
            "values": [[str(new_stock)]]
        })
        logging.info(f"[STOCK] {sku}: {old_stock} → {new_stock} (Δ={delta})")

    if not updates:
        logging.info("[STOCK] No valid SKUs to update.")
        return

    chunk_size = 50
    for i in range(0, len(updates), chunk_size):
        chunk = updates[i:i + chunk_size]
        retry = 0
        while retry < 5:
            try:
                sheet.batch_update([{"range": u["range"], "values": u["values"]} for u in chunk])
                logging.info(f"[BATCH] Updated {len(chunk)} SKU(s) via batch_update.")
                break
            except APIError as e:
                if "429" in str(e):
                    wait_time = 2 ** retry
                    logging.warning(f"[RETRY] Quota exceeded. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    retry += 1
                else:
                    logging.error(f"[ERROR] GSpread API error: {e}")
                    break

# 🚀 MAIN EXECUTION
if __name__ == "__main__":
    logging.info("🚀 ShipStation Sync Started")

    try:
        logging.info("🛠 Initializing database...")
        conn = init_db()
        logging.info("✅ Database ready")

        logging.info("📄 Loading kits and inventory...")
        kits = load_kits_from_sheets()
        inventory = load_inventory_from_sheets()

        client = get_gspread_client()
        sheet = client.open("Kit BOMs").worksheet("inventory")
        sheet_data = sheet.get_all_records()
        logging.info("✅ Sheets loaded")

        logging.info("🌐 Fetching orders from ShipStation...")
        orders = get_shipped_orders()
        logging.info(f"✅ Retrieved {len(orders)} orders")
    except Exception as e:
        logging.error(f"[ERR] Setup failed: {e}")
        sys.exit(1)

    for order in orders:
        order_id = str(order.get("orderId"))

        ship_date_raw = order.get("shipDate") or order.get("modifyDate")
        if not ship_date_raw:
            continue

        try:
            ship_date = datetime.strptime(ship_date_raw.split("T")[0], "%Y-%m-%d").date()
            if ship_date < ship_date_cutoff:
                continue
        except Exception as e:
            logging.warning(f"[WARN] Could not parse ship date for order {order_id}: {e}")
            continue

        if is_order_processed(conn, order_id):
            logging.info(f"⏩ Already processed order {order_id}")
            continue

        logging.info(f"🔧 Processing order {order_id} from {ship_date}")

        sku_changes = {}
        for item in order.get("items", []):
            sku = (item.get("sku") or "").strip().upper()
            qty = item.get("quantity", 0)
            if not sku:
                continue

            if sku in kits:
                if sku in inventory:
                    sku_changes[sku] = sku_changes.get(sku, 0) + qty
                else:
                    for comp in kits[sku]:
                        comp_sku = comp["sku"].strip().upper()
                        comp_qty = qty * comp["qty"]
                        sku_changes[comp_sku] = sku_changes.get(comp_sku, 0) + comp_qty
            else:
                sku_changes[sku] = sku_changes.get(sku, 0) + qty

        subtract_from_google_sheet(sheet, sheet_data, sku_changes)
        log_processed_order(conn, order_id, sku_changes)

    conn.close()
    logging.info("✅ ShipStation Sync Completed")
