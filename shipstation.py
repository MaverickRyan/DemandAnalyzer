import requests
import base64
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

API_KEY = os.getenv("SHIPSTATION_API_KEY")
API_SECRET = os.getenv("SHIPSTATION_API_SECRET")

if not API_KEY or not API_SECRET:
    raise ValueError("Missing SHIPSTATION_API_KEY or SHIPSTATION_API_SECRET in .env")

def get_orders():
    url = 'https://ssapi.shipstation.com/orders'
    auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth}',
        'Content-Type': 'application/json'
    }

    all_orders = []
    page = 1
    total_pages = 1  # will update after first request

    while page <= total_pages:
        params = {
            'pageSize': 500,
            'page': page,
            'sortBy': 'modifyDate',
            'sortDir': 'DESC',
            'orderStatus': 'awaiting_shipment'
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            all_orders.extend(data.get('orders', []))
            total_pages = data.get('pages', 1)  # total number of pages from API
            page += 1

        except requests.RequestException as e:
            print("Error fetching orders:", e)
            break

    return all_orders


    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('orders', [])
    except requests.RequestException as e:
        print("Error fetching orders:", e)
        return []