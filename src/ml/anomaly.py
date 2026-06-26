import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.config import load_postgres_settings


INVENTORY_QUERY = """
WITH sales_agg AS (
    SELECT
        product_key,
        SUM(standard_cost * order_qty) AS total_cogs,
        SUM(order_qty) AS units_sold,
        COUNT(DISTINCT date_key) AS active_sales_days
    FROM dw.fact_sales
    GROUP BY product_key
),
inventory_agg AS (
    SELECT
        i.product_key,
        p.name AS product_name,
        p.category,
        p.subcategory,
        AVG(i.quantity) AS avg_quantity,
        COALESCE(STDDEV(i.quantity), 0) AS std_quantity,
        MAX(i.quantity) AS max_quantity,
        SUM(i.quantity) AS total_quantity,
        AVG(COALESCE(i.ordered_qty, 0)) AS avg_ordered_qty,
        AVG(COALESCE(i.scrapped_qty, 0)) AS avg_scrapped_qty,
        AVG(i.quantity * p.standard_cost) AS inventory_value,
        AVG(p.standard_cost) AS standard_cost
    FROM dw.fact_inventory i
    JOIN dw.dim_product p ON i.product_key = p.product_key
    WHERE p.is_current = true
    GROUP BY i.product_key, p.name, p.category, p.subcategory
)
SELECT
    inv.product_key,
    inv.product_name,
    inv.category,
    inv.subcategory,
    inv.avg_quantity,
    inv.std_quantity,
    inv.max_quantity,
    inv.total_quantity,
    inv.avg_ordered_qty,
    inv.avg_scrapped_qty,
    inv.inventory_value,
    COALESCE(sa.total_cogs, 0) AS total_cogs,
    COALESCE(sa.units_sold, 0) AS units_sold,
    COALESCE(sa.active_sales_days, 1) AS active_sales_days
FROM inventory_agg inv
LEFT JOIN sales_agg sa ON inv.product_key = sa.product_key;
"""


def get_engine():
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


def run_inventory_anomaly_detection():
    engine = get_engine()

    print("Reading inventory data from DWH...")
    df = pd.read_sql(text(INVENTORY_QUERY), engine)

    if df.empty:
        raise RuntimeError("No inventory data found. Run ETL full load first.")

    numeric_cols = [
        "avg_quantity",
        "std_quantity",
        "max_quantity",
        "total_quantity",
        "avg_ordered_qty",
        "avg_scrapped_qty",
        "inventory_value",
        "total_cogs",
        "units_sold",
        "active_sales_days",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    daily_cogs = df["total_cogs"] / df["active_sales_days"].replace(0, np.nan)
    df["days_inventory_outstanding"] = df["inventory_value"] / daily_cogs.replace(0, np.nan)
    df["days_inventory_outstanding"] = (
        df["days_inventory_outstanding"]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(999)
        .clip(upper=999)
    )

    features = df[
        [
            "avg_quantity",
            "std_quantity",
            "max_quantity",
            "avg_ordered_qty",
            "avg_scrapped_qty",
            "inventory_value",
            "units_sold",
            "days_inventory_outstanding",
        ]
    ].copy()

    scaler = StandardScaler()
    x = scaler.fit_transform(features)

    model = IsolationForest(
        contamination=0.10,
        random_state=42,
        n_estimators=100,
    )

    predictions = model.fit_predict(x)
    scores = model.decision_function(x)

    df["anomaly_flag"] = predictions == -1
    df["anomaly_score"] = scores
    df["_load_timestamp"] = datetime.now()

    output = df[
        [
            "product_key",
            "product_name",
            "category",
            "subcategory",
            "avg_quantity",
            "std_quantity",
            "max_quantity",
            "inventory_value",
            "units_sold",
            "days_inventory_outstanding",
            "anomaly_flag",
            "anomaly_score",
            "_load_timestamp",
        ]
    ].copy()

    print("Writing dw.ml_inventory_anomaly...")
    output.to_sql(
        "ml_inventory_anomaly",
        engine,
        schema="dw",
        if_exists="replace",
        index=False,
        chunksize=10000,
    )

    print(f"Done. Wrote {len(output):,} inventory anomaly rows.")
    print(f"Anomalies detected: {int(output['anomaly_flag'].sum())}")


if __name__ == "__main__":
    run_inventory_anomaly_detection()