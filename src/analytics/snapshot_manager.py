"""Snapshot Manager - Quản lý việc tính và lưu snapshot KPI định kỳ.

Module này chịu trách nhiệm:
  1. Đọc watermark snapshot từ config.json (snapshot_watermark)
  2. Xác định kỳ cần tính (Q1, Q2, ...) dựa trên watermark
  3. Gọi KPI calculator cho từng kỳ
  4. UPSERT vào mart.kpi_snapshot
  5. Cập nhật watermark snapshot
"""
import fcntl
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.analytics.kpi_calculator import (
    calculate_all_kpis,
    get_quarter_boundaries,
    get_year_boundaries,
    get_period_key,
)

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"
_LOCK_PATH = CONFIG_PATH.with_suffix(".json.lock")


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(config: dict) -> None:
    lock_fd = None
    try:
        lock_fd = open(_LOCK_PATH, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, default=str)
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


def get_snapshot_watermark() -> Optional[str]:
    """Lấy watermark snapshot cuối cùng đã chạy."""
    config = _load_config()
    return config.get("snapshot_watermark")


def save_snapshot_watermark(period_key: str) -> None:
    """Lưu watermark snapshot."""
    config = _load_config()
    config["snapshot_watermark"] = period_key
    config["last_snapshot_run"] = datetime.now().isoformat()
    _save_config(config)


