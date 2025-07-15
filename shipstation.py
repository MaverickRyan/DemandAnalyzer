# -----------------------------
# 📁 shipstation.py (Streamlit-ready)
# -----------------------------
import requests
import base64
import streamlit as st

def get_orders(order_status="awaiting_shipment"):
    API_KEY = st.secrets["SHIPSTATION_API_KEY"]
    API_SECRET = st.secrets["SHIPSTATION_API_SECRET"]
    url = 'https://ssapi.shipstation.com/orders'
    auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth}',
        'Content-Type': 'application/json'
    }
    all_orders = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        params = {
            'pageSize': 500,
            'page': page,
            'sortBy': 'modifyDate',
            'sortDir': 'DESC',
            'orderStatus': order_status
        }
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            all_orders.extend(data.get('orders', []))
            total_pages = data.get('pages', 1)
            page += 1
        except requests.RequestException as e:
            print("Error fetching orders:", e)
            break
    return all_orders
