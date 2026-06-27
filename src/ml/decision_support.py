import os
import sys
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.config import load_postgres_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_engine():
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


def customer_priority(row):
    label = row["cluster_label"]
    recency = row["recency_days"]
    monetary = row["monetary"]

    if label == "At-Risk" and monetary >= 10000:
        return "HIGH", "Ưu tiên chăm sóc lại khách hàng giá trị cao có dấu hiệu rời bỏ"
    if label == "Champions":
        return "MEDIUM", "Duy trì engagement và đề xuất ưu đãi giữ chân nhóm khách hàng tốt nhất"
    if label == "New Customers":
        return "MEDIUM", "Kích hoạt lần mua tiếp theo cho khách hàng mới"
    if label == "Low Value":
        return "LOW", "Theo dõi định kỳ, chưa cần ưu tiên ngân sách cao"
    if recency > 180:
        return "MEDIUM", "Khách hàng đã lâu chưa mua, nên đưa vào chiến dịch tái kích hoạt"
    return "LOW", "Theo dõi định kỳ"


def inventory_priority(row):
    dio = row["days_inventory_outstanding"]
    value = row["inventory_value"]

    if dio >= 180 and value >= 10000:
        return "HIGH", "Xem xét thanh lý hoặc điều chỉnh reorder policy vì tồn kho lâu và giá trị tồn cao"
    if dio >= 90:
        return "MEDIUM", "Kiểm tra lại nhu cầu bán hàng và kế hoạch nhập hàng"
    return "MEDIUM", "Sản phẩm bị mô hình đánh dấu bất thường, cần kiểm tra thủ công"


def run_decision_support():
    engine = get_engine()

    logger.info("Reading ML outputs...")
    customers = pd.read_sql(
        text("SELECT * FROM dw.ml_customer_segments"),
        engine,
    )

    inventory = pd.read_sql(
        text("SELECT * FROM dw.ml_inventory_anomaly WHERE anomaly_flag = true"),
        engine,
    )

    decisions = []
    now = datetime.now()

    for _, row in customers.iterrows():
        priority, action = customer_priority(row)
        if priority == "LOW":
            continue

        decisions.append(
            {
                "entity_type": "customer",
                "entity_key": int(row["customer_key"]),
                "signal_type": f"Customer Segment: {row['cluster_label']}",
                "priority": priority,
                "recommended_action": action,
                "reason": (
                    f"RFM profile: recency={row['recency_days']}, "
                    f"frequency={row['frequency']}, monetary={float(row['monetary']):,.2f}"
                ),
                "_load_timestamp": now,
            }
        )

    for _, row in inventory.iterrows():
        priority, action = inventory_priority(row)

        decisions.append(
            {
                "entity_type": "product",
                "entity_key": int(row["product_key"]),
                "signal_type": "Inventory Anomaly",
                "priority": priority,
                "recommended_action": action,
                "reason": (
                    f"{row['product_name']} | category={row['category']} | "
                    f"DIO={float(row['days_inventory_outstanding']):.1f}, "
                    f"inventory_value={float(row['inventory_value']):,.2f}, "
                    f"anomaly_score={float(row['anomaly_score']):.4f}"
                ),
                "_load_timestamp": now,
            }
        )

    output = pd.DataFrame(decisions)

    if output.empty:
        output = pd.DataFrame(
            columns=[
                "entity_type",
                "entity_key",
                "signal_type",
                "priority",
                "recommended_action",
                "reason",
                "_load_timestamp",
            ]
        )

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

    logger.info("Done. Wrote %s decision support rows.", f"{len(output):,}")
    if not output.empty:
        logger.info("Priority distribution:\n%s", output["priority"].value_counts())


if __name__ == "__main__":
    run_decision_support()
