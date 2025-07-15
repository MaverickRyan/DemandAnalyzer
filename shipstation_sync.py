# shipstation_sync.py (with 7-day cutoff + logging)
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

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("shipstation_sync.log"),
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

# [OK] Only consider orders shipped in the last 7 days
SHIP_CUTOFF_DAYS = 7
ship_date_cutoff = date.today() - timedelta(days=SHIP_CUTOFF_DAYS)

# 🔐 Google Sheets client from gspread_key.json
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

    while page == 1:  # DEBUG: limit to 1 page
        params = {
            'pageSize': 500,
            'page': page,
            'sortBy': 'modifyDate',
            'sortDir': 'DESC',
            'orderStatus': 'shipped'
        }
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            print(f"[HTTP] API status: {response.status_code}")
            print(f"[RESP] API response preview: {response.text[:300]}")
            response.raise_for_status()
            print("✅ ShipStation API request succeeded")
            data = response.json()
            all_orders.extend(data.get('orders', []))
            total_pages = data.get('pages', 1)
            page += 1
        except requests.RequestException as e:
            logging.error(f"Error fetching orders: {e}")
            print(f"❌ Request error: {e}")
            break

    print(f"[ORDERS] Total shipped orders received: {len(all_orders)}")
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

# [START] MAIN EXECUTION
if __name__ == "__main__":
    print("🚀 Entered main function")

    try:
        load_dotenv()
        print("✅ dotenv loaded")
        print("🔐 API Key prefix:", API_KEY[:4])
    except Exception as e:
        print("❌ dotenv error:", e)

    try:
        print("[GSPREAD] Testing Google Sheets client...")
        get_gspread_client()
        print("✅ Google Sheets connection successful")
    except Exception as e:
        print("❌ Google Sheets connection error:", e)

    try:
        print("🌐 Fetching orders from ShipStation...")
        orders = get_shipped_orders()
        print(f"📦 Orders fetched: {len(orders)}")
        print("[SAMPLE] Sample order:", orders[0] if orders else "(none)")
    except Exception as e:
        print("❌ Error fetching orders:", e)

    print("✅ Debug mode complete")
