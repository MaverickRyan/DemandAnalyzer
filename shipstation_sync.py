# shipstation_sync.py (live mode, with 7-day cutoff + logging)
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
SHIP_CUTOFF_DAYS = 7
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
    total_pages = 1

    while page <= total_pages:
        params = {
            'pageSize': 500,
            'page': page,
            'sortBy': 'modifyDate',
            'sortDir': 'DESC',
            'orderStatus': 'shipped'
        }
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            all_orders.extend(data.get('orders', []))
            total_pages = data.get('pages', 1)
            page += 1
        except requests.RequestException as e:
            logging.error(f"Error fetching orders: {e}")
            break

    logging.info(f"[ORDERS] Total shipped orders received: {len(all_orders)}")
    return all_orders

def subtract_from_google_sheet(sku, qty):
    client = get_gspread_client()
    sheet = client.open("Kit BOMs").worksheet("inventory")
    data = sheet.get_all_records()
    for idx, row in enumerate(data, start=2):
        row_sku = row["SKU"].strip().upper()
        if row_sku == sku:
            current_stock = int(row.get("Stock On Hand", 0))
            new_stock = max(current_stock - qty, 0)
            sheet.update_cell(idx, 3, new_stock)
            logging.info(f"[STOCK] Updated {sku}: {current_stock} → {new_stock}")
            return
    logging.warning(f"[WARN] SKU {sku} not found in inventory sheet")

# 🚀 MAIN EXECUTION
if __name__ == "__main__":
    logging.info("🚀 ShipStation Sync Started")
    conn = init_db()
    kits = load_kits_from_sheets()
    inventory = load_inventory_from_sheets()

    try:
        orders = get_shipped_orders()
    except Exception as e:
        logging.error(f"[ERR] Failed to retrieve orders: {e}")
        conn.close()
        raise

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
            continue

        items = order.get("items", [])
        sku_dict = {}
        for item in items:
            sku = (item.get("sku") or '').strip().upper()
            qty = item.get("quantity", 0)
            if not sku:
                continue
            sku_dict[sku] = sku_dict.get(sku, 0) + qty

        for sku, qty in sku_dict.items():
            if sku in kits:
                if sku in inventory:
                    # Prepacked kit: subtract the main kit SKU only
                    subtract_from_google_sheet(sku, qty)
                else:
                    # Virtual kit: subtract its components
                    for comp in kits[sku]:
                        comp_sku = comp["sku"].strip().upper()
                        comp_qty = qty * comp["qty"]
                        subtract_from_google_sheet(comp_sku, comp_qty)
            else:
                subtract_from_google_sheet(sku, qty)

        log_processed_order(conn, order_id, sku_dict)

    conn.close()
    logging.info("✅ ShipStation Sync Completed")
