"""Add all created cards to the 3 dashboards using PUT with negative IDs."""
import json, sys, requests

MB_URL = "http://localhost:3000/api"
MB_TOKEN = "49b96967-9de3-41f8-86ae-249410b03d03"
HEADERS = {"X-Metabase-Session": MB_TOKEN, "Content-Type": "application/json"}

# Card IDs (created by first script):
# Dashboard 1: Business Performance Overview
cards1 = [
    {"card_id": 27, "row": 0, "col": 0, "size_x": 12, "size_y": 4},   # KPI Summary
    {"card_id": 28, "row": 4, "col": 0, "size_x": 6,  "size_y": 4},   # Revenue Trend
    {"card_id": 29, "row": 4, "col": 6, "size_x": 6,  "size_y": 4},   # Rev by Category
    {"card_id": 30, "row": 8, "col": 0, "size_x": 6,  "size_y": 4},   # Contribution
    {"card_id": 31, "row": 8, "col": 6, "size_x": 6,  "size_y": 4},   # Gross Margin
    {"card_id": 32, "row": 12, "col": 0, "size_x": 6, "size_y": 3},   # Customer Summary
    {"card_id": 33, "row": 12, "col": 6, "size_x": 6, "size_y": 3},   # Migration Stats
]

# Dashboard 2: Product & Customer Analytics
cards2 = [
    {"card_id": 34, "row": 0, "col": 0, "size_x": 8, "size_y": 4},    # Segments
    {"card_id": 35, "row": 0, "col": 8, "size_x": 4, "size_y": 4},    # Segment Details
    {"card_id": 36, "row": 4, "col": 0, "size_x": 6, "size_y": 4},    # Product Revenue
    {"card_id": 37, "row": 4, "col": 6, "size_x": 6, "size_y": 4},    # Top 10 Products
    {"card_id": 38, "row": 8, "col": 0, "size_x": 4, "size_y": 4},    # Rev by Cust Type
    {"card_id": 39, "row": 8, "col": 4, "size_x": 8, "size_y": 4},    # Decision Support
    {"card_id": 40, "row": 12, "col": 0, "size_x": 12, "size_y": 4},  # RFM Snapshot
]

# Dashboard 3: Inventory & Operational Decision Support
cards3 = [
    {"card_id": 41, "row": 0, "col": 0, "size_x": 12, "size_y": 4},   # Anomaly Flags
    {"card_id": 42, "row": 4, "col": 0, "size_x": 6, "size_y": 4},    # Turnover Trend
    {"card_id": 43, "row": 4, "col": 6, "size_x": 6, "size_y": 4},    # Anomaly Category
    {"card_id": 44, "row": 8, "col": 0, "size_x": 12, "size_y": 4},   # Op Decision Support
    {"card_id": 45, "row": 12, "col": 0, "size_x": 6, "size_y": 4},   # Inv Value by Cat
    {"card_id": 46, "row": 12, "col": 6, "size_x": 6, "size_y": 4},   # Migration Summary
]

def build_payload(cards, start_id=-1):
    """Build dashcards payload with sequential negative IDs."""
    dashcards = []
    for i, card in enumerate(cards):
        dc = {
            "id": start_id - i,
            "card_id": card["card_id"],
            "row": card["row"],
            "col": card["col"],
            "size_x": card["size_x"],
            "size_y": card["size_y"],
            "parameter_mappings": [],
            "visualization_settings": {},
            "dashboard_tab_id": None,
        }
        dashcards.append(dc)
    return {"dashcards": dashcards}

def add_to_dashboard(dash_id, cards):
    payload = build_payload(cards)
    resp = requests.put(f"{MB_URL}/dashboard/{dash_id}", headers=HEADERS, json=payload)
    if resp.status_code >= 400:
        print(f"  ERROR dashboard {dash_id}: {resp.status_code} {resp.text[:200]}")
        return False
    data = resp.json()
    count = len(data.get("dashcards", []))
    print(f"  Dashboard {dash_id}: {count} dashcards added")
    return True

print("=== Adding cards to Business Performance Overview (id=2) ===")
add_to_dashboard(2, cards1)

print("\n=== Adding cards to Product & Customer Analytics (id=3) ===")
add_to_dashboard(3, cards2)

print("\n=== Adding cards to Inventory & Operational Decision Support (id=4) ===")
add_to_dashboard(4, cards3)

print("\n=== All dashboards populated! ===")
