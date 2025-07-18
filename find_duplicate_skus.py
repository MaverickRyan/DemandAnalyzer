import os
import requests
import csv
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

SHOP_URL = os.getenv("SHOPIFY_SHOP_URL")
ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")

if not SHOP_URL or not ACCESS_TOKEN:
    raise ValueError("Missing SHOPIFY_SHOP_URL or SHOPIFY_ACCESS_TOKEN in .env")

HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

def fetch_all_products():
    endpoint = f"https://{SHOP_URL}/admin/api/2023-10/products.json?limit=250"
    variants = []

    while endpoint:
        response = requests.get(endpoint, headers=HEADERS)
        response.raise_for_status()
        products = response.json().get("products", [])
        for product in products:
            for variant in product.get("variants", []):
                sku = (variant.get("sku") or "").strip().upper()
                variants.append({
                    "sku": sku,
                    "product_title": product.get("title"),
                    "variant_title": variant.get("title"),
                    "variant_id": variant.get("id"),
                    "product_id": product.get("id"),
                    "archived": product.get("status", "") == "archived"
                })

        link_header = response.headers.get("Link", "")
        next_url = None
        for link in link_header.split(","):
            if 'rel="next"' in link:
                next_url = link[link.find("<")+1:link.find(">")]
                break
        endpoint = next_url

    return variants

def find_duplicates(variants):
    sku_map = defaultdict(list)
    for v in variants:
        if v["sku"]:
            sku_map[v["sku"]].append(v)

    return {sku: entries for sku, entries in sku_map.items() if len(entries) > 1}

def export_duplicates_to_csv(duplicates, filename="duplicate_skus.csv"):
    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "SKU", "Product Title", "Variant Title", "Variant ID",
            "Product ID", "Archived"
        ])
        for sku, entries in duplicates.items():
            for v in entries:
                writer.writerow([
                    sku, v["product_title"], v["variant_title"],
                    v["variant_id"], v["product_id"],
                    "Yes" if v["archived"] else "No"
                ])
    print(f"📁 Saved duplicates to {filename}")

if __name__ == "__main__":
    print("🔍 Fetching all product variants...")
    variants = fetch_all_products()
    print(f"✅ Retrieved {len(variants)} variants")

    duplicates = find_duplicates(variants)
    if not duplicates:
        print("🎉 No duplicate SKUs found.")
    else:
        print(f"⚠️ Found {len(duplicates)} duplicate SKUs:")
        for sku, entries in duplicates.items():
            print(f"\n🔁 SKU: {sku}")
            for v in entries:
                archived = " [ARCHIVED]" if v["archived"] else ""
                print(f"  - Product: {v['product_title']} | Variant: {v['variant_title']} | ID: {v['variant_id']}{archived}")

        export_duplicates_to_csv(duplicates)