def get_data_date_range(engine: Engine) -> tuple[int, int]:
    """Xác định năm nhỏ nhất và lớn nhất có dữ liệu trong DWH.

    Returns:
        (min_year, max_year): Khoảng năm thực tế có dữ liệu bán hàng.
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text("SELECT MIN(year) AS min_y, MAX(year) AS max_y FROM dw.dim_date d "
                     "WHERE EXISTS (SELECT 1 FROM dw.fact_sales f WHERE f.date_key = d.date_key)"),
                conn,
            )
            if df.empty or df.iloc[0]["min_y"] is None:
                return (2013, date.today().year)
            return (int(df.iloc[0]["min_y"]), int(df.iloc[0]["max_y"]))
    except Exception:
        return (2013, date.today().year)


def get_pending_periods(engine: Engine, snapshot_type: str = "Q") -> list[dict]:
    """Xác định các kỳ chưa được snapshot dựa trên watermark và dữ liệu thực tế.

    Args:
        engine: SQLAlchemy engine để query DWH cho date range.

    Returns:
        list[dict]: Danh sách các kỳ cần tính, mỗi kỳ có:
            - period_key: str (e.g. '2024Q1')
            - period_type: str ('Q' | 'Y')
            - start_date: str
            - end_date: str
            - year: int
            - quarter: int | None
    """
    last_watermark = get_snapshot_watermark()
    min_year, max_year = get_data_date_range(engine)

    periods = []

    if snapshot_type == "Q":
        for year in range(min_year, max_year + 1):
            max_q = 4 if year < max_year else 4
            for q in range(1, max_q + 1):
                pk = get_period_key("Q", year, q)
                if last_watermark and pk <= last_watermark:
                    continue
                start, end = get_quarter_boundaries(year, q)
                periods.append({
                    "period_key": pk,
                    "period_type": "Q",
                    "start_date": start,
                    "end_date": end,
                    "year": year,
                    "quarter": q,
                })
    elif snapshot_type == "Y":
        for year in range(min_year, max_year + 1):
            pk = get_period_key("Y", year)
            if last_watermark and pk <= last_watermark:
                continue
            start, end = get_year_boundaries(year)
            periods.append({
                "period_key": pk,
                "period_type": "Y",
                "start_date": start,
                "end_date": end,
                "year": year,
                "quarter": None,
            })

    return periods


def run_kpi_snapshot(engine: Engine, snapshot_type: str = "Q") -> int:
    """Tính và lưu KPI snapshot cho các kỳ chưa có.

    Returns:
        int: Số bản ghi snapshot đã insert.
    """
    periods = get_pending_periods(engine, snapshot_type)
    if not periods:
        logger.info("Không có kỳ mới cần snapshot.")
        return 0

    total_rows = 0
    for period in periods:
        logger.info(
            f"Tính KPI cho {period['period_key']} "
            f"({period['start_date']} → {period['end_date']})..."
        )

        kpi_values = calculate_all_kpis(engine, period["start_date"], period["end_date"])

        snapshot_rows = []
        for kv in kpi_values:
            snapshot_rows.append({
                "kpi_name": kv["kpi_name"],
                "period_type": period["period_type"],
                "period_key": period["period_key"],
                "period_start": period["start_date"],
                "period_end": period["end_date"],
                "value": float(kv["value"]) if kv.get("value") is not None else None,
                "dimension": kv.get("dimension", "overall"),
                "dimension_value": kv.get("dimension_value", "overall"),
                "row_count": int(kv.get("row_count", 0)),
                "calculated_at": datetime.now(),
            })

        if snapshot_rows:
            df_snapshot = pd.DataFrame(snapshot_rows)
            _upsert_kpi_snapshot(engine, df_snapshot)
            total_rows += len(snapshot_rows)
            logger.info(f"  → Inserted {len(snapshot_rows)} KPI rows cho {period['period_key']}")

        save_snapshot_watermark(period["period_key"])

    logger.info(f"Hoàn tất KPI snapshot: {total_rows} rows cho {len(periods)} periods")
    return total_rows


def _upsert_kpi_snapshot(engine: Engine, df: pd.DataFrame) -> None:
    """UPSERT KPI snapshot vào mart.kpi_snapshot, tránh duplicate."""
    rows = df.to_dict("records")
    BATCH_SIZE = 1000
    with engine.begin() as conn:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            conn.execute(
                text("""
                    INSERT INTO mart.kpi_snapshot
                        (kpi_name, period_type, period_key, period_start, period_end,
                         value, dimension, dimension_value, row_count, calculated_at)
                    VALUES
                        (:kpi_name, :period_type, :period_key, :period_start, :period_end,
                         :value, :dimension, :dimension_value, :row_count, :calculated_at)
                    ON CONFLICT (kpi_name, period_type, period_key, dimension, dimension_value)
                    DO UPDATE SET
                        value = EXCLUDED.value,
                        row_count = EXCLUDED.row_count,
                        calculated_at = EXCLUDED.calculated_at
                """),
                batch,
            )


def run_rfm_snapshot(engine: Engine, period_key: str, start_date: str, end_date: str) -> int:
    """Tính RFM cluster distribution cho một kỳ và lưu vào mart.rfm_snapshot.

    Returns:
        int: Số cluster đã insert.
    """
    query = """
        WITH rfm AS (
            SELECT
                c.customer_key,
                MAX(d.date) AS last_purchase_date,
                COUNT(f.sales_order_detail_id) AS frequency,
                SUM(f.line_total) AS monetary
            FROM dw.fact_sales f
            JOIN dw.dim_customer c ON f.customer_key = c.customer_key
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
            GROUP BY c.customer_key
        )
        SELECT
            COALESCE(s.cluster_label, 'Unclassified') AS cluster_label,
            COUNT(*) AS customer_count,
            AVG(:end_date::date - r.last_purchase_date) AS avg_recency,
            AVG(r.frequency) AS avg_frequency,
            AVG(r.monetary) AS avg_monetary,
            SUM(r.monetary) AS total_monetary
        FROM rfm r
        LEFT JOIN dw.ml_customer_segments s ON r.customer_key = s.customer_key
        WHERE r.monetary > 0
        GROUP BY s.cluster_label
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text(query),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )

    if df.empty:
        return 0

    total_monetary_all = df["total_monetary"].sum()
    df["pct_of_total"] = (df["total_monetary"] / total_monetary_all * 100).round(2) if total_monetary_all > 0 else 0
    df["period_key"] = period_key
    df["period_start"] = start_date
    df["period_end"] = end_date
    df["calculated_at"] = datetime.now()

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM mart.rfm_snapshot WHERE period_key = :pk"),
            {"pk": period_key},
        )
    df[["period_key", "period_start", "period_end", "cluster_label",
        "customer_count", "avg_recency", "avg_frequency", "avg_monetary",
        "total_monetary", "pct_of_total", "calculated_at"]].to_sql(
        "rfm_snapshot", engine, schema="mart",
        if_exists="append", index=False,
    )

    logger.info(f"RFM snapshot {period_key}: {len(df)} clusters")
    return len(df)
