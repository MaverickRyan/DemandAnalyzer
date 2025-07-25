# -------------------------
# 📁 app.py (Full version with kit checker restored)
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
    update_inventory_quantity,
    load_all_inventory_and_kit_skus
)
from streamlit_autorefresh import st_autorefresh

# === Session Settings ===
SESSION_TIMEOUT = 60 * 60

def password_gate():
    st.title("🔒 Secure Dashboard Login")
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

now = time.time()
auth_time = st.session_state.get("auth_time", 0)
session_age = now - auth_time
if not st.session_state.get("authenticated", False) or session_age > SESSION_TIMEOUT:
    st.session_state["authenticated"] = False
    password_gate()
    st.stop()

with st.sidebar:
    if st.session_state.get("authenticated", False):
        if st.button("🚪 Logout"):
            logout()
        # 🔄 Manual Refresh Button (moved under logout)
        if st.button("🔄 Refresh Inventory Now"):
            st.session_state["inventory"] = load_inventory_from_sheets()

st_autorefresh(interval=5 * 60 * 1000, key="inventory_autorefresh")

kits = load_kits_from_sheets()
inventory = load_inventory_from_sheets()
all_skus = load_all_inventory_and_kit_skus()

kit_names = {}
for kit_sku, components in kits.items():
    for comp in components:
        if "kit_name" in comp:
            kit_names[kit_sku] = comp["kit_name"]
            break
    if kit_sku not in kit_names:
        kit_names[kit_sku] = kit_sku

st.sidebar.header("🗓️ Filter Orders by Date")
default_start = datetime.now().date() - timedelta(days=14)
default_end = datetime.now().date()
start_date = st.sidebar.date_input("Start Date", default_start, key="filter_start_date")
end_date = st.sidebar.date_input("End Date", default_end, key="filter_end_date")

st.sidebar.markdown("---")
view_mode = st.sidebar.selectbox("📊 Select View Mode", ["Stock Components View", "Ordered SKUs View"])

st.sidebar.subheader("Inventory Controls")

# 🔎 Kit Component Checker (Restored)
st.sidebar.markdown("---")
st.sidebar.subheader("Check Kit Components")
kit_sku = st.sidebar.text_input("Enter SKU to check components").strip().upper()
if kit_sku:
    if kit_sku in kits:
        st.sidebar.success(f"{kit_sku} is a kit. Components:")
        rows = []
        for comp in kits[kit_sku]:
            comp_sku = comp.get("sku", "").strip().upper()
            qty = comp.get("qty", "")
            name = inventory.get(comp_sku, {}).get("name", "")
            rows.append({"Component SKU": comp_sku, "Quantity": qty, "Name": name})
        st.sidebar.dataframe(pd.DataFrame(rows))
    else:
        used_in = []
        for parent_kit, components in kits.items():
            for comp in components:
                if comp.get("sku", "").strip().upper() == kit_sku:
                    used_in.append({
                        "Kit SKU": parent_kit,
                        "Kit Name": kit_names.get(parent_kit, parent_kit),
                        "Quantity Used": comp.get("qty", "")
                    })
        if used_in:
            st.sidebar.info(f"{kit_sku} is not a kit but is used in the following kits:")
            st.sidebar.dataframe(pd.DataFrame(used_in))
        else:
            st.sidebar.info(f"{kit_sku} is not a kit and not used in any kit.")

st.markdown("# 🧾 SKU Fulfillment Summary")

inventory_levels = st.session_state.get("inventory", inventory)

# 📦 Add Inventory
with st.expander("➕ Add Received Inventory to Stock", expanded=False):
    with st.form("inventory_update_form"):
        sku_input = st.text_input("Enter SKU").strip().upper()
        qty_input = st.number_input("Enter quantity received", step=1, min_value=1)
        submitted = st.form_submit_button("Submit")
        if submitted:
            old_qty = inventory.get(sku_input, {}).get("stock", 0)
            result = update_inventory_quantity(sku_input, qty_input)
            if result["success"]:
                st.success(f"✅ {qty_input} units added to {sku_input}. Updated from {old_qty} → {result['new_qty']}")
            else:
                st.error(f"❌ SKU '{sku_input}' not found in the inventory sheet.")

