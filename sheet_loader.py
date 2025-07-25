# -----------------------------
# 📁 sheet_loader.py (Updated with virtual kit + inventory SKU loader)
# -----------------------------
import gspread
import json
import os
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    try:
        if "gspread_key" in st.secrets:
            creds_dict = dict(st.secrets["gspread_key"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            raise KeyError("gspread_key not found in st.secrets")
    except Exception:
        with open("gspread_key.json") as f:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(json.load(f), scope)

    return gspread.authorize(creds)

def load_kits_from_sheets():
    client = get_gspread_client()
    sheet = client.open("Kit BOMs").worksheet("kits")
    rows = sheet.get_all_records()
    kits = defaultdict(list)
    for row in rows:
        try:
            qty = float(row["Quantity"])
        except Exception:
            qty = 0.0

        kits[row["Kit SKU"].strip().upper()].append({
            "sku": row["Component SKU"].strip().upper(),
            "name": row["Component Name"].strip(),
            "qty": qty,
            "kit_name": row.get("Kit Name", "").strip()
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
            "stock": float(row.get("Stock On Hand", 0)),
            "name": row.get("Product Name", sku).strip()
        }
    return inventory

def update_inventory_quantity(sku, qty_to_add):
    client = get_gspread_client()
    sheet = client.open("Kit BOMs").worksheet("inventory")
    rows = sheet.get_all_records()
    for idx, row in enumerate(rows, start=2):
        if row["SKU"].strip().upper() == sku.strip().upper():
            try:
                current_qty = float(row.get("Stock On Hand", 0))
            except:
                current_qty = 0.0
            new_qty = current_qty + qty_to_add
            sheet.update_cell(idx, 3, new_qty)
            return {"success": True, "old_qty": current_qty, "new_qty": new_qty}
    return {"success": False}

def load_inflation_rules():
    client = get_gspread_client()
    try:
        sheet = client.open("Kit BOMs").worksheet("inflation_rules")
        rows = sheet.get_all_records()
        store2_inflated = set(
            row["SKU"].strip().upper()
            for row in rows
            if str(row.get("Store2 Inflate", "")).strip().upper() == "TRUE"
        )
        return store2_inflated
    except Exception as e:
        print(f"[ERROR] Could not load inflation rules: {e}")
        return set()

def load_all_inventory_and_kit_skus():
    """Returns a set of all SKUs that exist in the inventory or as virtual kits."""
    inventory_skus = set(load_inventory_from_sheets().keys())
    kits = load_kits_from_sheets()
    kit_skus = set(kits.keys())
    return inventory_skus.union(kit_skus)
