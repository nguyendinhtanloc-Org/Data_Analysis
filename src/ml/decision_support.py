"""Insight Engine - Tầng hỗ trợ quyết định thông minh.

Không chỉ đưa ra recommendations dạng rule-based,
mà còn tích hợp:
  - Insight từ KPI snapshot (phát hiện trend bất thường)
  - Insight từ contribution analysis (xác định nguyên nhân)
  - Insight từ customer migration (phát hiện churn)
  - Insight từ early warning (cảnh báo sớm)
  - Insight từ causal inference (bằng chứng nhân quả)
"""
import logging
from datetime import datetime

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


def _load_customer_segments(engine) -> pd.DataFrame:
    return pd.read_sql(text("SELECT * FROM dw.ml_customer_segments"), engine)


def _load_inventory_anomalies(engine) -> pd.DataFrame:
    return pd.read_sql(
        text("SELECT * FROM dw.ml_inventory_anomaly WHERE anomaly_flag = true OR zero_sales_flag = true"),
        engine,
    )


def _load_kpi_snapshots(engine, kpi_name: str = None) -> pd.DataFrame:
    if kpi_name:
        query = "SELECT * FROM mart.kpi_snapshot WHERE kpi_name = :kpi_name ORDER BY period_key"
        return pd.read_sql(text(query), engine, params={"kpi_name": kpi_name})
    query = "SELECT * FROM mart.kpi_snapshot ORDER BY period_key"
    return pd.read_sql(text(query), engine)


def _load_period_comparisons(engine, kpi_name: str = None) -> pd.DataFrame:
    if kpi_name:
        query = "SELECT * FROM mart.period_comparison WHERE kpi_name = :kpi_name ORDER BY curr_period_key, contribution_pct DESC"
        return pd.read_sql(text(query), engine, params={"kpi_name": kpi_name})
    query = "SELECT * FROM mart.period_comparison ORDER BY curr_period_key, contribution_pct DESC"
    return pd.read_sql(text(query), engine)


def _load_migration_data(engine) -> pd.DataFrame:
    return pd.read_sql(text("SELECT * FROM mart.customer_migration"), engine)


def customer_priority(row):
    label = row["cluster_label"]
    recency = row["recency_days"]
    monetary = row["monetary"]

    if label == "Champions" and monetary >= 5000:
        return ("HIGH",
                "VIP retention: khách hàng Champions giá trị cao, "
                "ưu tiên chương trình loyalty đặc biệt",
                f"Champions, monetary=${monetary:,.0f}")
    if label == "Champions":
        return ("MEDIUM",
                "Duy trì engagement cho Champions",
                f"Champions, monetary=${monetary:,.0f}")
    if label == "Loyal Customers" and recency <= 30 and monetary >= 2000:
        return ("HIGH",
                "Loyal Customers active gần đây và giá trị cao, "
                "ưu tiên cross-sell/upsell",
                f"Loyal, recency={recency}d, monetary=${monetary:,.0f}")
    if label == "Loyal Customers" and recency > 180:
        return ("HIGH",
                "Loyal Customers đã lâu không mua, "
                "cần chiến dịch tái kích hoạt khẩn cấp",
                f"Loyal dormant, recency={recency}d, monetary=${monetary:,.0f}")
    if label == "Loyal Customers":
        return ("MEDIUM",
                "Loyal Customers tiêu chuẩn, duy trì engagement",
                f"Loyal, recency={recency}d, monetary=${monetary:,.0f}")
    if label == "Potential Loyalists" and monetary >= 1000:
        return ("MEDIUM",
                "Potential Loyalists giá trị cao, cần nurturing",
                f"Potential Loyalist, monetary=${monetary:,.0f}")
    if label == "Potential Loyalists":
        return ("LOW",
                "Potential Loyalists giá trị thấp, theo dõi định kỳ",
                f"Potential Loyalist, monetary=${monetary:,.0f}")
    return ("LOW", "Theo dõi định kỳ", "No specific signal")


