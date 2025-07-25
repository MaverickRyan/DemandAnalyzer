# -------------------------
# 📁 app.py (Updated with Set Inventory Level Feature)
# -------------------------
import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime, timedelta
from collections import defaultdict
from shipstation import get_orders
from sheet_loader import (
    load_kits_from_sheets,
    load_inventory_from_sheets,
    update_inventory_quantity
)
from streamlit_autorefresh import st_autorefresh

# === Session Settings ===
SESSION_TIMEOUT = 60 * 60  # 1 hour in seconds

def password_gate():
    st.title("🔒 Secure Dashboard Login")
    st.markdown("Please enter the access password to continue:")

    with st.form("login_form"):
        password = st.text_input("🔑 Password", type="password", placeholder="Enter password...")
        submitted = st.form_submit_button("🔓 Login")

        if submitted:
            if password == st.secrets["auth"]["password"]:
                st.session_state["authenticated"] = True
                st.session_state["auth_time"] = time.time()
                st.rerun()
            else:
                st.error("❌ Incorrect password. Please try again.")

def logout():
    st.session_state["authenticated"] = False
    st.session_state["auth_time"] = 0
    st.rerun()

# === Handle Timeout ===
now = time.time()
auth_time = st.session_state.get("auth_time", 0)
session_age = now - auth_time

if not st.session_state.get("authenticated", False) or session_age > SESSION_TIMEOUT:
    st.session_state["authenticated"] = False
    password_gate()
    st.stop()

# === Show logout button in sidebar once logged in ===
with st.sidebar:
    if st.session_state.get("authenticated", False):
        if st.button("🚪 Logout"):
            logout()

# 🔄 Auto-refresh every 5 minutes
st_autorefresh(interval=5 * 60 * 1000, key="inventory_autorefresh")

kits = load_kits_from_sheets()
inventory = load_inventory_from_sheets()

# Sidebar filter
st.sidebar.header("🗓️ Filter Orders by Date")
default_start = datetime.now().date() - timedelta(days=14)
default_end = datetime.now().date()
start_date = st.sidebar.date_input("Start Date", default_start, key="filter_start_date")
end_date = st.sidebar.date_input("End Date", default_end, key="filter_end_date")

st.sidebar.markdown("---")
st.sidebar.subheader("Inventory Controls")
if st.sidebar.button("🔄 Refresh Inventory Now"):
    st.session_state["inventory"] = load_inventory_from_sheets()

# 🔎 Kit Checker Feature
st.sidebar.markdown("---")
st.sidebar.subheader("Check Kit Components")
kit_sku = st.sidebar.text_input("Enter SKU to check components").strip().upper()
if kit_sku:
    if kit_sku in kits:
        st.sidebar.success(f"{kit_sku} is a kit. Components:")
        components = kits[kit_sku]
        rows = []
        for comp in components:
            comp_sku = comp.get("sku", "").strip().upper()
            qty = comp.get("qty", "")
            name = inventory.get(comp_sku, {}).get("name", "")
            rows.append({"Component SKU": comp_sku, "Quantity": qty, "Name": name})
        comp_data = pd.DataFrame(rows)
        st.sidebar.dataframe(comp_data)
    else:
        st.sidebar.info(f"{kit_sku} is not a kit.")

inventory_levels = st.session_state.get("inventory", inventory)

# Title
st.title("📦 Fulfillment & Production Dashboard")
st.caption(f"🔄 Last Refreshed: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")

# Add Received Inventory
with st.expander("➕ Add Received Inventory to Stock", expanded=False):
    with st.form("inventory_update_form"):
        sku_input = st.text_input("Enter SKU").strip().upper()
        qty_input = st.number_input("Enter quantity received", step=1, min_value=1)
        submitted = st.form_submit_button("Submit")
        if submitted:
            kits = load_kits_from_sheets()
            inventory = load_inventory_from_sheets()

            if sku_input in kits and sku_input in inventory:
                st.info("[KIT] Prepacked kit detected. Subtracting components from inventory.")
                feedback = []
                for comp in kits[sku_input]:
                    comp_sku = comp["sku"].strip().upper()
                    comp_qty = qty_input * float(comp["qty"])
                    old_stock = inventory.get(comp_sku, {}).get("stock", 0)
                    result = update_inventory_quantity(comp_sku, -comp_qty)
                    new_stock = max(old_stock - comp_qty, 0)
                    if result["success"]:
                        feedback.append(f"[STOCK] {comp_sku}: {old_stock} → {new_stock}")
                    else:
                        feedback.append(f"❌ Component SKU '{comp_sku}' not found.")
                for line in feedback[:4]:
                    st.write(line)
                if len(feedback) > 4:
                    st.write(f"...and {len(feedback) - 4} more components.")

                kit_result = update_inventory_quantity(sku_input, qty_input)
                if kit_result["success"]:
                    st.success(f"[OK] {qty_input} units of '{sku_input}' added to inventory. New total: {kit_result['new_qty']}")
                else:
                    st.warning(f"[WARN] Kit SKU '{sku_input}' could not be updated.")
            else:
                result = update_inventory_quantity(sku_input, qty_input)
                if result["success"]:
                    st.success(f"✅ {qty_input} units added to {sku_input}. Stock updated from {result['old_qty']} → {result['new_qty']}.")
                else:
                    st.error(f"❌ SKU '{sku_input}' not found in the inventory sheet.")

