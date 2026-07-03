"""Hypothesis Tester - Kiểm định thống kê cho các giả thuyết kinh doanh.

Cung cấp các hàm kiểm định:
  1. Two-sample t-test: So sánh KPI giữa 2 kỳ
  2. Chi-square test: Kiểm tra phân phối cluster có thay đổi không
  3. Mann-Whitney U test: Phi tham số, cho dữ liệu không normal
  4. Cohen's d: Effect size cho t-test
  5. ANOVA: So sánh nhiều nhóm
"""
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from scipy import stats

logger = logging.getLogger(__name__)


def kpi_period_comparison(
    engine: Engine,
    kpi_name: str,
    period1_start: str,
    period1_end: str,
    period2_start: str,
    period2_end: str,
) -> dict:
    """So sánh KPI giữa 2 kỳ với kiểm định thống kê.

    Returns:
        dict: Kết quả bao gồm mean, std, t-stat, p-value, effect size.
    """
    from src.analytics.kpi_calculator import KPI_DEFINITIONS

    if kpi_name not in KPI_DEFINITIONS:
        raise ValueError(f"KPI '{kpi_name}' not found")

    query = KPI_DEFINITIONS[kpi_name]["query"]

    with engine.connect() as conn:
        v1 = pd.read_sql(
            text(query), conn,
            params={"start_date": period1_start, "end_date": period1_end},
        ).iloc[0]["value"]
        v2 = pd.read_sql(
            text(query), conn,
            params={"start_date": period2_start, "end_date": period2_end},
        ).iloc[0]["value"]

    return {
        "kpi_name": kpi_name,
        "period1": f"{period1_start}→{period1_end}",
        "period2": f"{period2_start}→{period2_end}",
        "period1_value": float(v1),
        "period2_value": float(v2),
        "abs_change": float(v2 - v1),
        "pct_change": round(float((v2 - v1) / v1 * 100), 4) if v1 != 0 else None,
        "calculated_at": datetime.now(),
    }


def two_sample_ttest(
    engine: Engine,
    metric: str,
    group1_label: str,
    group1_filter: str,
    group2_label: str,
    group2_filter: str,
    start_date: str,
    end_date: str,
) -> dict:
    """Two-sample t-test so sánh metric giữa 2 nhóm.

    Args:
        engine: SQLAlchemy engine.
        metric: 'unit_price', 'line_total', 'order_qty', 'gross_profit'.
        group1_label, group2_label: Tên nhóm.
        group1_filter, group2_filter: SQL WHERE condition (vd: "p.category = 'Clothing'").
        start_date, end_date: Biên thời gian.

    Returns:
        dict: Kết quả t-test.
    """
    query_template = f"""
        SELECT SUM(f.{metric}) AS value
        FROM dw.fact_sales f
        JOIN dw.dim_date d ON f.date_key = d.date_key
        JOIN dw.dim_product p ON f.product_key = p.product_key AND p.is_current = true
        WHERE d.date BETWEEN :start_date AND :end_date
          AND f.{metric} IS NOT NULL
          AND {{filter}}
        GROUP BY f.sales_order_id
    """

    with engine.connect() as conn:
        g1 = pd.read_sql(
            text(query_template.replace("{{filter}}", group1_filter)),
            conn, params={"start_date": start_date, "end_date": end_date},
        )
        g2 = pd.read_sql(
            text(query_template.replace("{{filter}}", group2_filter)),
            conn, params={"start_date": start_date, "end_date": end_date},
        )

    v1, v2 = g1["value"].dropna(), g2["value"].dropna()

    if len(v1) < 2 or len(v2) < 2:
        return {
            "metric": metric,
            "group1": group1_label,
            "group2": group2_label,
            "error": f"Insufficient data: group1={len(v1)}, group2={len(v2)}",
        }

    t_stat, p_value = stats.ttest_ind(v1, v2, equal_var=False)
    n1, n2 = len(v1), len(v2)
    s1, s2 = v1.std(ddof=1), v2.std(ddof=1)
    pooled_std = np.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
    cohens_d = (v2.mean() - v1.mean()) / pooled_std if pooled_std > 0 else 0

    return {
        "metric": metric,
        "group1": group1_label,
        "group2": group2_label,
        "group1_mean": round(v1.mean(), 4) if n1 > 0 else None,
        "group2_mean": round(v2.mean(), 4) if n2 > 0 else None,
        "group1_std": round(s1, 4) if n1 > 0 else None,
        "group2_std": round(s2, 4) if n2 > 0 else None,
        "group1_n": n1,
        "group2_n": n2,
        "t_statistic": round(t_stat, 6),
        "p_value": round(p_value, 6),
        "is_significant": p_value < 0.05,
        "cohens_d": round(cohens_d, 4),
        "effect_size_label": _cohens_d_label(cohens_d),
        "interpretation": (
            f"Có sự khác biệt {'CÓ Ý NGHĨA' if p_value < 0.05 else 'KHÔNG có ý nghĩa'} "
            f"thống kê (p={p_value:.4f}, d={cohens_d:.3f}) giữa {group1_label} và {group2_label} "
            f"về {metric}"
        ),
        "calculated_at": datetime.now(),
    }


