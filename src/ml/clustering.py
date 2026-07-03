import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from src.config import load_postgres_settings

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


RFM_QUERY = """
WITH base AS (
    SELECT MAX(d.date) + INTERVAL '1 day' AS analysis_date
    FROM dw.fact_sales f
    JOIN dw.dim_date d ON f.date_key = d.date_key
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
    GROUP BY c.customer_key, c.full_name
)
SELECT
    r.customer_key,
    r.full_name,
    (b.analysis_date::date - r.last_purchase_date) AS recency_days,
    r.frequency,
    r.monetary
FROM rfm r
CROSS JOIN base b
WHERE r.monetary > 0;
"""


def get_engine():
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


def choose_best_k(x, min_k=2, max_k=7):
    scores = []
    max_k = min(max_k, len(x) - 1)

    for k in range(min_k, max_k + 1):
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = model.fit_predict(x)
        score = silhouette_score(x, labels)
        scores.append((k, score, model.inertia_))

    if not scores:
        return 2, pd.DataFrame()

    best_k = max(scores, key=lambda item: item[1])[0]
    score_df = pd.DataFrame(scores, columns=["k", "silhouette_score", "inertia"])
    return best_k, score_df


def assign_cluster_labels(df):
    profile = (
        df.groupby("cluster_id")
        .agg(
            recency_days=("recency_days", "mean"),
            frequency=("frequency", "mean"),
            monetary=("monetary", "mean"),
        )
        .reset_index()
    )

    profile["rfm_score"] = (
        -profile["recency_days"].rank(pct=True)
        + profile["frequency"].rank(pct=True)
        + profile["monetary"].rank(pct=True)
    )

    sorted_clusters = profile.sort_values("rfm_score", ascending=False)["cluster_id"].tolist()

    label_pool = [
        "Champions",
        "Loyal Customers",
        "Potential Loyalists",
        "New Customers",
        "At-Risk",
        "Low Value",
    ]

    label_map = {}
    for idx, cluster_id in enumerate(sorted_clusters):
        label_map[cluster_id] = label_pool[min(idx, len(label_pool) - 1)]

    return df["cluster_id"].map(label_map)


def run_customer_clustering():
    engine = get_engine()

    logger.info("Reading RFM data from DWH...")
    df = pd.read_sql(text(RFM_QUERY), engine)

    if df.empty:
        raise RuntimeError("No RFM data found. Run ETL full load first.")

    df["recency_days"] = pd.to_numeric(df["recency_days"], errors="coerce")
    df["frequency"] = pd.to_numeric(df["frequency"], errors="coerce")
    df["monetary"] = pd.to_numeric(df["monetary"], errors="coerce")
    df = df.dropna(subset=["recency_days", "frequency", "monetary"])

    q1 = df["monetary"].quantile(0.25)
    q3 = df["monetary"].quantile(0.75)
    iqr = q3 - q1
    df_model = df[df["monetary"] <= q3 + 3 * iqr].copy()

    features = df_model[["recency_days", "frequency", "monetary"]].copy()
    features["recency_days"] = features["recency_days"] * -1

    scaler = StandardScaler()
    x = scaler.fit_transform(features)

    best_k, score_df = choose_best_k(x)
    logger.info("Best K selected: %s", best_k)

    model = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    df_model["cluster_id"] = model.fit_predict(x)

    # Save scaler and centroids for migration module (cross-period consistency)
    scaler_params = {"mean_": scaler.mean_.tolist(), "scale_": scaler.scale_.tolist()}
    with open(MODELS_DIR / "rfm_scaler.json", "w") as f:
        json.dump(scaler_params, f)
    centroids_path = MODELS_DIR / "rfm_centroids.npy"
    np.save(centroids_path, model.cluster_centers_)
    logger.info("Saved scaler params to models/rfm_scaler.json")
    logger.info("Saved centroids to models/rfm_centroids.npy")

    final_silhouette = silhouette_score(x, df_model["cluster_id"]) if best_k > 1 else None
    df_model["silhouette_score"] = final_silhouette
    df_model["cluster_label"] = assign_cluster_labels(df_model)
    df_model["_load_timestamp"] = datetime.now()

    output = df_model[
        [
            "customer_key",
            "full_name",
            "recency_days",
            "frequency",
            "monetary",
            "cluster_id",
            "cluster_label",
            "silhouette_score",
            "_load_timestamp",
        ]
    ].copy()

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE dw.ml_customer_segments"))

    output.to_sql(
        "ml_customer_segments",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
        chunksize=10000,
    )

    if not score_df.empty:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE dw.ml_customer_clustering_metrics"))

    score_df.to_sql(
        "ml_customer_clustering_metrics",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )

    logger.info("Done. Wrote %s customer segment rows.", f"{len(output):,}")
    logger.info("Cluster distribution:\n%s", output["cluster_label"].value_counts())


if __name__ == "__main__":
    run_customer_clustering()