# 📦 Subtract Inventory
with st.expander("➖ Subtract Inventory Manually", expanded=False):
    with st.form("inventory_subtract_form"):
        sku_input = st.text_input("Enter SKU to subtract").strip().upper()
        qty_input = st.number_input("Enter quantity to subtract", step=1, min_value=1)
        submitted = st.form_submit_button("Submit")
        if submitted:
            old_qty = inventory.get(sku_input, {}).get("stock", 0)
            result = update_inventory_quantity(sku_input, -qty_input)
            if result["success"]:
                st.success(f"✅ {qty_input} units subtracted from {sku_input}. Updated from {old_qty} → {result['new_qty']}")
            else:
                st.error(f"❌ SKU '{sku_input}' not found in the inventory sheet.")

# 📦 Set Inventory Value
with st.expander("✏️ Set Inventory Quantity Manually", expanded=False):
    with st.form("inventory_set_form"):
        sku_input = st.text_input("Enter SKU to overwrite").strip().upper()
        qty_input = st.number_input("Set stock quantity", min_value=0.0, step=1.0)
        password_check = st.text_input("Re-enter password", type="password")
        submitted = st.form_submit_button("Set Quantity")
        if submitted:
            if password_check != st.secrets["auth"]["set_inventory_password"]:
                st.error("❌ Incorrect password. Quantity not changed.")
            else:
                old_qty = inventory.get(sku_input, {}).get("stock", 0.0)
            diff = qty_input - old_qty
            result = update_inventory_quantity(sku_input, diff)
            if result["success"]:
                st.success(f"[UPDATED] {sku_input}: Overwrote from {old_qty} → {qty_input}.")
            else:
                st.error(f"❌ SKU '{sku_input}' not found in the inventory sheet.")

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

if not filtered_orders:
    st.warning("No orders found in the selected date range.")
    st.stop()

st.write("🔎 Filter range:", start_date, "to", end_date)

# Demand calculation
def get_sku_totals(orders, kits, inventory, separate_virtual=False):
    exploded = defaultdict(lambda: {"total": 0.0, "from_kits": 0.0, "standalone": 0.0})
    for order in orders:
        for item in order.get("items", []):
            sku = (item.get("sku") or '').strip().upper()
            qty = item.get("quantity", 0)
            if sku in kits:
                if separate_virtual:
                    exploded[sku]["total"] += qty
                    exploded[sku]["standalone"] += qty
                else:
                    for comp in kits[sku]:
                        comp_sku = comp["sku"].strip().upper()
                        exploded[comp_sku]["total"] += qty * float(comp["qty"])
                        exploded[comp_sku]["from_kits"] += qty * float(comp["qty"])
                if sku in inventory:
                    exploded[sku]["total"] += qty
                    exploded[sku]["standalone"] += qty
            else:
                exploded[sku]["total"] += qty
                exploded[sku]["standalone"] += qty
    return exploded

sku_totals = get_sku_totals(filtered_orders, kits, inventory_levels, separate_virtual=(view_mode == "Ordered SKUs View"))

display_skus = list(inventory_levels.keys()) if view_mode == "Stock Components View" else sorted(all_skus)

rows = []
for sku in display_skus:
    info = inventory_levels.get(sku, {"stock": 0.0, "name": sku})
    product_name = info.get("name") or kit_names.get(sku, sku)
    total = sku_totals.get(sku, {}).get("total", 0.0)
    from_kits = sku_totals.get(sku, {}).get("from_kits", 0.0)
    standalone = sku_totals.get(sku, {}).get("standalone", 0.0)
    stock = info.get("stock", 0.0)
    running = stock - total

    rows.append({
        "Is Kit": "✅" if sku in kits else "",
        "SKU": sku,
        "Product Name": product_name,
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

csv_buffer = io.StringIO()
df.to_csv(csv_buffer, index=False)
st.download_button("📅 Download CSV", csv_buffer.getvalue(), "sku_fulfillment_summary.csv", "text/csv")
