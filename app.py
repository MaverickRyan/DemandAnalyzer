# 📁 app.py
import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
from collections import defaultdict
from shipstation import get_orders
from sheet_loader import load_kits_from_sheets, load_inventory_from_sheets

# Load Google Sheet data
kits = load_kits_from_sheets()
inventory_levels = load_inventory_from_sheets()

# Sidebar filter
st.sidebar.header("🗓️ Filter Orders by Date")
default_start = datetime.now().date() - timedelta(days=14)
default_end = datetime.now().date()
start_date = st.sidebar.date_input("Start Date", default_start)
end_date = st.sidebar.date_input("End Date", default_end)

# Title
st.title("📦 Fulfillment & Production Dashboard")
with st.expander("📦 Add Received Inventory", expanded=False):
    with st.form("add_inventory_form"):
        sku_input = st.text_input("Enter SKU").strip().upper()
        qty_input = st.number_input("Enter quantity received", step=1, min_value=1)
        submitted = st.form_submit_button("Add to Inventory")

        if submitted:
            from sheet_loader import update_inventory_quantity
            success = update_inventory_quantity(sku_input, qty_input)
            if success:
                st.success(f"✅ {qty_input} units added to {sku_input}.")
            else:
                st.error(f"❌ SKU '{sku_input}' not found in the inventory sheet.")

# Load & filter orders
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
    except Exception as e:
        st.write("Skipping order due to date parsing error:", order)

st.write("🔎 Filter range:", start_date, "to", end_date)

with st.expander("🔍 View Filtered Payment Dates", expanded=False):
    st.write([o.get("paymentDate") for o in filtered_orders])

if not filtered_orders:
    st.warning("No orders found in the selected date range.")
    st.stop()

# Function to explode orders into component SKUs
def explode_orders(orders, kits):
    exploded = defaultdict(lambda: {"total": 0, "from_kits": 0, "standalone": 0})
    for order in orders:
        items = order.get('items')
        if not items:
            continue

        for item in items:
            sku = (item.get('sku') or '').strip().upper()
            qty = item.get('quantity', 0)
            item_name = (item.get('name') or 'Unknown').strip()

            if sku in kits:
                for comp in kits[sku]:
                    key = (comp["sku"], comp["name"])
                    exploded[key]["total"] += qty * comp["qty"]
                    exploded[key]["from_kits"] += qty * comp["qty"]

                # Also include the kit SKU itself if stocked
                if sku in inventory_levels:
                    key = (sku, item_name)
                    exploded[key]["total"] += qty
                    exploded[key]["standalone"] += qty
            else:
                key = (sku, item_name)
                exploded[key]["total"] += qty
                exploded[key]["standalone"] += qty
    return exploded

# Explode data
sku_totals = explode_orders(filtered_orders, kits)

# Build dataframe
df = pd.DataFrame([
    {
        "SKU": k[0],
        "Product Name": k[1],
        "Total Quantity Needed": v["total"],
        "From Kits": v["from_kits"],
        "Standalone Orders": v["standalone"],
        "Stock On Hand": inventory_levels.get(k[0], 0),
        "Is Kit": "✅" if k[0] in kits and k[0] in inventory_levels else ""
    }
    for k, v in sku_totals.items()
])

if df.empty:
    st.warning("No data to display. Check your kits or order contents.")
    st.stop()

# Filter output to only show relevant SKUs (including prepacked kits, components, and inventory SKUs)
kit_component_skus = {comp["sku"] for kit in kits.values() for comp in kit}
kit_skus = set(kits.keys())
inventory_skus = set(inventory_levels.keys())
valid_skus = kit_component_skus.union(kit_skus).union(inventory_skus)
df = df[df["SKU"].notna() & df["SKU"].str.upper().isin({sku.upper() for sku in valid_skus})]

# Calculate shortage
df["Qty Short"] = df["Total Quantity Needed"] - df["Stock On Hand"]
df["Qty Short"] = df["Qty Short"].apply(lambda x: max(x, 0))

# Sort and display
df = df.sort_values(by="Total Quantity Needed", ascending=False).reset_index(drop=True)
st.dataframe(df, use_container_width=True)

# Export CSV
csv_buffer = io.StringIO()
df.to_csv(csv_buffer, index=False)
st.download_button(
    label="📅 Download CSV",
    data=csv_buffer.getvalue(),
    file_name="sku_fulfillment_summary.csv",
    mime="text/csv"
)