def inventory_priority(row):
    dio = row["days_inventory_outstanding"]
    value = row["inventory_value"]
    anomaly_score = row.get("anomaly_score", 0)
    zero_sales = row.get("zero_sales_flag", False)

    if zero_sales:
        return ("MEDIUM",
                "Sản phẩm không có doanh số, cần đánh giá lại danh mục",
                "Zero sales product")
    if dio >= 360 and value >= 5000:
        return ("HIGH",
                "Xem xét thanh lý vì tồn kho rất lâu và giá trị cao",
                f"DIO={dio:.0f}, value=${value:,.0f}")
    if dio >= 180:
        return ("MEDIUM",
                "Tồn kho lâu ngày, kiểm tra reorder policy",
                f"DIO={dio:.0f}")
    if anomaly_score >= 80:
        return ("MEDIUM",
                "Sản phẩm có bất thường theo mô hình, cần kiểm tra",
                f"anomaly_score={anomaly_score:.0f}")
    return ("LOW",
            "Sản phẩm bình thường, theo dõi định kỳ",
            f"DIO={dio:.0f}, anomaly_score={anomaly_score:.0f}")


def generate_insights_from_kpi_snapshots(engine) -> list[dict]:
    """Sinh insights từ KPI snapshot: phát hiện trend bất thường."""
    insights = []
    try:
        df = _load_kpi_snapshots(engine)
        if df.empty:
            return insights

        for kpi_name in df["kpi_name"].unique():
            kpi_df = df[df["kpi_name"] == kpi_name].sort_values("period_key")
            if len(kpi_df) < 2:
                continue

            values = kpi_df["value"].dropna().values
            if len(values) < 2:
                continue

            recent = values[-1]
            prev = values[-2]
            pct_change = ((recent - prev) / prev * 100) if prev != 0 else 0

            if abs(pct_change) > 10:
                severity = "warning" if abs(pct_change) > 20 else "info"
                trend = "up" if pct_change > 0 else "down"
                insights.append({
                    "entity_type": "kpi",
                    "entity_key": 0,
                    "signal_type": f"KPI Trend: {kpi_name}",
                    "priority": "HIGH" if severity == "warning" else "MEDIUM",
                    "recommended_action": (
                        f"KPI {kpi_name} {trend} {abs(pct_change):.1f}% kỳ này. "
                        f"Cần phân tích nguyên nhân."
                    ),
                    "reason": (
                        f"{kpi_name}: {float(recent):,.2f} vs {float(prev):,.2f} "
                        f"({pct_change:+.1f}%)"
                    ),
                    "_load_timestamp": datetime.now(),
                })
    except Exception as e:
        logger.warning(f"KPI insight generation failed: {e}")

    return insights


def generate_insights_from_migration(engine) -> list[dict]:
    """Sinh insights từ customer migration."""
    insights = []
    try:
        df = _load_migration_data(engine)
        if df.empty:
            return insights

        churned = df[df["is_churned"]]
        new = df[df["is_new"]]
        downgraded = df[
            (df["prev_cluster"].isin(["Champions", "Loyal Customers"]))
            & (~df["curr_cluster"].isin(["Champions", "Loyal Customers"]))
        ]

        for cluster in ["Champions", "Loyal Customers", "At-Risk"]:
            churned_cluster = churned[churned["prev_cluster"] == cluster]
            if len(churned_cluster) > 0:
                churn_value = churned_cluster["prev_monetary"].sum()
                insights.append({
                    "entity_type": "customer_segment",
                    "entity_key": 0,
                    "signal_type": f"Migration: {cluster}",
                    "priority": "HIGH" if len(churned_cluster) > 10 else "MEDIUM",
                    "recommended_action": (
                        f"{len(churned_cluster)} KH từ {cluster} đã ngừng mua hàng "
                        f"(giá trị mất: ${churn_value:,.0f}). Cần chiến dịch win-back."
                    ),
                    "reason": f"Churned from {cluster}, total value= ${churn_value:,.0f}",
                    "_load_timestamp": datetime.now(),
                })

        if len(downgraded) > 0:
            downgrade_value = downgraded["prev_monetary"].sum()
            insights.append({
                "entity_type": "customer_segment",
                "entity_key": 0,
                "signal_type": "Migration: Downgraded",
                "priority": "MEDIUM",
                "recommended_action": (
                    f"{len(downgraded)} KH từ Champion/Loyal đang giảm hạng. "
                    f"Triển khai chương trình loyalty phục hồi."
                ),
                "reason": f"{len(downgraded)} downgraded, value at risk=${downgrade_value:,.0f}",
                "_load_timestamp": datetime.now(),
            })

        if len(new) > 0:
            new_value = new["curr_monetary"].sum()
            insights.append({
                "entity_type": "customer_segment",
                "entity_key": 0,
                "signal_type": "Migration: New Customers",
                "priority": "MEDIUM",
                "recommended_action": (
                    f"{len(new)} KH mới, tổng giá trị ${new_value:,.0f}. "
                    f"Cần kích hoạt lần mua thứ 2."
                ),
                "reason": f"{len(new)} new customers, total=${new_value:,.0f}",
                "_load_timestamp": datetime.now(),
            })

    except Exception as e:
        logger.warning(f"Migration insight generation failed: {e}")

    return insights


