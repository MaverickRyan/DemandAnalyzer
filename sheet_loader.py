# 📁 sheet_loader.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict
import streamlit as st

# Create credentials from secrets dictionary
def get_gspread_client():
    gspread_key_dict = dict(st.secrets["gspread_key"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(gspread_key_dict, scope)
    return gspread.authorize(creds)

# Load Kits from Google Sheets
def load_kits_from_sheets():
    client = get_gspread_client()
    sheet = client.open("Kit BOMs").worksheet("kits")
    rows = sheet.get_all_records()

    kits = defaultdict(list)
    for row in rows:
        kit_sku = row["Kit SKU"].strip()
        component_sku = row["Component SKU"].strip()
        component_name = row["Component Name"].strip()
        quantity = int(row["Quantity"])
        kits[kit_sku].append({
            "sku": component_sku,
            "name": component_name,
            "qty": quantity
        })

    return dict(kits)

# Load Inventory from Google Sheets
def load_inventory_from_sheets():
    client = get_gspread_client()
    sheet = client.open("Kit BOMs").worksheet("inventory")
    rows = sheet.get_all_records()

    inventory = {}
    for row in rows:
        sku = row["SKU"].strip().upper()
        stock = int(row.get("Stock On Hand", 0))
        name = row.get("Product Name", "").strip()
        inventory[sku] = {"stock": stock, "name": name}

    return inventory
