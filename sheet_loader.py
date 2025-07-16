# -----------------------------
# 📁 sheet_loader.py (Streamlit-ready)
# -----------------------------
import gspread
import json
import os
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st

def get_gspread_client():
    if os.getenv("STREAMLIT_RUNTIME") == "true":
        import streamlit as st
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gspread_key"]), scope)
    else:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("gspread_key.json", scope)
    return gspread.authorize(creds)

def load_kits_from_sheets():
    client = get_gspread_client()
    sheet = client.open("Kit BOMs").worksheet("kits")
    rows = sheet.get_all_records()
    kits = defaultdict(list)
    for row in rows:
        kits[row["Kit SKU"].strip()].append({
            "sku": row["Component SKU"].strip(),
            "name": row["Component Name"].strip(),
            "qty": int(row["Quantity"])
        })
    return dict(kits)

def load_inventory_from_sheets():
    client = get_gspread_client()
    sheet = client.open("Kit BOMs").worksheet("inventory")
    rows = sheet.get_all_records()
    inventory = {}
    for row in rows:
        sku = row["SKU"].strip().upper()
        inventory[sku] = {
            "stock": int(row.get("Stock On Hand", 0)),
            "name": row.get("Product Name", sku).strip()
        }
    return inventory

def update_inventory_quantity(sku, qty_to_add):
    client = get_gspread_client()
    sheet = client.open("Kit BOMs").worksheet("inventory")
    rows = sheet.get_all_records()
    for idx, row in enumerate(rows, start=2):
        if row["SKU"].strip().upper() == sku.strip().upper():
            current_qty = int(row.get("Stock On Hand", 0))
            new_qty = current_qty + qty_to_add
            sheet.update_cell(idx, 3, new_qty)  # Column C = Stock On Hand
            return {"success": True, "old_qty": current_qty, "new_qty": new_qty}
    return {"success": False}
