import logging
from datetime import datetime

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from src.config import load_postgres_settings

load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Ngưỡng contamination mặc định dựa trên domain knowledge:
# Với inventory, ~5-8% sản phẩm có thể có bất thường thực sự (hết hạn, hỏng, mất cắp)
DEFAULT_CONTAMINATION = 0.06

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

    logger.info("Reading inventory data from DWH...")
    df = pd.read_sql(text(INVENTORY_QUERY), engine)

    if df.empty:
        raise RuntimeError("No inventory data found. Run ETL full load first.")

    numeric_cols = [
        "avg_quantity",
        "std_quantity",
        "max_quantity",
        "total_quantity",
        "inventory_value",
        "total_cogs",
        "units_sold",
        "active_sales_days",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # DIO = (inventory_value * active_sales_days) / total_cogs
    mask_sold = (df["total_cogs"] > 0) & (df["active_sales_days"] > 0)
    df["days_inventory_outstanding"] = np.where(
        mask_sold,
        (df["inventory_value"] * df["active_sales_days"]) / df["total_cogs"],
        999.0,
    ).clip(0, 999)

    # Phân tách: sản phẩm có bán và không bán
    df_sold = df[mask_sold].copy()
    df_unsold = df[~mask_sold].copy()

    df["anomaly_flag"] = False
    df["anomaly_score"] = 0.0
    df["zero_sales_flag"] = False

    if len(df_sold) >= 10:
        features_sold = df_sold[
            ["avg_quantity", "std_quantity", "max_quantity",
             "inventory_value", "units_sold", "days_inventory_outstanding"]
        ].copy()

        scaler = RobustScaler()
        x = scaler.fit_transform(features_sold)

        contamination = DEFAULT_CONTAMINATION
        logger.info(f"Contamination={contamination:.3f} (domain-driven default)")

        model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100,
            max_features=0.7,
        )

        preds = model.fit_predict(x)
        scores = model.decision_function(x)

        # Normalize score to 0-100 severity index
        # Isolation Forest decision_function: negative = anomaly, positive = inlier
        # Map: min score → 100 (most anomalous), max score → 0 (normal)
        score_min, score_max = scores.min(), scores.max()
        if score_max > score_min:
            severity = (1 - (scores - score_min) / (score_max - score_min)) * 100
        else:
            severity = np.full_like(scores, 50)

        df_sold["anomaly_flag"] = preds == -1
        df_sold["anomaly_score"] = severity.round(1)

        df.update(df_sold[["anomaly_flag", "anomaly_score"]])
        logger.info(f"Anomaly model fitted on {len(df_sold)} sold products (max_features=0.7, robust scaler, severity index)")

    # Sản phẩm không bán được: gắn zero_sales_flag, KHÔNG gộp vào anomaly
    # (zero sales là business reality, không phải statistical anomaly)
    if len(df_unsold) > 0:
        df_unsold["anomaly_flag"] = False
        df_unsold["anomaly_score"] = 0.0
        df_unsold["zero_sales_flag"] = True
        df.update(df_unsold[["anomaly_flag", "anomaly_score", "zero_sales_flag"]])
        logger.info(f"Zero-sales products flagged: {len(df_unsold)} (warning only, not anomaly)")
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
            "zero_sales_flag",
            "_load_timestamp",
        ]
    ].copy()

    logger.info("Writing dw.ml_inventory_anomaly...")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE dw.ml_inventory_anomaly"))

    output.to_sql(
        "ml_inventory_anomaly",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )

    logger.info("Done. Wrote %s inventory anomaly rows.", f"{len(output):,}")
    logger.info("Anomalies detected: %s", int(output["anomaly_flag"].sum()))
    logger.info("Zero-sales warnings: %s", int(output["zero_sales_flag"].sum()))


if __name__ == "__main__":
    run_inventory_anomaly_detection()
