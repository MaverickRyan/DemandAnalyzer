# 📁 sheet_loader.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict

# Load Kits from Google Sheets
def load_kits_from_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("gspread_key.json", scope)
    client = gspread.authorize(creds)

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
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("gspread_key.json", scope)
    client = gspread.authorize(creds)

    sheet = client.open("Kit BOMs").worksheet("inventory")
    rows = sheet.get_all_records()

    inventory = {}
    for row in rows:
        sku = row["SKU"].strip()
        stock = int(row.get("Stock On Hand", 0))
        inventory[sku] = stock

    return inventory
