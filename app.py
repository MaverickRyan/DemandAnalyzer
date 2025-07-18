# 📁 app.py (Final clean version)
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

# Title
st.title("📦 Fulfillment & Production Dashboard")
st.caption(f"🔄 Last Refreshed: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")

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
