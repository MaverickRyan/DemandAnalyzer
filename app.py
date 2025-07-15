# -------------------------
# 📁 app.py (Streamlit-ready)
# -------------------------
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
from collections import defaultdict
from shipstation import get_orders
from sheet_loader import (
    load_kits_from_sheets,
    load_inventory_from_sheets,
    update_inventory_quantity
)

from streamlit_autorefresh import st_autorefresh
# 🔄 Auto-refresh every 5 minutes
st_autorefresh(interval=5 * 60 * 1000, key="inventory_autorefresh")

kits = load_kits_from_sheets()

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

inventory_levels = st.session_state.get("inventory", load_inventory_from_sheets())


# Sidebar filter
st.sidebar.header("🗓️ Filter Orders by Date")
default_start = datetime.now().date() - timedelta(days=14)
default_end = datetime.now().date()
start_date = st.sidebar.date_input("Start Date", default_start)
end_date = st.sidebar.date_input("End Date", default_end)

# Title and Add Inventory Form
st.title("📦 Fulfillment & Production Dashboard")
with st.expander("➕ Add Received Inventory to Stock", expanded=False):
    with st.form("inventory_update_form"):
        sku_input = st.text_input("Enter SKU").strip().upper()
        qty_input = st.number_input("Enter quantity received", step=1, min_value=1)
        submitted = st.form_submit_button("Submit")
        if submitted:
            kits = load_kits_from_sheets()
            inventory = load_inventory_from_sheets()

            if sku_input in kits and sku_input in inventory:
                st.info(f"[KIT] Prepacked kit detected. Subtracting components from inventory.")
                feedback = []
                for comp in kits[sku_input]:
                    comp_sku = comp["sku"].strip().upper()
                    comp_qty = qty_input * comp["qty"]
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

                # Finally, update the kit SKU stock level
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
    exploded = defaultdict(lambda: {"total": 0, "from_kits": 0, "standalone": 0})
    for order in orders:
        for item in order.get("items", []):
            sku = (item.get("sku") or '').strip().upper()
            qty = item.get("quantity", 0)
            if sku in kits:
                for comp in kits[sku]:
                    key = comp["sku"].strip().upper()
                    exploded[key]["total"] += qty * comp["qty"]
                    exploded[key]["from_kits"] += qty * comp["qty"]
                if sku in inventory_levels:
                    exploded[sku]["total"] += qty
                    exploded[sku]["standalone"] += qty
            else:
                exploded[sku]["total"] += qty
                exploded[sku]["standalone"] += qty
    return exploded

sku_totals = explode_orders(filtered_orders, kits)

# Build DataFrame
data = []
for sku, v in sku_totals.items():
    info = inventory_levels.get(sku, {})
    data.append({
        "Is Kit": "✅" if sku in kits and sku in inventory_levels else "",
        "SKU": sku,
        "Product Name": info.get("name", sku),
        "Total Quantity Needed": v["total"],
        "From Kits": v["from_kits"],
        "Standalone Orders": v["standalone"],
        "Stock On Hand": info.get("stock", 0)
    })

df = pd.DataFrame(data)
if df.empty:
    st.warning("No data to display.")
    st.stop()

# Filter relevant SKUs
valid_skus = set(kits.keys()) | {comp["sku"] for kit in kits.values() for comp in kit} | set(inventory_levels.keys())
df = df[df["SKU"].isin(valid_skus)]

# Final calculations
df["Qty Short"] = (df["Total Quantity Needed"] - df["Stock On Hand"]).clip(lower=0)
df["Running Inventory"] = (df["Stock On Hand"] - df["Total Quantity Needed"]).clip(lower=0)

# Display
df = df.sort_values("Total Quantity Needed", ascending=False).reset_index(drop=True)
st.dataframe(df, use_container_width=True)

# Download
csv_buffer = io.StringIO()
df.to_csv(csv_buffer, index=False)
st.download_button("📅 Download CSV", csv_buffer.getvalue(), "sku_fulfillment_summary.csv", "text/csv")
