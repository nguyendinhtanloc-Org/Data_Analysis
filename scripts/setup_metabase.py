"""Rebuild 3 Metabase dashboards from scratch with all cards, layout, and colors."""
import json, sys, os, time
import requests

MB_URL = os.getenv("MB_URL", "http://localhost:3000/api")
MB_EMAIL = os.getenv("MB_EMAIL", "admin@example.com")
MB_PASS = os.getenv("MB_PASS", "KW9!xPzLmQvR7")
COLLECTION_ID = None

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
    if not props:
        raise RuntimeError("Cannot reach Metabase")
    setup_token = props.get("setup-token")
    if not props.get("has-user-setup") and setup_token:
        log("First-time setup...")
        r = api("POST", "/setup", {
            "token": setup_token,
            "user": {"first_name": "Admin", "last_name": "User",
                     "email": MB_EMAIL, "password": MB_PASS},
            "prefs": {"site_name": "AdventureWorks BI", "site_locale": "en", "allow_tracking": False},
        })
        if r and r.get("id"):
            return r["id"]
    r = api("POST", "/session", {"username": MB_EMAIL, "password": MB_PASS})
    if r and r.get("id"):
        return r["id"]
    raise RuntimeError(f"Login failed: {r}")

def get_db_id(token):
    dbs = api("GET", "/database", token=token)
    if dbs and dbs.get("data"):
        for db in dbs["data"]:
            if db.get("name") == "AdventureWorks DW":
                return db["id"]
    log("Adding database...")
    r = api("POST", "/database", {
        "name": "AdventureWorks DW", "engine": "postgres",
        "details": {"host": "postgres", "port": 5432, "dbname": "adventureworks_dw",
                    "user": "admin", "password": "admin123",
                    "schema-filters-type": "inclusion", "schemas": "public,dw,mart"},
        "is_full_sync": True,
    }, token=token)
    if r and r.get("id"):
        time.sleep(5)
        return r["id"]
    raise RuntimeError(f"Cannot add database: {r}")

def make_card(name, sql, db_id, display="table", desc="", viz=None, token=None):
    data = {
        "name": name, "description": desc, "display": display,
        "dataset_query": {"database": db_id, "type": "native",
                          "native": {"query": sql, "template-tags": {}}},
        "visualization_settings": viz or {},
        "collection_id": COLLECTION_ID,
    }
    r = api("POST", "/card", data, token=token)
    return r.get("id") if r else None

def make_dashboard(name, desc="", token=None):
    r = api("POST", "/dashboard", {"name": name, "description": desc, "collection_id": COLLECTION_ID}, token=token)
    return r.get("id") if r else None

def add_cards(dash_id, cards, token=None):
    dashcards = []
    for i, c in enumerate(cards):
        dashcards.append({
            "id": -(i + 1), "card_id": c["card_id"],
            "row": c["row"], "col": c["col"],
            "size_x": c["size_x"], "size_y": c["size_y"],
            "parameter_mappings": [], "visualization_settings": {},
            "dashboard_tab_id": None,
        })
    r = api("PUT", f"/dashboard/{dash_id}", {"dashcards": dashcards}, token=token)
    log(f"  {len(dashcards)} cards → dashboard {dash_id}")
    return r

def delete_old_dashboards(token):
    """Remove old dashboards but keep cards (which will be archived separately)."""
    dbs = api("GET", "/dashboard", token=token)
    if dbs:
        for d in dbs:
            # Keep only the ones we're about to create
            log(f"Will delete old dashboard id={d['id']} '{d['name']}'")
            api("DELETE", f"/dashboard/{d['id']}", token=token)

def archive_old_cards(token):
    """Archive old cards to avoid clutter."""
    cards = api("GET", "/card", token=token)
    if cards:
        for c in cards:
            if c.get("archived"):
                continue
            log(f"Archiving old card id={c['id']} '{c['name']}'")
            api("PUT", f"/card/{c['id']}", {"archived": True}, token=token)