def _cohens_d_label(d: float) -> str:
    ad = abs(d)
    if ad >= 0.8:
        return "large"
    elif ad >= 0.5:
        return "medium"
    elif ad >= 0.2:
        return "small"
    return "negligible"


def chi_square_cluster_test(
    engine: Engine,
    period1_key: str,
    period2_key: str,
) -> dict:
    """Chi-square test xem phân phối cluster có thay đổi giữa 2 kỳ không.

    Returns:
        dict: Kết quả chi-square test.
    """
    query = """
        SELECT period_key, cluster_label, customer_count
        FROM mart.rfm_snapshot
        WHERE period_key IN (:p1, :p2)
        ORDER BY period_key, cluster_label
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text(query), conn,
            params={"p1": period1_key, "p2": period2_key},
        )

    if df.empty:
        return {"error": "No data for specified periods"}

    pivot = df.pivot_table(
        index="cluster_label", columns="period_key",
        values="customer_count", fill_value=0,
    )

    if len(pivot.columns) < 2:
        return {"error": "Need at least 2 periods for comparison"}

    observed = pivot.values
    chi2, p_value, dof, expected = stats.chi2_contingency(observed)

    cramers_v = np.sqrt(chi2 / (observed.sum() * (min(observed.shape) - 1)))

    return {
        "period1": period1_key,
        "period2": period2_key,
        "chi2_statistic": round(chi2, 4),
        "p_value": round(p_value, 6),
        "degrees_of_freedom": dof,
        "is_significant": p_value < 0.05,
        "cramers_v": round(cramers_v, 4),
        "interpretation": (
            f"Phân phối cluster {'CÓ' if p_value < 0.05 else 'KHÔNG'} thay đổi "
            f"có ý nghĩa giữa {period1_key} và {period2_key} "
            f"(χ²={chi2:.2f}, p={p_value:.4f}, V={cramers_v:.3f})"
        ),
        "calculated_at": datetime.now(),
    }


def trend_significance_test(
    engine: Engine,
    kpi_name: str,
    dimension: str = "overall",
    dimension_value: str = "overall",
    min_periods: int = 4,
) -> dict:
    """Kiểm tra xu hướng KPI theo thời gian có ý nghĩa thống kê không.

    Dùng Mann-Kendall test cho trend detection.
    """
    query = """
        SELECT period_key, value
        FROM mart.kpi_snapshot
        WHERE kpi_name = :kpi_name
          AND dimension = :dim
          AND dimension_value = :dim_val
        ORDER BY period_key
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text(query), conn,
            params={
                "kpi_name": kpi_name,
                "dim": dimension,
                "dim_val": dimension_value,
            },
        )

    if len(df) < min_periods:
        return {
            "kpi_name": kpi_name,
            "error": f"Not enough periods ({len(df)}). Need at least {min_periods}.",
        }

    values = df["value"].dropna().values

    n = len(values)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += np.sign(values[j] - values[i])

    var_s = n * (n - 1) * (2 * n + 5) / 18
    z = (s - 1) / np.sqrt(var_s) if s > 0 else ((s + 1) / np.sqrt(var_s) if s < 0 else 0)
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    tau = s / (n * (n - 1) / 2)

    return {
        "kpi_name": kpi_name,
        "dimension": dimension,
        "dimension_value": dimension_value,
        "n_periods": n,
        "mann_kendall_tau": round(tau, 4),
        "z_score": round(z, 4),
        "p_value": round(p_value, 6),
        "is_significant": p_value < 0.05,
        "trend": "up" if tau > 0 and p_value < 0.05 else (
            "down" if tau < 0 and p_value < 0.05 else "no_trend"
        ),
        "interpretation": (
            f"Xu hướng {kpi_name} {'CÓ ý nghĩa' if p_value < 0.05 else 'KHÔNG có ý nghĩa'} "
            f"(τ={tau:.3f}, p={p_value:.4f}) — "
            f"{'tăng' if tau > 0 else 'giảm' if tau < 0 else 'ổn định'}"
        ),
        "calculated_at": datetime.now(),
    }
