# shipstation_sync.py (fully local .env & json-based)
import requests
import base64
import sqlite3
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("SHIPSTATION_API_KEY")
API_SECRET = os.getenv("SHIPSTATION_API_SECRET")

if not API_KEY or not API_SECRET:
    raise ValueError("Missing SHIPSTATION_API_KEY or SHIPSTATION_API_SECRET in .env")

DB_PATH = "order_log.db"

# Gspread client from gspread_key.json
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
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            all_orders.extend(data.get('orders', []))
            total_pages = data.get('pages', 1)
            page += 1
        except requests.RequestException as e:
            print("Error fetching orders:", e)
            break

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
            sheet.update_cell(idx, 3, new_stock)  # Column C = Stock On Hand
            print(f"📉 Updated {sku}: {current_stock} → {new_stock}")
            return
    print(f"⚠️ SKU {sku} not found in inventory sheet")

# MAIN EXECUTION
if __name__ == "__main__":
    conn = init_db()
    orders = get_shipped_orders()
    for order in orders:
        order_id = str(order.get("orderId"))
        if is_order_processed(conn, order_id):
            continue

        items = order.get("items", [])
        sku_dict = {}
        for item in items:
            sku = (item.get("sku") or "").strip().upper()
            qty = item.get("quantity", 0)
            sku_dict[sku] = sku_dict.get(sku, 0) + qty

        for sku, qty in sku_dict.items():
            subtract_from_google_sheet(sku, qty)

        log_processed_order(conn, order_id, sku_dict)
        print(f"✅ Logged order {order_id} → {sku_dict}")

    conn.close()