# ══════════════════════════════════════════════════════════════════════
def build_all():
    log("=== Login & setup ===")
    token = login()
    db_id = get_db_id(token)

    # Clean slate
    log("\n=== Cleaning old dashboards & cards ===")
    archive_old_cards(token)
    delete_old_dashboards(token)

    # ────────── DASHBOARD 1: Business Performance Overview ──────────
    log("\n=== Dashboard 1: Business Performance Overview ===")

    d1_cards_def = []

    # C1: Revenue 2014Q2
    d1_cards_def.append(make_card(
        "D1-C1 Revenue (2014Q2)",
        "SELECT ROUND(value / 1000000.0, 2) AS \"Revenue ($M)\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE kpi_name = 'revenue' AND dimension = 'overall' AND period_key = '2014Q2';",
        db_id, "scalar", "Revenue in millions",
        {"scalar.field": "Revenue ($M)"}, token))

    # C2: Gross Profit 2014Q2
    d1_cards_def.append(make_card(
        "D1-C2 Gross Profit (2014Q2)",
        "SELECT ROUND(value / 1000000.0, 2) AS \"Gross Profit ($M)\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE kpi_name = 'gross_profit' AND dimension = 'overall' AND period_key = '2014Q2';",
        db_id, "scalar", "Gross Profit in millions",
        {"scalar.field": "Gross Profit ($M)"}, token))

    # C3: Gross Margin % 2014Q2
    d1_cards_def.append(make_card(
        "D1-C3 Gross Margin % (2014Q2)",
        "SELECT ROUND(value, 2) AS \"Gross Margin (%)\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE kpi_name = 'gross_margin_pct' AND dimension = 'overall' AND period_key = '2014Q2';",
        db_id, "scalar", "Gross Margin percentage",
        {"scalar.field": "Gross Margin (%)"}, token))

    # C4: Order Count 2014Q2
    d1_cards_def.append(make_card(
        "D1-C4 Order Count (2014Q2)",
        "SELECT ROUND(value, 0) AS \"Order Count\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE kpi_name = 'order_count' AND dimension = 'overall' AND period_key = '2014Q2';",
        db_id, "scalar", "Total orders",
        {"scalar.field": "Order Count"}, token))

    # C5: Revenue & Gross Profit Trend
    d1_cards_def.append(make_card(
        "D1-C5 Revenue & Gross Profit Trend",
        "SELECT\n"
        "    period_key AS \"Period\",\n"
        "    ROUND(MAX(CASE WHEN kpi_name = 'revenue' THEN value END) / 1000000.0, 2) AS \"Revenue ($M)\",\n"
        "    ROUND(MAX(CASE WHEN kpi_name = 'gross_profit' THEN value END) / 1000000.0, 2) AS \"Gross Profit ($M)\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE kpi_name IN ('revenue', 'gross_profit')\n"
        "  AND dimension = 'overall'\n"
        "  AND period_key BETWEEN '2011Q2' AND '2014Q2'\n"
        "GROUP BY period_key\n"
        "ORDER BY period_key;",
        db_id, "line", "Revenue and gross profit over quarters",
        {"graph.colors": ["#2563EB", "#16A34A"]}, token))

    # C6: Gross Margin % Trend
    d1_cards_def.append(make_card(
        "D1-C6 Gross Margin % Trend",
        "SELECT period_key AS \"Period\", ROUND(value, 2) AS \"Gross Margin (%)\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE kpi_name = 'gross_margin_pct'\n"
        "  AND dimension = 'overall'\n"
        "  AND period_key BETWEEN '2011Q2' AND '2014Q2'\n"
        "ORDER BY period_key;",
        db_id, "line", "Gross margin trend",
        {"graph.colors": ["#F59E0B"]}, token))

    # C7: Revenue by Product Category 2014Q2
    d1_cards_def.append(make_card(
        "D1-C7 Revenue by Product Category (2014Q2)",
        "SELECT dimension_value AS \"Category\", ROUND(value / 1000000.0, 2) AS \"Revenue ($M)\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE kpi_name = 'revenue_by_category'\n"
        "  AND period_key = '2014Q2'\n"
        "ORDER BY value DESC;",
        db_id, "bar", "Revenue by category in Q2 2014",
        {"graph.colors": ["#2563EB"]}, token))

    # C8: Contribution by Category
    d1_cards_def.append(make_card(
        "D1-C8 Contribution by Category (2014Q2 vs 2014Q1)",
        "SELECT\n"
        "    dimension_value AS \"Category\",\n"
        "    ROUND(contribution_pct, 2) AS \"Contribution (%)\",\n"
        "    ROUND(pct_change, 2) AS \"Change (%)\"\n"
        "FROM mart.period_comparison\n"
        "WHERE kpi_name = 'revenue'\n"
        "  AND dimension = 'category'\n"
        "  AND curr_period_key = '2014Q2'\n"
        "ORDER BY ABS(contribution_pct) DESC;",
        db_id, "bar", "Category contribution to revenue change",
        {"graph.colors": ["#2563EB", "#DC2626"]}, token))

    # C9: Contribution by Territory
    d1_cards_def.append(make_card(
        "D1-C9 Contribution by Territory (2014Q2 vs 2014Q1)",
        "SELECT\n"
        "    dimension_value AS \"Territory\",\n"
        "    ROUND(contribution_pct, 2) AS \"Contribution (%)\",\n"
        "    ROUND(pct_change, 2) AS \"Change (%)\"\n"
        "FROM mart.period_comparison\n"
        "WHERE kpi_name = 'revenue'\n"
        "  AND dimension = 'territory'\n"
        "  AND curr_period_key = '2014Q2'\n"
        "ORDER BY ABS(contribution_pct) DESC\n"
        "LIMIT 10;",
        db_id, "bar", "Territory contribution to revenue change",
        {"graph.colors": ["#2563EB", "#DC2626"]}, token))

    # C10: KPI Comparison Table
    d1_cards_def.append(make_card(
        "D1-C10 KPI Comparison Table (2014Q2 vs 2014Q1)",
        "SELECT\n"
        "    kpi_name AS \"KPI\",\n"
        "    ROUND(MAX(CASE WHEN period_key = '2014Q2' THEN value END), 2) AS \"2014Q2\",\n"
        "    ROUND(MAX(CASE WHEN period_key = '2014Q1' THEN value END), 2) AS \"2014Q1\",\n"
        "    ROUND(MAX(CASE WHEN period_key = '2014Q2' THEN value END) - MAX(CASE WHEN period_key = '2014Q1' THEN value END), 2) AS \"Abs Change\",\n"
        "    ROUND(\n"
        "        CASE\n"
        "            WHEN MAX(CASE WHEN period_key = '2014Q1' THEN value END) <> 0\n"
        "            THEN (\n"
        "                MAX(CASE WHEN period_key = '2014Q2' THEN value END)\n"
        "                - MAX(CASE WHEN period_key = '2014Q1' THEN value END)\n"
        "            ) * 100.0 / MAX(CASE WHEN period_key = '2014Q1' THEN value END)\n"
        "            ELSE NULL\n"
        "        END,\n"
        "        2\n"
        "    ) AS \"Change (%)\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE period_key IN ('2014Q1', '2014Q2')\n"
        "  AND dimension = 'overall'\n"
        "  AND kpi_name IN ('revenue','gross_profit','gross_margin_pct','order_count',\n"
        "                   'total_customers','avg_order_value','revenue_per_customer')\n"
        "GROUP BY kpi_name\n"
        "ORDER BY kpi_name;",
        db_id, "table", "KPI comparison", {}, token))

    # Build Dashboard 1
    d1 = make_dashboard("Business Performance Overview",
        "Period-based KPI snapshot, trend by quarter, comparison 2014Q2 vs 2014Q1, contribution/root-cause analysis. "
        "Data source: mart.kpi_snapshot, mart.period_comparison.", token)
    if d1:
        add_cards(d1, [
            {"card_id": d1_cards_def[0], "row": 0, "col": 0, "size_x": 3, "size_y": 2},
            {"card_id": d1_cards_def[1], "row": 0, "col": 3, "size_x": 3, "size_y": 2},
            {"card_id": d1_cards_def[2], "row": 0, "col": 6, "size_x": 3, "size_y": 2},
            {"card_id": d1_cards_def[3], "row": 0, "col": 9, "size_x": 3, "size_y": 2},
            {"card_id": d1_cards_def[4], "row": 2, "col": 0, "size_x": 12, "size_y": 5},
            {"card_id": d1_cards_def[5], "row": 7, "col": 0, "size_x": 6, "size_y": 4},
            {"card_id": d1_cards_def[6], "row": 7, "col": 6, "size_x": 6, "size_y": 4},
            {"card_id": d1_cards_def[7], "row": 11, "col": 0, "size_x": 6, "size_y": 4},
            {"card_id": d1_cards_def[8], "row": 11, "col": 6, "size_x": 6, "size_y": 4},
            {"card_id": d1_cards_def[9], "row": 15, "col": 0, "size_x": 12, "size_y": 4},
        ], token)
        log(f"Dashboard 1 created: id={d1}")

    # ────────── DASHBOARD 2: Product & Customer Analytics ──────────
    log("\n=== Dashboard 2: Product & Customer Analytics ===")

    d2_cards_def = []

    # C1: Active Customers
    d2_cards_def.append(make_card(
        "D2-C1 Active Customers (2014Q2)",
        "SELECT COUNT(DISTINCT f.customer_key) AS \"Active Customers\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30';",
        db_id, "scalar", "Active customers in Q2 2014", {}, token))

    # C2: Active Products
    d2_cards_def.append(make_card(
        "D2-C2 Active Products (2014Q2)",
        "SELECT COUNT(DISTINCT f.product_key) AS \"Active Products\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30';",
        db_id, "scalar", "Active products in Q2 2014", {}, token))

    # C3: Units Sold
    d2_cards_def.append(make_card(
        "D2-C3 Units Sold (2014Q2)",
        "SELECT SUM(f.order_qty) AS \"Units Sold\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30';",
        db_id, "scalar", "Total units sold", {}, token))

    # C4: Avg Revenue per Customer
    d2_cards_def.append(make_card(
        "D2-C4 Avg Revenue per Customer (2014Q2)",
        "SELECT ROUND(SUM(f.line_total) / NULLIF(COUNT(DISTINCT f.customer_key), 0), 2) AS \"Avg Revenue per Customer\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30';",
        db_id, "scalar", "Average revenue per customer", {}, token))

    # C5: Customer Segments — RFM K-Means (K=3)
    d2_cards_def.append(make_card(
        "D2-C5 Customer Segments — RFM K-Means",
        "SELECT\n"
        "    cluster_label AS \"Customer Segment\",\n"
        "    COUNT(*) AS \"Customer Count\",\n"
        "    ROUND(AVG(monetary), 2) AS \"Avg Monetary\",\n"
        "    ROUND(AVG(recency_days), 2) AS \"Avg Recency\",\n"
        "    ROUND(AVG(frequency), 2) AS \"Avg Frequency\"\n"
        "FROM dw.ml_customer_segments\n"
        "GROUP BY cluster_label\n"
        "ORDER BY \"Customer Count\" DESC;",
        db_id, "bar", "RFM customer segments from K-Means (K=3)",
        {"graph.colors": ["#7C3AED"]}, token))

    # C6: RFM Segment Details
    d2_cards_def.append(make_card(
        "D2-C6 RFM Segment Details",
        "SELECT\n"
        "    cluster_label AS \"Customer Segment\",\n"
        "    COUNT(*) AS \"Customers\",\n"
        "    ROUND(AVG(recency_days), 0) AS \"Avg Recency Days\",\n"
        "    ROUND(AVG(frequency), 0) AS \"Avg Frequency\",\n"
        "    ROUND(AVG(monetary), 2) AS \"Avg Monetary\",\n"
        "    ROUND(SUM(monetary), 2) AS \"Total Monetary\",\n"
        "    ROUND(MAX(silhouette_score), 4) AS \"Silhouette Score\"\n"
        "FROM dw.ml_customer_segments\n"
        "GROUP BY cluster_label\n"
        "ORDER BY \"Total Monetary\" DESC;",
        db_id, "table", "Detailed RFM metrics per segment", {}, token))

    # C7: ABC Product Class
    d2_cards_def.append(make_card(
        "D2-C7 Revenue Share by ABC Product Class (2014Q2)",
        "WITH product_revenue AS (\n"
        "    SELECT p.product_key, p.name AS product_name, SUM(f.line_total) AS revenue\n"
        "    FROM dw.fact_sales f\n"
        "    JOIN dw.dim_product p ON f.product_key = p.product_key\n"
        "    JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "    WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'\n"
        "    GROUP BY p.product_key, p.name\n"
        "),\n"
        "ranked AS (\n"
        "    SELECT *,\n"
        "        SUM(revenue) OVER () AS total_revenue,\n"
        "        SUM(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING)\n"
        "            / NULLIF(SUM(revenue) OVER (), 0) AS cumulative_share\n"
        "    FROM product_revenue\n"
        "),\n"
        "classified AS (\n"
        "    SELECT\n"
        "        CASE\n"
        "            WHEN cumulative_share <= 0.80 THEN 'A - Core Products'\n"
        "            WHEN cumulative_share <= 0.95 THEN 'B - Support Products'\n"
        "            ELSE 'C - Long Tail'\n"
        "        END AS abc_class,\n"
        "        revenue\n"
        "    FROM ranked\n"
        ")\n"
        "SELECT abc_class AS \"ABC Class\", ROUND(SUM(revenue) / 1000000.0, 2) AS \"Revenue ($M)\"\n"
        "FROM classified\n"
        "GROUP BY abc_class\n"
        "ORDER BY \"Revenue ($M)\" DESC;",
        db_id, "bar", "ABC product classification by revenue share",
        {"graph.colors": ["#2563EB", "#F59E0B", "#64748B"]}, token))

    # C8: Top 10 Products by Revenue
    d2_cards_def.append(make_card(
        "D2-C8 Top 10 Products by Revenue (2014Q2)",
        "SELECT p.name AS \"Product\", ROUND(SUM(f.line_total) / 1000000.0, 2) AS \"Revenue ($M)\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_product p ON f.product_key = p.product_key\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'\n"
        "GROUP BY p.name\n"
        "ORDER BY \"Revenue ($M)\" DESC\n"
        "LIMIT 10;",
        db_id, "bar", "Top 10 products by revenue",
        {"graph.colors": ["#2563EB"]}, token))

    # C9: Top 10 Customers by Revenue
    d2_cards_def.append(make_card(
        "D2-C9 Top 10 Customers by Revenue (2014Q2)",
        "SELECT\n"
        "    c.full_name AS \"Customer\",\n"
        "    c.customer_type AS \"Customer Type\",\n"
        "    c.country AS \"Country\",\n"
        "    ROUND(SUM(f.line_total) / 1000000.0, 2) AS \"Revenue ($M)\",\n"
        "    COUNT(DISTINCT f.sales_order_id) AS \"Order Count\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_customer c ON f.customer_key = c.customer_key\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'\n"
        "GROUP BY c.full_name, c.customer_type, c.country\n"
        "ORDER BY \"Revenue ($M)\" DESC\n"
        "LIMIT 10;",
        db_id, "table", "Top 10 customers by revenue", {}, token))

    # C10: Customer Segment Share by Quarter
    d2_cards_def.append(make_card(
        "D2-C10 Customer Segment Share by Quarter",
        "SELECT\n"
        "    period_key AS \"Period\",\n"
        "    cluster_label AS \"Customer Segment\",\n"
        "    ROUND(pct_of_total, 2) AS \"Share (%)\"\n"
        "FROM mart.rfm_snapshot\n"
        "WHERE period_key BETWEEN '2013Q1' AND '2014Q2'\n"
        "ORDER BY period_key, cluster_label;",
        db_id, "line", "RFM segment share over time",
        {"graph.colors": ["#7C3AED", "#2563EB", "#16A34A"]}, token))

    # C11: Revenue by Customer Type
    d2_cards_def.append(make_card(
        "D2-C11 Revenue by Customer Type (2014Q2)",
        "SELECT c.customer_type AS \"Customer Type\", ROUND(SUM(f.line_total) / 1000000.0, 2) AS \"Revenue ($M)\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_customer c ON f.customer_key = c.customer_key\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'\n"
        "GROUP BY c.customer_type\n"
        "ORDER BY \"Revenue ($M)\" DESC;",
        db_id, "pie", "Revenue distribution by customer type",
        {"pie.colors": {"Individual": "#2563EB", "Store": "#16A34A"}}, token))

    # C12: Gross Margin % by Product Category
    d2_cards_def.append(make_card(
        "D2-C12 Gross Margin % by Product Category (2014Q2)",
        "SELECT\n"
        "    p.category AS \"Category\",\n"
        "    ROUND(SUM(f.gross_profit)::numeric / NULLIF(SUM(f.line_total), 0) * 100, 2) AS \"Gross Margin (%)\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_product p ON f.product_key = p.product_key\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'\n"
        "GROUP BY p.category\n"
        "ORDER BY \"Gross Margin (%)\" DESC;",
        db_id, "bar", "Gross margin by category",
        {"graph.colors": ["#16A34A"]}, token))

    # C13: Average Cost vs Selling Price
    d2_cards_def.append(make_card(
        "D2-C13 Average Cost vs Selling Price by Product",
        "SELECT\n"
        "    p.name AS \"Product\",\n"
        "    p.category AS \"Category\",\n"
        "    ROUND(AVG(f.standard_cost), 2) AS \"Standard Cost\",\n"
        "    ROUND(AVG(f.unit_price), 2) AS \"Average Selling Price\",\n"
        "    ROUND(SUM(f.line_total) / 1000000.0, 2) AS \"Revenue ($M)\"\n"
        "FROM dw.fact_sales f\n"
        "JOIN dw.dim_product p ON f.product_key = p.product_key\n"
        "JOIN dw.dim_date d ON f.date_key = d.date_key\n"
        "WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'\n"
        "GROUP BY p.name, p.category\n"
        "HAVING SUM(f.line_total) > 0\n"
        "ORDER BY \"Revenue ($M)\" DESC\n"
        "LIMIT 100;",
        db_id, "scatter", "Cost vs selling price scatter", {}, token))

    d2 = make_dashboard("Product & Customer Analytics",
        "Product performance, ABC analysis, customer segmentation ML. "
        "Data source: dw.fact_sales, dw.ml_customer_segments, mart.rfm_snapshot.", token)
    if d2:
        add_cards(d2, [
            {"card_id": d2_cards_def[0], "row": 0, "col": 0, "size_x": 3, "size_y": 2},
            {"card_id": d2_cards_def[1], "row": 0, "col": 3, "size_x": 3, "size_y": 2},
            {"card_id": d2_cards_def[2], "row": 0, "col": 6, "size_x": 3, "size_y": 2},
            {"card_id": d2_cards_def[3], "row": 0, "col": 9, "size_x": 3, "size_y": 2},
            {"card_id": d2_cards_def[4], "row": 2, "col": 0, "size_x": 6, "size_y": 5},
            {"card_id": d2_cards_def[5], "row": 2, "col": 6, "size_x": 6, "size_y": 5},
            {"card_id": d2_cards_def[6], "row": 7, "col": 0, "size_x": 6, "size_y": 4},
            {"card_id": d2_cards_def[7], "row": 7, "col": 6, "size_x": 6, "size_y": 4},
            {"card_id": d2_cards_def[8], "row": 11, "col": 0, "size_x": 12, "size_y": 5},
            {"card_id": d2_cards_def[9], "row": 16, "col": 0, "size_x": 6, "size_y": 4},
            {"card_id": d2_cards_def[10], "row": 16, "col": 6, "size_x": 6, "size_y": 4},
            {"card_id": d2_cards_def[11], "row": 20, "col": 0, "size_x": 6, "size_y": 4},
            {"card_id": d2_cards_def[12], "row": 20, "col": 6, "size_x": 6, "size_y": 4},
        ], token)
        log(f"Dashboard 2 created: id={d2}")

    # ────────── DASHBOARD 3: Inventory & Operational Decision Support ──────────
    log("\n=== Dashboard 3: Inventory & Operational Decision Support ===")

    d3_cards_def = []

    # C1: Inventory Risk Products
    d3_cards_def.append(make_card(
        "D3-C1 Inventory Risk Products",
        "SELECT COUNT(*) AS \"Inventory Risk Products\"\n"
        "FROM dw.ml_inventory_anomaly\n"
        "WHERE anomaly_flag = true OR zero_sales_flag = true;",
        db_id, "scalar", "Total flagged inventory products", {}, token))

    # C2: Zero-Sales Warnings
    d3_cards_def.append(make_card(
        "D3-C2 Zero-Sales Warnings",
        "SELECT COUNT(*) AS \"Zero-Sales Warnings\"\n"
        "FROM dw.ml_inventory_anomaly\n"
        "WHERE zero_sales_flag = true;",
        db_id, "scalar", "Products with zero sales", {}, token))

    # C3: High Priority Actions
    d3_cards_def.append(make_card(
        "D3-C3 High Priority Actions",
        "SELECT COUNT(*) AS \"High Priority Actions\"\n"
        "FROM dw.decision_support\n"
        "WHERE priority = 'HIGH';",
        db_id, "scalar", "HIGH priority decision support actions", {}, token))

    # C4: Inventory Value
    d3_cards_def.append(make_card(
        "D3-C4 Inventory Value",
        "SELECT ROUND(SUM(i.quantity * p.standard_cost) / 1000000.0, 2) AS \"Inventory Value ($M)\"\n"
        "FROM dw.fact_inventory i\n"
        "JOIN dw.dim_product p ON i.product_key = p.product_key;",
        db_id, "scalar", "Total inventory value", {}, token))

    # C5: Inventory Risk Flags Table
    d3_cards_def.append(make_card(
        "D3-C5 Inventory Risk Flags — Zero-Sales & Slow-Moving Products",
        "SELECT\n"
        "    product_name AS \"Product\",\n"
        "    category AS \"Category\",\n"
        "    subcategory AS \"Subcategory\",\n"
        "    ROUND(days_inventory_outstanding, 1) AS \"DIO Days\",\n"
        "    ROUND(inventory_value / 1000000.0, 2) AS \"Inventory Value ($M)\",\n"
        "    ROUND(anomaly_score, 4) AS \"Risk Score\",\n"
        "    CASE\n"
        "        WHEN anomaly_flag = true THEN 'Anomaly'\n"
        "        WHEN zero_sales_flag = true THEN 'Zero-Sales Warning'\n"
        "        ELSE 'Slow-Moving Warning'\n"
        "    END AS \"Risk Type\"\n"
        "FROM dw.ml_inventory_anomaly\n"
        "WHERE anomaly_flag = true\n"
        "   OR zero_sales_flag = true\n"
        "   OR days_inventory_outstanding >= 180\n"
        "ORDER BY\n"
        "    CASE\n"
        "        WHEN anomaly_flag = true THEN 1\n"
        "        WHEN zero_sales_flag = true THEN 2\n"
        "        ELSE 3\n"
        "    END,\n"
        "    days_inventory_outstanding DESC,\n"
        "    inventory_value DESC\n"
        "LIMIT 30;",
        db_id, "table", "Inventory risk flagged products", {}, token))

    # C6: Inventory Risk Count by Category
    d3_cards_def.append(make_card(
        "D3-C6 Inventory Risk Count by Category",
        "SELECT category AS \"Category\", COUNT(*) AS \"Risk Products\"\n"
        "FROM dw.ml_inventory_anomaly\n"
        "WHERE anomaly_flag = true OR zero_sales_flag = true OR days_inventory_outstanding >= 180\n"
        "GROUP BY category\n"
        "ORDER BY \"Risk Products\" DESC;",
        db_id, "bar", "Risk count by category",
        {"graph.colors": ["#DC2626"]}, token))

    # C7: Inventory Value by Category
    d3_cards_def.append(make_card(
        "D3-C7 Inventory Value by Category",
        "SELECT\n"
        "    p.category AS \"Category\",\n"
        "    ROUND(SUM(i.quantity * p.standard_cost) / 1000000.0, 2) AS \"Inventory Value ($M)\",\n"
        "    SUM(i.quantity) AS \"Inventory Units\"\n"
        "FROM dw.fact_inventory i\n"
        "JOIN dw.dim_product p ON i.product_key = p.product_key\n"
        "GROUP BY p.category\n"
        "ORDER BY \"Inventory Value ($M)\" DESC;",
        db_id, "bar", "Inventory value by category",
        {"graph.colors": ["#2563EB"]}, token))

    # C8: DIO vs Inventory Value Scatter
    d3_cards_def.append(make_card(
        "D3-C8 DIO vs Inventory Value — Risk Map",
        "SELECT\n"
        "    product_name AS \"Product\",\n"
        "    category AS \"Category\",\n"
        "    ROUND(days_inventory_outstanding, 1) AS \"DIO Days\",\n"
        "    ROUND(inventory_value / 1000000.0, 2) AS \"Inventory Value ($M)\",\n"
        "    CASE\n"
        "        WHEN anomaly_flag = true THEN 'Anomaly'\n"
        "        WHEN zero_sales_flag = true THEN 'Zero-Sales Warning'\n"
        "        ELSE 'Normal / Low Risk'\n"
        "    END AS \"Risk Type\"\n"
        "FROM dw.ml_inventory_anomaly\n"
        "WHERE inventory_value > 0\n"
        "ORDER BY inventory_value DESC;",
        db_id, "scatter", "DIO vs inventory value risk scatter", {}, token))

    # C9: Inventory Turnover Trend
    d3_cards_def.append(make_card(
        "D3-C9 Inventory Turnover Trend",
        "SELECT period_key AS \"Period\", ROUND(value, 4) AS \"Inventory Turnover\"\n"
        "FROM mart.kpi_snapshot\n"
        "WHERE kpi_name = 'inventory_turnover'\n"
        "  AND dimension = 'overall'\n"
        "  AND period_key BETWEEN '2011Q2' AND '2014Q2'\n"
        "ORDER BY period_key;",
        db_id, "line", "Inventory turnover over quarters",
        {"graph.colors": ["#F59E0B"]}, token))

    # C10: Decision Support Actions by Priority
    d3_cards_def.append(make_card(
        "D3-C10 Decision Support Actions by Priority",
        "SELECT priority AS \"Priority\", COUNT(*) AS \"Action Count\"\n"
        "FROM dw.decision_support\n"
        "GROUP BY priority\n"
        "ORDER BY\n"
        "    CASE priority\n"
        "        WHEN 'CRITICAL' THEN 1\n"
        "        WHEN 'HIGH' THEN 2\n"
        "        WHEN 'MEDIUM' THEN 3\n"
        "        WHEN 'LOW' THEN 4\n"
        "        ELSE 5\n"
        "    END;",
        db_id, "bar", "Decision support actions by priority",
        {"graph.colors": ["#DC2626", "#F59E0B"]}, token))

    # C11: High Priority Decision Support
    d3_cards_def.append(make_card(
        "D3-C11 High Priority Decision Support Actions",
        "SELECT\n"
        "    entity_type AS \"Entity Type\",\n"
        "    entity_key AS \"Entity Key\",\n"
        "    signal_type AS \"Signal Type\",\n"
        "    priority AS \"Priority\",\n"
        "    recommended_action AS \"Recommended Action\",\n"
        "    reason AS \"Reason\"\n"
        "FROM dw.decision_support\n"
        "WHERE priority = 'HIGH'\n"
        "ORDER BY _load_timestamp DESC\n"
        "LIMIT 30;",
        db_id, "table", "HIGH priority recommendations", {}, token))

    # C12: Operational Decision Support
    d3_cards_def.append(make_card(
        "D3-C12 Operational Decision Support — Inventory/Product",
        "SELECT\n"
        "    entity_type AS \"Entity Type\",\n"
        "    signal_type AS \"Signal Type\",\n"
        "    priority AS \"Priority\",\n"
        "    recommended_action AS \"Recommended Action\",\n"
        "    reason AS \"Reason\"\n"
        "FROM dw.decision_support\n"
        "WHERE entity_type IN ('product', 'inventory', 'operations')\n"
        "ORDER BY\n"
        "    CASE priority\n"
        "        WHEN 'HIGH' THEN 1\n"
        "        WHEN 'MEDIUM' THEN 2\n"
        "        ELSE 3\n"
        "    END,\n"
        "    _load_timestamp DESC\n"
        "LIMIT 20;",
        db_id, "table", "Operational recommendations for inventory/products", {}, token))

    d3 = make_dashboard("Inventory & Operational Decision Support",
        "Inventory risk, zero-sales warning, decision support actions. "
        "Data source: dw.ml_inventory_anomaly, dw.decision_support, mart.kpi_snapshot.", token)
    if d3:
        add_cards(d3, [
            {"card_id": d3_cards_def[0], "row": 0, "col": 0, "size_x": 3, "size_y": 2},
            {"card_id": d3_cards_def[1], "row": 0, "col": 3, "size_x": 3, "size_y": 2},
            {"card_id": d3_cards_def[2], "row": 0, "col": 6, "size_x": 3, "size_y": 2},
            {"card_id": d3_cards_def[3], "row": 0, "col": 9, "size_x": 3, "size_y": 2},
            {"card_id": d3_cards_def[4], "row": 2, "col": 0, "size_x": 12, "size_y": 5},
            {"card_id": d3_cards_def[5], "row": 7, "col": 0, "size_x": 6, "size_y": 4},
            {"card_id": d3_cards_def[6], "row": 7, "col": 6, "size_x": 6, "size_y": 4},
            {"card_id": d3_cards_def[7], "row": 11, "col": 0, "size_x": 6, "size_y": 4},
            {"card_id": d3_cards_def[8], "row": 11, "col": 6, "size_x": 6, "size_y": 4},
            {"card_id": d3_cards_def[9], "row": 15, "col": 0, "size_x": 4, "size_y": 4},
            {"card_id": d3_cards_def[10], "row": 15, "col": 4, "size_x": 4, "size_y": 4},
            {"card_id": d3_cards_def[11], "row": 15, "col": 8, "size_x": 4, "size_y": 4},
        ], token)
        log(f"Dashboard 3 created: id={d3}")

    log(f"\n=== Done ===")
    log(f"D1 (Business Performance): id={d1}")
    log(f"D2 (Product & Customer Analytics): id={d2}")
    log(f"D3 (Inventory & Operational): id={d3}")
    log(f"Visit http://localhost:3000")

if __name__ == "__main__":
    build_all()
