"""Rebuild 3 Metabase dashboards per chuẩn spec — 24-col grid, combo, heatmap, bubble, donut."""
import json, sys, os, time
import requests

MB_URL = os.getenv("MB_URL", "http://localhost:3000/api")
MB_EMAIL = os.getenv("MB_EMAIL", "admin@example.com")
MB_PASS = os.getenv("MB_PASS", "KW9!xPzLmQvR7")
DB_ID = 2
COLLECTION_ID = None

P = "2014Q2"
Q = "2014Q1"

def log(msg):
    print(f"  {msg}")

def api(method, path, data=None, token=None):
    url = f"{MB_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Metabase-Session"] = token
    r = requests.request(method, url, headers=headers, json=data)
    if r.status_code >= 400:
        log(f"WARN {method} {path}: {r.status_code} {r.text[:200]}")
        return None
    if r.status_code == 204 or not r.text.strip():
        return {"ok": True}
    return r.json()

def login():
    props = api("GET", "/session/properties")
    if not props: raise RuntimeError("Cannot reach Metabase")
    tk = props.get("setup-token")
    if not props.get("has-user-setup") and tk:
        r = api("POST", "/setup", {"token": tk, "user": {"first_name": "Admin", "last_name": "User", "email": MB_EMAIL, "password": MB_PASS}, "prefs": {"site_name": "AdventureWorks BI", "site_locale": "en", "allow_tracking": False}})
        if r and r.get("id"): return r["id"]
    r = api("POST", "/session", {"username": MB_EMAIL, "password": MB_PASS})
    if r and r.get("id"): return r["id"]
    raise RuntimeError(f"Login failed: {r}")

def card(name, sql, display="table", desc=None, viz=None, token=None):
    payload = {"name": name, "display": display, "dataset_query": {"database": DB_ID, "type": "native", "native": {"query": sql, "template-tags": {}}}, "visualization_settings": viz or {}, "collection_id": COLLECTION_ID}
    if desc: payload["description"] = desc
    r = api("POST", "/card", payload, token=token)
    return r.get("id") if r else None

def text_card(name, content, token=None):
    """Create a text/heading card."""
    return card(name, "SELECT 1 AS _", "scalar", viz={"text": content, "text.align_vertical": "middle", "text.align_horizontal": "center"}, token=token)

def dashboard(name, desc="", token=None):
    r = api("POST", "/dashboard", {"name": name, "description": desc, "collection_id": COLLECTION_ID}, token=token)
    return r.get("id") if r else None

def add_cards(dash_id, cards, token=None):
    dc = []
    for i, c in enumerate(cards):
        dc.append({"id": -(i+1), "card_id": c["card_id"], "row": c["row"], "col": c["col"], "size_x": c["size_x"], "size_y": c["size_y"], "parameter_mappings": [], "visualization_settings": {}, "dashboard_tab_id": None})
    r = api("PUT", f"/dashboard/{dash_id}", {"dashcards": dc}, token=token)
    log(f"  {len(dc)} cards → dashboard {dash_id}")
    return r

def cleanup(token):
    # Archive old cards
    for c in (api("GET", "/card", token=token) or []):
        if not c.get("archived"):
            api("PUT", f"/card/{c['id']}", {"archived": True}, token=token)
    # Delete old dashboards
    for d in (api("GET", "/dashboard", token=token) or []):
        api("DELETE", f"/dashboard/{d['id']}", token=token)
    log("Cleaned up old dashboards & cards")

