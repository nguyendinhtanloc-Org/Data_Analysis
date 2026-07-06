"""Early Warning System - Hệ thống cảnh báo sớm.

Dùng leading indicators để dự báo nguy cơ trước khi KPI chính bị ảnh hưởng.

Các leading indicators:
  1. Customer: Giảm visit frequency, giảm basket size → dự báo churn
  2. Inventory: Tăng DIO, giảm turnover → dự báo tồn kho chết
  3. Revenue: Giảm avg_order_value, giảm new customer → dự báo doanh thu giảm
"""
import logging
from datetime import datetime, timedelta

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.config import load_postgres_settings

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_engine():
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


def detect_churn_risk(engine, lookback_months: int = 3, min_monetary: float = 500) -> pd.DataFrame:
    """Phát hiện khách hàng có nguy cơ churn dựa trên leading indicators.

    Leading indicators:
      - Frequency giảm >50% so với kỳ trước
      - Monetary giảm >50% so với kỳ trước
      - Recency > 90 ngày

    Returns:
        pd.DataFrame: Danh sách KH có nguy cơ churn.
    """
    query = f"""
        WITH max_data_date AS (
            SELECT MAX(d.date) AS max_d
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
        ),
        current_period AS (
            SELECT
                customer_key,
                COUNT(f.sales_order_detail_id) AS cur_freq,
                SUM(f.line_total) AS cur_monetary,
                MAX(d.date) AS last_purchase
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            CROSS JOIN max_data_date mdd
            WHERE d.date >= mdd.max_d - INTERVAL '{lookback_months} months'
            GROUP BY customer_key
        ),
        prev_period AS (
            SELECT
                customer_key,
                COUNT(f.sales_order_detail_id) AS prev_freq,
                SUM(f.line_total) AS prev_monetary
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            CROSS JOIN max_data_date mdd
            WHERE d.date >= mdd.max_d - INTERVAL '{lookback_months * 2} months'
              AND d.date < mdd.max_d - INTERVAL '{lookback_months} months'
            GROUP BY customer_key
        )
        SELECT
            c.customer_key,
            c.full_name,
            COALESCE(cur.cur_freq, 0) AS cur_frequency,
            COALESCE(prev.prev_freq, 0) AS prev_frequency,
            COALESCE(cur.cur_monetary, 0) AS cur_monetary,
            COALESCE(prev.prev_monetary, 0) AS prev_monetary,
            CASE
                WHEN cur.last_purchase IS NULL THEN 999
                ELSE (mdd.max_d - cur.last_purchase)::int
            END AS recency_days
        FROM dw.dim_customer c
        CROSS JOIN max_data_date mdd
        LEFT JOIN current_period cur ON c.customer_key = cur.customer_key
        LEFT JOIN prev_period prev ON c.customer_key = prev.customer_key
        WHERE COALESCE(prev.prev_monetary, 0) > {min_monetary}
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        return df

    df["freq_decline_pct"] = (
        (df["prev_frequency"] - df["cur_frequency"]) / df["prev_frequency"].replace(0, 1) * 100
    )
    df["monetary_decline_pct"] = (
        (df["prev_monetary"] - df["cur_monetary"]) / df["prev_monetary"].replace(0, 1) * 100
    )

    df["churn_risk_score"] = 0.0
    df.loc[df["recency_days"] > 90, "churn_risk_score"] += 0.3
    df.loc[df["freq_decline_pct"] > 50, "churn_risk_score"] += 0.35
    df.loc[df["monetary_decline_pct"] > 50, "churn_risk_score"] += 0.35

    df["risk_level"] = pd.cut(
        df["churn_risk_score"],
        bins=[0, 0.3, 0.6, 1.0],
        labels=["LOW", "MEDIUM", "HIGH"],
    )

    df = df.sort_values("churn_risk_score", ascending=False)
    return df


def detect_inventory_risk(engine, lookback_days: int = 90) -> pd.DataFrame:
    """Phát hiện sản phẩm có nguy cơ tồn kho chết."""
    query = f"""
        SELECT
            p.product_key,
            p.name AS product_name,
            p.category,
            AVG(i.quantity) AS avg_stock,
            AVG(i.quantity * p.standard_cost) AS avg_inventory_value,
            COALESCE(AVG(s.qty_sold), 0) AS avg_monthly_sold,
            CASE
                WHEN COALESCE(AVG(s.qty_sold), 0) = 0 THEN 999
                ELSE AVG(i.quantity) / NULLIF(AVG(s.qty_sold), 0)
            END AS months_of_stock
        FROM dw.dim_product p
        JOIN dw.fact_inventory i ON p.product_key = i.product_key
        LEFT JOIN (
            SELECT product_key,
                   SUM(order_qty) / 3.0 AS qty_sold
            FROM dw.fact_sales
            WHERE date_key >= (SELECT MAX(date_key) - {lookback_days} FROM dw.fact_sales)
            GROUP BY product_key
        ) s ON p.product_key = s.product_key
        GROUP BY p.product_key, p.name, p.category
        HAVING AVG(i.quantity) > 0
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        return df

    df["risk_level"] = "LOW"
    df.loc[df["months_of_stock"] >= 6, "risk_level"] = "MEDIUM"
    df.loc[df["months_of_stock"] >= 12, "risk_level"] = "HIGH"
    df = df.sort_values("months_of_stock", ascending=False)
    return df


def run_early_warning(engine=None) -> dict:
    """Chạy toàn bộ early warning pipeline."""
    if engine is None:
        engine = get_engine()

    logger.info("=== EARLY WARNING SYSTEM ===")

    logger.info("1. Detecting churn risk customers...")
    churn_df = detect_churn_risk(engine)
    high_churn = churn_df[churn_df["risk_level"] == "HIGH"] if not churn_df.empty else pd.DataFrame()
    logger.info(f"   HIGH risk churn: {len(high_churn)} customers")

    logger.info("2. Detecting inventory risk products...")
    inv_df = detect_inventory_risk(engine)
    high_inv = inv_df[inv_df["risk_level"] == "HIGH"] if not inv_df.empty else pd.DataFrame()
    logger.info(f"   HIGH risk inventory: {len(high_inv)} products")

    results = {
        "churn_risk": {
            "high_count": len(high_churn),
            "total_analyzed": len(churn_df),
            "high_value_at_risk": churn_df[churn_df["risk_level"] == "HIGH"]["cur_monetary"].sum() if not churn_df.empty else 0,
        },
        "inventory_risk": {
            "high_count": len(high_inv),
            "total_analyzed": len(inv_df),
            "high_value_at_risk": inv_df[inv_df["risk_level"] == "HIGH"]["avg_inventory_value"].sum() if not inv_df.empty else 0,
        },
        "calculated_at": datetime.now(),
    }

    logger.info(f"   Churn risk: {results['churn_risk']['high_count']} HIGH / {results['churn_risk']['total_analyzed']} total")
    logger.info(f"   Inventory risk: {results['inventory_risk']['high_count']} HIGH / {results['inventory_risk']['total_analyzed']} total")

    return results


if __name__ == "__main__":
    run_early_warning()