# Subtract Inventory Manually
with st.expander("➖ Subtract Inventory Manually", expanded=False):
    with st.form("inventory_subtract_form"):
        sku_input = st.text_input("Enter SKU to subtract").strip().upper()
        qty_input = st.number_input("Enter quantity to subtract", step=1, min_value=1)
        submitted = st.form_submit_button("Submit")
        if submitted:
            kits = load_kits_from_sheets()
            inventory = load_inventory_from_sheets()

            if sku_input in kits and sku_input in inventory:
                st.info("[KIT] Prepacked kit detected. Subtracting components from inventory.")
                feedback = []
                for comp in kits[sku_input]:
                    comp_sku = comp["sku"].strip().upper()
                    comp_qty = qty_input * float(comp["qty"])
                    old_stock = inventory.get(comp_sku, {}).get("stock", 0)
                    result = update_inventory_quantity(comp_sku, -comp_qty)
                    new_stock = max(old_stock - comp_qty, 0)
                    if result["success"]:
                        feedback.append(f"[STOCK] {comp_sku}: {old_stock} → {new_stock}")
                    else:
                        feedback.append(f"❌ Component SKU '{comp_sku}' not found.")
                for line in feedback[:4]:
                    st.write(line)
                if len(feedback) > 4:
                    st.write(f"...and {len(feedback) - 4} more components.")

                kit_result = update_inventory_quantity(sku_input, -qty_input)
                if kit_result["success"]:
                    st.success(f"[OK] {qty_input} units of '{sku_input}' subtracted. New total: {kit_result['new_qty']}")
                else:
                    st.warning(f"[WARN] Kit SKU '{sku_input}' could not be updated.")
            else:
                result = update_inventory_quantity(sku_input, -qty_input)
                if result["success"]:
                    st.success(f"✅ {qty_input} units subtracted from {sku_input}. New total: {result['new_qty']}")
                else:
                    st.error(f"❌ SKU '{sku_input}' not found in the inventory sheet.")

# Set Inventory Value Directly
with st.expander("✏️ Set Inventory Quantity Manually", expanded=False):
    with st.form("inventory_set_form"):
        sku_input = st.text_input("Enter SKU to overwrite").strip().upper()
        qty_input = st.number_input("Set stock quantity", min_value=0.0, step=1.0)
        submitted = st.form_submit_button("Set Quantity")
        if submitted:
            old_qty = inventory.get(sku_input, {}).get("stock", 0.0)
            diff = qty_input - old_qty
            result = update_inventory_quantity(sku_input, diff)
            if result["success"]:
                st.success(f"[UPDATED] {sku_input}: Overwrote from {old_qty} → {qty_input}.")
            else:
                st.error(f"❌ SKU '{sku_input}' not found in the inventory sheet.")

# Pull orders
orders = get_orders()
filtered_orders = []
for order in orders:
    payment_date_str = order.get("paymentDate")
    if not payment_date_str:
        continue
    try:
        payment_date = datetime.strptime(payment_date_str.split("T")[0], "%Y-%m-%d").date()
        if start_date <= payment_date <= end_date:
            filtered_orders.append(order)
    except:
        continue

st.write("🔎 Filter range:", start_date, "to", end_date)
with st.expander("🔍 View Filtered Payment Dates", expanded=False):
    st.write([o.get("paymentDate") for o in filtered_orders])

if not filtered_orders:
    st.warning("No orders found in the selected date range.")
    st.stop()

# Explode orders
def explode_orders(orders, kits):
    exploded = defaultdict(lambda: {"total": 0.0, "from_kits": 0.0, "standalone": 0.0})
    for order in orders:
        for item in order.get("items", []):
            sku = (item.get("sku") or '').strip().upper()
            qty = item.get("quantity", 0)
            if sku in kits:
                for comp in kits[sku]:
                    key = comp["sku"].strip().upper()
                    exploded[key]["total"] += qty * float(comp["qty"])
                    exploded[key]["from_kits"] += qty * float(comp["qty"])
                if sku in inventory_levels:
                    exploded[sku]["total"] += qty
                    exploded[sku]["standalone"] += qty
            else:
                exploded[sku]["total"] += qty
                exploded[sku]["standalone"] += qty
    return exploded

sku_totals = explode_orders(filtered_orders, kits)

# Build DataFrame
rows = []
for sku in inventory_levels:
    info = inventory_levels[sku]
    total = sku_totals.get(sku, {}).get("total", 0.0)
    from_kits = sku_totals.get(sku, {}).get("from_kits", 0.0)
    standalone = sku_totals.get(sku, {}).get("standalone", 0.0)
    stock = info.get("stock", 0.0)
    running = stock - total

    rows.append({
        "Is Kit": "✅" if sku in kits and sku in inventory_levels else "",
        "SKU": sku,
        "Product Name": info.get("name", sku),
        "Total Quantity Needed": round(total, 2),
        "From Kits": round(from_kits, 2),
        "Standalone Orders": round(standalone, 2),
        "Stock On Hand": round(stock, 2),
        "Qty Short": round(max(total - stock, 0), 2),
        "Running Inventory": round(max(running, 0), 2)
    })

df = pd.DataFrame(rows)
df = df.sort_values("Total Quantity Needed", ascending=False).reset_index(drop=True)
st.dataframe(df, use_container_width=True)

# Export CSV
csv_buffer = io.StringIO()
df.to_csv(csv_buffer, index=False)
st.download_button("📅 Download CSV", csv_buffer.getvalue(), "sku_fulfillment_summary.csv", "text/csv")