# ══════════════════════════════════════════════════════════════════════
# DASHBOARD 1: Business Performance Overview
# ══════════════════════════════════════════════════════════════════════
def build_d1(token):
    log("\n=== Dashboard 1: Business Performance Overview ===")
    ids = []

    # Text heading
    ids.append(text_card("D1-H · Business Performance Overview",
        "## 📊 Business Performance Overview\n\n"
        f"**Period:** {P} vs {Q}  |  **Source:** mart.kpi_snapshot (snapshot theo quý)  |  "
        "**Flow:** KPI → Trend → Contribution → Table", token))

    # C1: Revenue
    ids.append(card("C1 · Revenue — " + P,
        f"SELECT ROUND(value/1000000.0,2) AS \"Revenue ($M)\" FROM mart.kpi_snapshot WHERE kpi_name='revenue' AND period_key='{P}' AND dimension='overall'",
        "scalar", viz={"scalar.field": "Revenue ($M)"}, token=token))

    # C2: Gross Profit
    ids.append(card("C2 · Gross Profit — " + P,
        f"SELECT ROUND(value/1000000.0,2) AS \"Gross Profit ($M)\" FROM mart.kpi_snapshot WHERE kpi_name='gross_profit' AND period_key='{P}' AND dimension='overall'",
        "scalar", viz={"scalar.field": "Gross Profit ($M)"}, token=token))

    # C3: Gross Margin %
    ids.append(card("C3 · Gross Margin % — " + P,
        f"SELECT ROUND(value,2) AS \"Gross Margin (%)\" FROM mart.kpi_snapshot WHERE kpi_name='gross_margin_pct' AND period_key='{P}' AND dimension='overall'",
        "scalar", viz={"scalar.field": "Gross Margin (%)"}, token=token))

    # C4: Orders
    ids.append(card("C4 · Orders — " + P,
        f"SELECT ROUND(value,0) AS \"Orders\" FROM mart.kpi_snapshot WHERE kpi_name='order_count' AND period_key='{P}' AND dimension='overall'",
        "scalar", viz={"scalar.field": "Orders"}, token=token))

    # C5: Revenue & Gross Profit Trend — Combo
    ids.append(card("C5 · Revenue & Gross Profit Trend by Quarter",
        "SELECT period_key AS \"Period\", ROUND(MAX(CASE WHEN kpi_name='revenue' THEN value END)/1000000.0,2) AS \"Revenue ($M)\", ROUND(MAX(CASE WHEN kpi_name='gross_profit' THEN value END)/1000000.0,2) AS \"Gross Profit ($M)\" FROM mart.kpi_snapshot WHERE dimension='overall' AND kpi_name IN ('revenue','gross_profit') AND period_key BETWEEN '2011Q2' AND '2014Q2' GROUP BY period_key ORDER BY period_key",
        "combo", desc="Revenue = bar, Gross Profit = line",
        viz={"series_settings": {"Revenue ($M)": {"display": "bar"}, "Gross Profit ($M)": {"display": "line"}}, "graph.colors": ["#2563EB", "#16A34A"]}, token=token))

    # C6: Gross Margin % Trend
    ids.append(card("C6 · Gross Margin % Trend by Quarter",
        "SELECT period_key AS \"Period\", ROUND(value,2) AS \"Gross Margin (%)\" FROM mart.kpi_snapshot WHERE kpi_name='gross_margin_pct' AND dimension='overall' AND period_key BETWEEN '2011Q2' AND '2014Q2' ORDER BY period_key",
        "line", viz={"graph.colors": ["#7C3AED"]}, token=token))

    # C7: Revenue by Category
    ids.append(card("C7 · Revenue by Category — " + P,
        f"SELECT dimension_value AS \"Category\", ROUND(value/1000000.0,2) AS \"Revenue ($M)\" FROM mart.kpi_snapshot WHERE kpi_name='revenue_by_category' AND period_key='{P}' ORDER BY value DESC",
        "bar", viz={"graph.colors": {"Bikes": "#2563EB", "Components": "#7C3AED", "Clothing": "#EC4899", "Accessories": "#14B8A6"}}, token=token))

    # C8: Contribution by Category (horizontal bar)
    ids.append(card("C8 · Revenue Change Contribution by Category — " + P + " vs " + Q,
        f"SELECT dimension_value AS \"Category\", ROUND(contribution_pct,2) AS \"Contribution (%)\", ROUND(pct_change,2) AS \"Change (%)\" FROM mart.period_comparison WHERE kpi_name='revenue' AND curr_period_key='{P}' AND dimension='category' ORDER BY contribution_pct ASC",
        "row", viz={"graph.colors": ["#DC2626", "#16A34A"]}, token=token))

    # C9: Contribution by Territory (horizontal bar)
    ids.append(card("C9 · Revenue Change Contribution by Territory — " + P + " vs " + Q,
        f"SELECT dimension_value AS \"Territory\", ROUND(contribution_pct,2) AS \"Contribution (%)\", ROUND(pct_change,2) AS \"Change (%)\" FROM mart.period_comparison WHERE kpi_name='revenue' AND curr_period_key='{P}' AND dimension='territory' ORDER BY ABS(contribution_pct) DESC LIMIT 10",
        "row", viz={"graph.colors": ["#DC2626", "#16A34A"]}, token=token))

    # C10: KPI Comparison Table (use kpi_snapshot since period_comparison has no 'overall' dimension)
    ids.append(card("C10 · KPI Comparison — " + P + " vs " + Q,
        f"SELECT kpi_name AS \"KPI\", ROUND(MAX(CASE WHEN period_key='{P}' THEN value END),2) AS \"{P}\", ROUND(MAX(CASE WHEN period_key='{Q}' THEN value END),2) AS \"{Q}\", ROUND(MAX(CASE WHEN period_key='{P}' THEN value END)-MAX(CASE WHEN period_key='{Q}' THEN value END),2) AS \"Δ\", ROUND(CASE WHEN MAX(CASE WHEN period_key='{Q}' THEN value END)<>0 THEN (MAX(CASE WHEN period_key='{P}' THEN value END)-MAX(CASE WHEN period_key='{Q}' THEN value END))*100.0/MAX(CASE WHEN period_key='{Q}' THEN value END) ELSE NULL END,2) AS \"Δ %\" FROM mart.kpi_snapshot WHERE period_key IN ('{P}','{Q}') AND dimension='overall' AND kpi_name IN ('revenue','gross_profit','gross_margin_pct','order_count','total_customers','avg_order_value','revenue_per_customer') GROUP BY kpi_name ORDER BY kpi_name",
        "table", viz={}, token=token))

    # Build dashboard
    d1 = dashboard("Business Performance Overview",
        "KPI snapshot theo quý, trend, root-cause contribution. Source: mart.kpi_snapshot, mart.period_comparison.", token)
    if d1:
        add_cards(d1, [
            # Row 0: Text heading
            {"card_id": ids[0], "row": 0, "col": 0, "size_x": 24, "size_y": 2},
            # Row 1: 4 scalar
            {"card_id": ids[1], "row": 2, "col": 0, "size_x": 6, "size_y": 3},
            {"card_id": ids[2], "row": 2, "col": 6, "size_x": 6, "size_y": 3},
            {"card_id": ids[3], "row": 2, "col": 12, "size_x": 6, "size_y": 3},
            {"card_id": ids[4], "row": 2, "col": 18, "size_x": 6, "size_y": 3},
            # Row 2: Combo full
            {"card_id": ids[5], "row": 5, "col": 0, "size_x": 24, "size_y": 6},
            # Row 3: Line + Bar
            {"card_id": ids[6], "row": 11, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": ids[7], "row": 11, "col": 12, "size_x": 12, "size_y": 6},
            # Row 4: Horizontal bars
            {"card_id": ids[8], "row": 17, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": ids[9], "row": 17, "col": 12, "size_x": 12, "size_y": 6},
            # Row 5: Table full
            {"card_id": ids[10], "row": 23, "col": 0, "size_x": 24, "size_y": 6},
        ], token)
        log(f"Dashboard 1 created: id={d1}")
    return d1, ids

# ══════════════════════════════════════════════════════════════════════
# DASHBOARD 2: Product & Customer Analytics
# ══════════════════════════════════════════════════════════════════════
def build_d2(token):
    log("\n=== Dashboard 2: Product & Customer Analytics ===")
    ids = []

    # Text heading
    ids.append(text_card("D2-H · Product & Customer Analytics",
        "## 🛒 Product & Customer Analytics\n\n"
        "RFM Segmentation (K-Means K=3), Product ABC classification, Customer behavior.  "
        "**Source:** dw.ml_customer_segments, mart.rfm_snapshot, dw.fact_sales", token))

    # C1: Active Customers
    ids.append(card("C1 · Active Customers — " + P,
        "SELECT COUNT(DISTINCT f.customer_key) AS \"Active Customers\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'",
        "scalar", token=token))

    # C2: Active Products
    ids.append(card("C2 · Active Products — " + P,
        "SELECT COUNT(DISTINCT f.product_key) AS \"Active Products\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'",
        "scalar", token=token))

    # C3: Units Sold
    ids.append(card("C3 · Units Sold — " + P,
        "SELECT SUM(f.order_qty) AS \"Units Sold\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'",
        "scalar", token=token))

    # C4: Revenue / Customer
    ids.append(card("C4 · Revenue per Customer — " + P,
        "SELECT ROUND(SUM(f.line_total)/NULLIF(COUNT(DISTINCT f.customer_key),0),2) AS \"Revenue/Customer\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'",
        "scalar", token=token))

    # C5: Customer Segments — RFM K-Means (K=3)
    ids.append(card("C5 · Customer Segments — RFM K-Means (K=3)",
        "SELECT cluster_label AS \"Segment\", COUNT(*) AS \"Customers\", ROUND(SUM(monetary),0) AS \"Total ($)\" FROM dw.ml_customer_segments GROUP BY cluster_label ORDER BY \"Customers\" DESC",
        "bar", desc="K=3, silhouette≈0.48",
        viz={"graph.colors": {"Champions": "#F59E0B", "Loyal Customers": "#2563EB", "Potential Loyalists": "#10B981"}}, token=token))

    # C6: RFM Segment Details
    ids.append(card("C6 · RFM Segment Details",
        "SELECT cluster_label AS \"Segment\", COUNT(*) AS \"Customers\", ROUND(AVG(recency_days),1) AS \"Avg Recency (d)\", ROUND(AVG(frequency),1) AS \"Avg Frequency\", ROUND(AVG(monetary),2) AS \"Avg Monetary\" FROM dw.ml_customer_segments GROUP BY cluster_label ORDER BY \"Customers\" DESC",
        "table", token=token))

    # C7: ABC Product Class
    ids.append(card("C7 · Revenue Share by ABC Product Class — " + P,
        "WITH prod AS (SELECT p.product_key, SUM(f.line_total) AS rev FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key JOIN dw.dim_product p ON f.product_key=p.product_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30' GROUP BY p.product_key), ranked AS (SELECT rev, SUM(rev) OVER (ORDER BY rev DESC) / NULLIF(SUM(rev) OVER (),0) AS cum_share FROM prod) SELECT CASE WHEN cum_share<=0.8 THEN 'A - Core' WHEN cum_share<=0.95 THEN 'B - Support' ELSE 'C - Long Tail' END AS \"ABC Class\", COUNT(*) AS \"Products\", ROUND(SUM(rev)/1000000.0,2) AS \"Revenue ($M)\" FROM ranked GROUP BY 1 ORDER BY 1",
        "bar", viz={"graph.colors": {"A - Core": "#16A34A", "B - Support": "#F59E0B", "C - Long Tail": "#94A3B8"}}, token=token))

    # C8: Top 10 Products
    ids.append(card("C8 · Top 10 Products by Revenue — " + P,
        "SELECT p.name AS \"Product\", ROUND(SUM(f.line_total)/1000000.0,2) AS \"Revenue ($M)\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key JOIN dw.dim_product p ON f.product_key=p.product_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30' GROUP BY p.name ORDER BY \"Revenue ($M)\" DESC LIMIT 10",
        "row", viz={"graph.colors": ["#2563EB"]}, token=token))

    # C9: Top 10 Customers
    ids.append(card("C9 · Top 10 Customers — " + P,
        "SELECT c.full_name AS \"Customer\", c.customer_type AS \"Type\", c.country AS \"Country\", COUNT(DISTINCT f.sales_order_id) AS \"Orders\", ROUND(SUM(f.line_total),0) AS \"Revenue\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key JOIN dw.dim_customer c ON f.customer_key=c.customer_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30' GROUP BY c.full_name,c.customer_type,c.country ORDER BY \"Revenue\" DESC LIMIT 10",
        "table", token=token))

    # C10: Customer Segment Share by Quarter
    ids.append(card("C10 · Customer Segment Share by Quarter",
        "SELECT period_key AS \"Period\", cluster_label AS \"Segment\", ROUND(pct_of_total,2) AS \"Share (%)\" FROM mart.rfm_snapshot WHERE period_key BETWEEN '2013Q1' AND '2014Q2' ORDER BY period_key, cluster_label",
        "line", viz={"graph.colors": {"Champions": "#F59E0B", "Loyal Customers": "#2563EB", "Potential Loyalists": "#10B981"}}, token=token))

    # C11: Revenue by Territory — Donut
    ids.append(card("C11 · Revenue by Territory — " + P,
        "SELECT t.territory_name AS \"Territory\", ROUND(SUM(f.line_total)/1000000.0,2) AS \"Revenue ($M)\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key JOIN dw.dim_territory t ON f.territory_key=t.territory_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30' GROUP BY t.territory_name ORDER BY \"Revenue ($M)\" DESC",
        "pie", viz={"pie.show_total": True, "pie.show_legend": True, "pie.colors": {}}, token=token))

    # C12: Revenue Heatmap — Customer Type × Category (pivoted SQL → table + color-scale)
    ids.append(card("C12 · Revenue Heatmap — Customer Type × Category (" + P + ")",
        "SELECT c.customer_type AS \"Customer Type\", ROUND(SUM(f.line_total) FILTER (WHERE p.category='Bikes')/1e6,3) AS \"Bikes\", ROUND(SUM(f.line_total) FILTER (WHERE p.category='Components')/1e6,3) AS \"Components\", ROUND(SUM(f.line_total) FILTER (WHERE p.category='Clothing')/1e6,3) AS \"Clothing\", ROUND(SUM(f.line_total) FILTER (WHERE p.category='Accessories')/1e6,3) AS \"Accessories\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key JOIN dw.dim_customer c ON f.customer_key=c.customer_key JOIN dw.dim_product p ON f.product_key=p.product_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30' GROUP BY c.customer_type",
        "table", viz={"table.column_formatting": [{"columns": ["Bikes", "Components", "Clothing", "Accessories"], "type": "color", "color_condition": "not_null", "color": "#2563EB"}]}, token=token))

    # C13: Gross Margin % by Category
    ids.append(card("C13 · Gross Margin % by Category — " + P,
        "SELECT p.category AS \"Category\", ROUND(SUM(f.gross_profit)/NULLIF(SUM(f.line_total),0)*100,1) AS \"Gross Margin (%)\" FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key JOIN dw.dim_product p ON f.product_key=p.product_key WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30' GROUP BY p.category ORDER BY \"Gross Margin (%)\" DESC",
        "bar", viz={"graph.colors": {"Bikes": "#2563EB", "Components": "#7C3AED", "Clothing": "#EC4899", "Accessories": "#14B8A6"}}, token=token))

    # C14: Cost vs Selling Price — Scatter
    ids.append(card("C14 · Cost vs Selling Price by Product",
        "SELECT p.name AS \"Product\", p.category AS \"Category\", p.standard_cost AS \"Cost\", p.list_price AS \"Price\", ROUND(SUM(f.line_total)/1000000.0,2) AS \"Revenue ($M)\" FROM dw.dim_product p JOIN dw.fact_sales f ON p.product_key=f.product_key WHERE p.is_current AND p.list_price>0 GROUP BY p.name, p.category, p.standard_cost, p.list_price ORDER BY \"Revenue ($M)\" DESC LIMIT 100",
        "scatter", viz={"graph.dimensions": ["Cost"], "graph.metrics": ["Price"]}, token=token))

    d2 = dashboard("Product & Customer Analytics",
        "RFM segmentation (K=3), ABC classification, customer behavior. Source: dw.ml_customer_segments, mart.rfm_snapshot, dw.fact_sales.", token)
    if d2:
        add_cards(d2, [
            {"card_id": ids[0], "row": 0, "col": 0, "size_x": 24, "size_y": 2},
            {"card_id": ids[1], "row": 2, "col": 0, "size_x": 6, "size_y": 3},
            {"card_id": ids[2], "row": 2, "col": 6, "size_x": 6, "size_y": 3},
            {"card_id": ids[3], "row": 2, "col": 12, "size_x": 6, "size_y": 3},
            {"card_id": ids[4], "row": 2, "col": 18, "size_x": 6, "size_y": 3},
            {"card_id": ids[5], "row": 5, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": ids[6], "row": 5, "col": 12, "size_x": 12, "size_y": 6},
            {"card_id": ids[7], "row": 11, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": ids[8], "row": 11, "col": 12, "size_x": 12, "size_y": 6},
            {"card_id": ids[9], "row": 17, "col": 0, "size_x": 24, "size_y": 6},
            {"card_id": ids[10], "row": 23, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": ids[11], "row": 23, "col": 12, "size_x": 12, "size_y": 6},
            {"card_id": ids[12], "row": 29, "col": 0, "size_x": 24, "size_y": 6},
            {"card_id": ids[13], "row": 35, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": ids[14], "row": 35, "col": 12, "size_x": 12, "size_y": 6},
        ], token)
        log(f"Dashboard 2 created: id={d2}")
    return d2, ids

# ══════════════════════════════════════════════════════════════════════
# DASHBOARD 3: Inventory & Operational Decision Support
# ══════════════════════════════════════════════════════════════════════
def build_d3(token):
    log("\n=== Dashboard 3: Inventory & Operational Decision Support ===")
    ids = []

    # Text heading
    ids.append(text_card("D3-H · Inventory & Operational Decision Support",
        "## 📦 Inventory & Operational Decision Support\n\n"
        "Inventory Risk / Zero-Sales Warning, Decision Support actions.  "
        "**Source:** dw.ml_inventory_anomaly, dw.decision_support, dw.fact_inventory  |  "
        "**Wording:** Risk / Zero-Sales Warning (anomaly_flag = 0)", token))

    # C1: Inventory Risk Products
    ids.append(card("C1 · Inventory Risk Products",
        "SELECT COUNT(*) AS \"Risk Products\" FROM dw.ml_inventory_anomaly WHERE anomaly_flag = true OR zero_sales_flag = true",
        "scalar", viz={"scalar.field": "Risk Products"}, token=token))

    # C2: Zero-Sales Warnings
    ids.append(card("C2 · Zero-Sales Warnings",
        "SELECT COUNT(*) AS \"Zero-Sales\" FROM dw.ml_inventory_anomaly WHERE zero_sales_flag = true",
        "scalar", viz={"scalar.field": "Zero-Sales"}, token=token))

    # C3: High-Priority Actions
    ids.append(card("C3 · High-Priority Actions",
        "SELECT COUNT(*) AS \"High Priority\" FROM dw.decision_support WHERE priority='HIGH'",
        "scalar", viz={"scalar.field": "High Priority"}, token=token))

    # C4: Total Inventory Value
    ids.append(card("C4 · Total Inventory Value",
        "SELECT ROUND(SUM(inventory_value),0) AS \"Inv Value ($)\" FROM dw.ml_inventory_anomaly",
        "scalar", viz={"scalar.field": "Inv Value ($)"}, token=token))

    # C5: Risk Flags Table
    ids.append(card("C5 · Zero-Sales & Slow-Moving Products",
        "SELECT product_name AS \"Product\", category AS \"Category\", ROUND(inventory_value,0) AS \"Inv Value\", units_sold AS \"Units Sold\", ROUND(days_inventory_outstanding,0) AS \"DIO\", CASE WHEN zero_sales_flag THEN 'Zero-Sales' ELSE 'Slow-Moving' END AS \"Risk\" FROM dw.ml_inventory_anomaly WHERE zero_sales_flag OR days_inventory_outstanding>=180 ORDER BY days_inventory_outstanding DESC, inventory_value DESC LIMIT 50",
        "table", viz={}, token=token))

    # C6: Risk Count by Category
    ids.append(card("C6 · Inventory Risk Count by Category",
        "SELECT category AS \"Category\", COUNT(*) FILTER (WHERE zero_sales_flag) AS \"Zero-Sales\", ROUND(AVG(days_inventory_outstanding),1) AS \"Avg DIO\" FROM dw.ml_inventory_anomaly GROUP BY category ORDER BY \"Zero-Sales\" DESC",
        "bar", viz={"graph.colors": ["#F59E0B", "#DC2626"]}, token=token))

    # C7: Inventory Value by Category (horizontal bar)
    ids.append(card("C7 · Inventory Value by Category",
        "SELECT category AS \"Category\", ROUND(SUM(inventory_value),0) AS \"Inv Value\" FROM dw.ml_inventory_anomaly GROUP BY category ORDER BY \"Inv Value\" DESC",
        "row", viz={"graph.colors": {"Bikes": "#2563EB", "Components": "#7C3AED", "Clothing": "#EC4899", "Accessories": "#14B8A6", "Unknown": "#94A3B8"}}, token=token))

    # C8: DIO vs Value — Bubble Chart
    ids.append(card("C8 · DIO vs Inventory Value — Risk Map",
        "SELECT product_name AS \"Product\", category AS \"Category\", inventory_value AS \"Inv Value\", days_inventory_outstanding AS \"DIO\", avg_quantity AS \"Avg Qty\", CASE WHEN zero_sales_flag THEN 'Zero-Sales' ELSE 'Has-Sales' END AS \"Status\" FROM dw.ml_inventory_anomaly WHERE inventory_value>0 ORDER BY inventory_value DESC",
        "scatter", viz={"graph.dimensions": ["Inv Value"], "graph.metrics": ["DIO"], "scatter.bubble": "Avg Qty"}, token=token))

    # C9: Inventory Snapshot Summary
    ids.append(card("C9 · Top 20 by Inventory Value",
        "SELECT product_name AS \"Product\", category AS \"Category\", ROUND(avg_quantity,0) AS \"Avg Qty\", ROUND(inventory_value,0) AS \"Inv Value\", ROUND(days_inventory_outstanding,0) AS \"DIO\" FROM dw.ml_inventory_anomaly ORDER BY inventory_value DESC LIMIT 20",
        "table", token=token))

    # C10: Actions by Priority
    ids.append(card("C10 · Decision Support Actions by Priority",
        "SELECT priority AS \"Priority\", COUNT(*) AS \"Actions\" FROM dw.decision_support GROUP BY priority ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END",
        "bar", viz={"graph.colors": {"HIGH": "#DC2626", "MEDIUM": "#F59E0B", "LOW": "#94A3B8"}}, token=token))

    # C11: High-Priority Actions
    ids.append(card("C11 · High-Priority Actions",
        "SELECT entity_type AS \"Entity\", signal_type AS \"Signal\", recommended_action AS \"Action\" FROM dw.decision_support WHERE priority='HIGH' ORDER BY entity_type LIMIT 30",
        "table", token=token))

    # C12: Operational Decision Support
    ids.append(card("C12 · Operational Decision Support (Inventory/Product)",
        "SELECT signal_type AS \"Signal\", priority AS \"Priority\", recommended_action AS \"Action\" FROM dw.decision_support WHERE entity_type IN ('product','inventory','operations') ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END LIMIT 30",
        "table", token=token))

    d3 = dashboard("Inventory & Operational Decision Support",
        "Inventory risk, zero-sales warning, decision support. Source: dw.ml_inventory_anomaly, dw.decision_support.", token)
    if d3:
        add_cards(d3, [
            {"card_id": ids[0], "row": 0, "col": 0, "size_x": 24, "size_y": 2},
            {"card_id": ids[1], "row": 2, "col": 0, "size_x": 6, "size_y": 3},
            {"card_id": ids[2], "row": 2, "col": 6, "size_x": 6, "size_y": 3},
            {"card_id": ids[3], "row": 2, "col": 12, "size_x": 6, "size_y": 3},
            {"card_id": ids[4], "row": 2, "col": 18, "size_x": 6, "size_y": 3},
            {"card_id": ids[5], "row": 5, "col": 0, "size_x": 24, "size_y": 6},
            {"card_id": ids[6], "row": 11, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": ids[7], "row": 11, "col": 12, "size_x": 12, "size_y": 6},
            {"card_id": ids[8], "row": 17, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": ids[9], "row": 17, "col": 12, "size_x": 12, "size_y": 6},
            {"card_id": ids[10], "row": 23, "col": 0, "size_x": 8, "size_y": 6},
            {"card_id": ids[11], "row": 23, "col": 8, "size_x": 8, "size_y": 6},
            {"card_id": ids[12], "row": 23, "col": 16, "size_x": 8, "size_y": 6},
        ], token)
        log(f"Dashboard 3 created: id={d3}")
    return d3, ids

# ══════════════════════════════════════════════════════════════════════
def main():
    log("=== Metabase Rebuild (spec-compliant) ===")
    token = login()
    cleanup(token)

    d1, d1_ids = build_d1(token)
    d2, d2_ids = build_d2(token)
    d3, d3_ids = build_d3(token)

    total = len(d1_ids) + len(d2_ids) + len(d3_ids)
    log(f"\n=== Complete ===")
    log(f"D1 (Business Performance): id={d1}, {len(d1_ids)} cards")
    log(f"D2 (Product & Customer Analytics): id={d2}, {len(d2_ids)} cards")
    log(f"D3 (Inventory & Operational): id={d3}, {len(d3_ids)} cards")
    log(f"Total: {total} cards")
    log(f"Visit http://localhost:3000")

if __name__ == "__main__":
    main()