def run_decision_support(engine=None) -> None:
    """Chạy toàn bộ insight engine."""
    if engine is None:
        engine = get_engine()

    logger.info("=== INSIGHT ENGINE ===")
    all_decisions = []

    logger.info("1. Customer-based insights (from ML)...")
    try:
        customers = _load_customer_segments(engine)
        for _, row in customers.iterrows():
            priority, action, reason = customer_priority(row)
            if priority == "LOW":
                continue
            all_decisions.append({
                "entity_type": "customer",
                "entity_key": int(row["customer_key"]),
                "signal_type": f"Customer Segment: {row['cluster_label']}",
                "priority": priority,
                "recommended_action": action,
                "reason": reason,
                "_load_timestamp": datetime.now(),
            })
        logger.info(f"  {sum(1 for d in all_decisions if d['entity_type'] == 'customer')} customer insights")
    except Exception as e:
        logger.warning(f"Customer insights failed: {e}")

    logger.info("2. Inventory-based insights (from ML)...")
    try:
        inventory = _load_inventory_anomalies(engine)
        for _, row in inventory.iterrows():
            priority, action, reason = inventory_priority(row)
            all_decisions.append({
                "entity_type": "product",
                "entity_key": int(row["product_key"]),
                "signal_type": "Inventory Anomaly",
                "priority": priority,
                "recommended_action": action,
                "reason": reason,
                "_load_timestamp": datetime.now(),
            })
        logger.info(f"  {sum(1 for d in all_decisions if d['entity_type'] == 'product')} inventory insights")
    except Exception as e:
        logger.warning(f"Inventory insights failed: {e}")

    logger.info("3. KPI Trend insights (from mart snapshots)...")
    kpi_insights = generate_insights_from_kpi_snapshots(engine)
    all_decisions.extend(kpi_insights)
    logger.info(f"  {len(kpi_insights)} KPI trend insights")

    logger.info("4. Customer Migration insights (from mart)...")
    migration_insights = generate_insights_from_migration(engine)
    all_decisions.extend(migration_insights)
    logger.info(f"  {len(migration_insights)} migration insights")

    output = pd.DataFrame(all_decisions)
    if output.empty:
        output = pd.DataFrame(columns=[
            "entity_type", "entity_key", "signal_type",
            "priority", "recommended_action", "reason", "_load_timestamp",
        ])

    logger.info("Writing dw.decision_support...")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE dw.decision_support"))

    output.to_sql(
        "decision_support",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )

    logger.info(f"Done. {len(output)} insights written to dw.decision_support")
    if not output.empty:
        logger.info("Priority distribution:\n%s", output["priority"].value_counts())
        logger.info("Signal type distribution:\n%s", output["signal_type"].value_counts())


if __name__ == "__main__":
    run_decision_support()
