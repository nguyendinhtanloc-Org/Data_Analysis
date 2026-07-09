"""Customer Migration & Concept Drift Tracking.

Module này theo dõi sự di chuyển của khách hàng giữa các cluster
qua các kỳ (Q1 → Q2 → Q3 → Q4).

QUAN TRỌNG: Sử dụng FIXED CENTROIDS từ clustering.py (fit 1 lần trên toàn bộ dữ liệu).
Không fit K-Means riêng mỗi kỳ — điều đó làm cluster không tương thích giữa các kỳ.

Output: mart.customer_migration, mart.rfm_snapshot
"""
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sklearn.preprocessing import StandardScaler

from src.config import load_postgres_settings

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

from src.ml.clustering import assign_cluster_labels

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_engine():
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


def get_rfm_by_period(engine, start_date: str, end_date: str) -> pd.DataFrame:
    """Tính RFM cho một kỳ cụ thể."""
    query = """
        WITH base AS (
            SELECT CAST(:end_date AS date) AS analysis_date
        ),
        rfm AS (
            SELECT
                c.customer_key,
                c.full_name,
                MAX(d.date) AS last_purchase_date,
                COUNT(f.sales_order_detail_id) AS frequency,
                SUM(f.line_total) AS monetary
            FROM dw.fact_sales f
            JOIN dw.dim_customer c ON f.customer_key = c.customer_key
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
            GROUP BY c.customer_key, c.full_name
        )
        SELECT
            r.customer_key,
            r.full_name,
            (b.analysis_date - r.last_purchase_date) AS recency_days,
            r.frequency,
            r.monetary
        FROM rfm r
        CROSS JOIN base b
        WHERE r.monetary > 0
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text(query),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )
    return df


def _load_fixed_centroids():
    """Load fixed centroids và scaler từ clustering.py (fit 1 lần trên all-time data)."""
    centroids_path = MODELS_DIR / "rfm_centroids.npy"
    scaler_path = MODELS_DIR / "rfm_scaler.json"

    if not centroids_path.exists() or not scaler_path.exists():
        raise FileNotFoundError(
            "Không tìm thấy model artifacts (rfm_centroids.npy, rfm_scaler.json). "
            "Chạy src.ml.clustering.run_customer_clustering() trước."
        )

    centroids = np.load(centroids_path)
    with open(scaler_path) as f:
        scaler_params = json.load(f)

    scaler = StandardScaler()
    scaler.mean_ = np.array(scaler_params["mean_"])
    scaler.scale_ = np.array(scaler_params["scale_"])
    scaler.n_features_in_ = len(scaler_params["mean_"])

    return centroids, scaler


def compute_clusters_for_period(df: pd.DataFrame, period_key: str = "") -> pd.DataFrame:
    """Gán cluster cho RFM của một kỳ dùng FIXED CENTROIDS từ all-time data.

    Không fit K-Means mới — dùng nearest-centroid assignment.
    Điều này đảm bảo cluster label có ý nghĩa tương đương giữa các kỳ.
    """
    if df.empty:
        return df

    centroids, scaler = _load_fixed_centroids()

    df_model = df.copy()
    df_model["recency_days"] = pd.to_numeric(df_model["recency_days"], errors="coerce")
    df_model["frequency"] = pd.to_numeric(df_model["frequency"], errors="coerce")
    df_model["monetary"] = pd.to_numeric(df_model["monetary"], errors="coerce")
    df_model = df_model.dropna(subset=["recency_days", "frequency", "monetary"])

    if len(df_model) < 10:
        return df_model

    features = df_model[["recency_days", "frequency", "monetary"]].copy()
    features["recency_days"] = features["recency_days"] * -1

    x = scaler.transform(features.values)

    # Nearest-centroid assignment
    distances = np.linalg.norm(x[:, np.newaxis] - centroids, axis=2)
    df_model["cluster_id"] = np.argmin(distances, axis=1)
    df_model["silhouette_score"] = None  # Silhouette không có ý nghĩa với fixed centroids
    df_model["cluster_label"] = assign_cluster_labels(df_model)

    # Track mean nearest-centroid distance (log info, không warning vì
    # so với all-time centroids tự nhiên cao ở quý đầu — không phải drift)
    mean_dist = float(np.mean(np.min(distances, axis=1)))
    logger.info(f"  [Period {period_key}] Mean nearest-centroid distance: {mean_dist:.3f}")

    # So sánh distribution so với baseline
    cluster_dist = df_model["cluster_label"].value_counts(normalize=True)
    logger.info(f"  [Period {period_key}] Cluster distribution: {cluster_dist.to_dict()}")

    return df_model


def build_migration_matrix(
    prev_df: pd.DataFrame,
    curr_df: pd.DataFrame,
    prev_period_key: str,
    curr_period_key: str,
) -> pd.DataFrame:
    """Xây dựng migration matrix giữa 2 kỳ.

    Returns:
        pd.DataFrame: Mỗi row là 1 customer với cluster trước/sau.
    """
    if prev_df.empty or curr_df.empty:
        return pd.DataFrame()

    merged = pd.merge(
        curr_df[["customer_key", "cluster_label", "monetary"]],
        prev_df[["customer_key", "cluster_label", "monetary"]],
        on="customer_key", how="outer",
        suffixes=("_curr", "_prev"),
        indicator=True,
    )

    merged["prev_period_key"] = prev_period_key
    merged["curr_period_key"] = curr_period_key
    merged["prev_cluster"] = merged["cluster_label_prev"].fillna("New")
    merged["curr_cluster"] = merged["cluster_label_curr"].fillna("Churned")
    merged["prev_monetary"] = merged["monetary_prev"]
    merged["curr_monetary"] = merged["monetary_curr"]
    merged["is_churned"] = merged["_merge"] == "right_only"
    merged["is_new"] = merged["_merge"] == "left_only"
    merged["calculated_at"] = datetime.now()

    cols = [
        "customer_key", "prev_period_key", "curr_period_key",
        "prev_cluster", "curr_cluster",
        "prev_monetary", "curr_monetary",
        "is_churned", "is_new", "calculated_at",
    ]
    return merged[cols].copy()


def save_migration_to_mart(engine, df: pd.DataFrame) -> int:
    """Lưu migration data vào mart.customer_migration."""
    if df.empty:
        return 0

    records = []
    for _, row in df.iterrows():
        records.append({
            "customer_key": int(row["customer_key"]),
            "prev_period_key": row["prev_period_key"],
            "curr_period_key": row["curr_period_key"],
            "prev_cluster": str(row["prev_cluster"]),
            "curr_cluster": str(row["curr_cluster"]),
            "prev_monetary": float(row["prev_monetary"]) if pd.notna(row["prev_monetary"]) else None,
            "curr_monetary": float(row["curr_monetary"]) if pd.notna(row["curr_monetary"]) else None,
            "is_churned": bool(row["is_churned"]),
            "is_new": bool(row["is_new"]),
            "calculated_at": row["calculated_at"],
        })

    BATCH = 1000
    with engine.begin() as conn:
        for i in range(0, len(records), BATCH):
            batch = records[i:i + BATCH]
            conn.execute(
                text("""
                    INSERT INTO mart.customer_migration
                        (customer_key, prev_period_key, curr_period_key,
                         prev_cluster, curr_cluster,
                         prev_monetary, curr_monetary,
                         is_churned, is_new, calculated_at)
                    VALUES
                        (:customer_key, :prev_period_key, :curr_period_key,
                         :prev_cluster, :curr_cluster,
                         :prev_monetary, :curr_monetary,
                         :is_churned, :is_new, :calculated_at)
                    ON CONFLICT (customer_key, prev_period_key, curr_period_key)
                    DO UPDATE SET
                        prev_cluster = EXCLUDED.prev_cluster,
                        curr_cluster = EXCLUDED.curr_cluster,
                        is_churned = EXCLUDED.is_churned,
                        is_new = EXCLUDED.is_new
                """),
                batch,
            )
    return len(df)


def save_rfm_snapshot(engine, df: pd.DataFrame, period_key: str, start_date: str, end_date: str) -> int:
    """Lưu RFM cluster distribution snapshot vào mart.rfm_snapshot."""
    if df.empty:
        return 0

    profile = (
        df.groupby("cluster_label")
        .agg(
            customer_count=("customer_key", "count"),
            avg_recency=("recency_days", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_monetary=("monetary", "mean"),
        )
        .reset_index()
    )
    profile["total_monetary"] = profile["avg_monetary"] * profile["customer_count"]
    total_m = profile["total_monetary"].sum()
    profile["pct_of_total"] = (profile["total_monetary"] / total_m * 100).round(2) if total_m > 0 else 0
    profile["period_key"] = period_key
    profile["period_start"] = start_date
    profile["period_end"] = end_date
    profile["calculated_at"] = datetime.now()

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM mart.rfm_snapshot WHERE period_key = :pk"),
            {"pk": period_key},
        )

    profile[[
        "period_key", "period_start", "period_end", "cluster_label",
        "customer_count", "avg_recency", "avg_frequency", "avg_monetary",
        "total_monetary", "pct_of_total", "calculated_at",
    ]].to_sql(
        "rfm_snapshot", engine, schema="mart",
        if_exists="append", index=False,
    )
    return len(profile)


def run_full_migration_pipeline(
    engine=None,
    start_year: int = 2013,
    end_year: int = None,
) -> int:
    """Chạy toàn bộ migration pipeline cho tất cả các quý.

    Migration chỉ tính khi so sánh cùng quý năm trước (YoY),
    không so sánh quý liền nhau — tránh gán "churned" sai cho
    khách hàng chỉ không mua trong quý kế tiếp.

    Với mỗi quý:
        1. Tính RFM cho quý đó
        2. Gán cluster dùng fixed centroids
        3. Lưu RFM snapshot vào mart.rfm_snapshot
        4. Nếu có dữ liệu cùng quý năm trước → migration matrix

    Returns:
        int: Tổng số migration rows đã lưu.
    """
    if engine is None:
        engine = get_engine()

    if end_year is None:
        try:
            with engine.connect() as conn:
                df = pd.read_sql(
                    text("SELECT MIN(year) AS min_y, MAX(year) AS max_y FROM dw.dim_date d "
                         "WHERE EXISTS (SELECT 1 FROM dw.fact_sales f WHERE f.date_key = d.date_key)"),
                    conn,
                )
                if not df.empty and df.iloc[0]["min_y"] is not None:
                    end_year = int(df.iloc[0]["max_y"])
                else:
                    end_year = 2014
        except Exception:
            end_year = 2014

    total_rows = 0
    baseline: dict[str, pd.DataFrame] = {}

    for year in range(start_year, end_year + 1):
        for q in range(1, 5):

            period_key = f"{year}Q{q}"
            start_map = {1: f"{year}-01-01", 2: f"{year}-04-01",
                         3: f"{year}-07-01", 4: f"{year}-10-01"}
            end_map = {1: f"{year}-03-31", 2: f"{year}-06-30",
                       3: f"{year}-09-30", 4: f"{year}-12-31"}
            start_date = start_map[q]
            end_date = end_map[q]

            logger.info(f"[{period_key}] Tính RFM & clustering...")
            curr_df = get_rfm_by_period(engine, start_date, end_date)
            curr_df = compute_clusters_for_period(curr_df, period_key=period_key)

            n_snapshot = save_rfm_snapshot(engine, curr_df, period_key, start_date, end_date)
            logger.info(f"  → RFM snapshot: {n_snapshot} clusters")

            # YoY comparison: chỉ so cùng quý năm trước, không so Q1→Q2
            if year > start_year:
                prev_key = f"{year - 1}Q{q}"
                prev_df = baseline.get(prev_key)
                if prev_df is not None and not prev_df.empty and not curr_df.empty:
                    migration_df = build_migration_matrix(prev_df, curr_df, prev_key, period_key)
                    n_mig = save_migration_to_mart(engine, migration_df)
                    total_rows += n_mig
                    logger.info(f"  → Migration: {n_mig} customers tracked")

                    churned = migration_df["is_churned"].sum()
                    new = migration_df["is_new"].sum()
                    if churned > 0 or new > 0:
                        logger.warning(f"  → Churned: {churned}, New: {new}")

            baseline[period_key] = curr_df

    logger.info(f"Migration pipeline hoàn tất: {total_rows} migration rows")
    return total_rows


if __name__ == "__main__":
    run_full_migration_pipeline()
