"""Causal Inference Module - Suy luận nhân quả.

Các phương pháp:
  1. Difference-in-Differences (DiD):
     So sánh treatment group vs control group trước/sau intervention.
     VD: Chiến dịch discount có thực sự làm tăng doanh thu?

  2. Granger Causality Test:
     Kiểm tra "liệu X có phải nguyên nhân gây ra Y" trên chuỗi thời gian.
     VD: "Tồn kho tăng có gây ra giảm doanh thu?" hay ngược lại.

  3. Price Elasticity:
     Tính Price Elasticity of Demand (PED) dùng log-log regression.
"""
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from scipy import stats

logger = logging.getLogger(__name__)


def difference_in_differences(
    engine: Engine,
    treatment_category: str,
    control_category: str,
    intervention_date: str,
    kpi: str = "revenue",
    pre_period_days: int = 90,
    post_period_days: int = 90,
) -> dict:
    """Difference-in-Differences analysis.

    Ví dụ: Discount trên 'Clothing' (treatment) có thực sự làm tăng doanh thu
    so với 'Accessories' (control) không?
    """
    select_val = {
        "revenue": "COALESCE(SUM(f.line_total), 0)",
        "gross_profit": "COALESCE(SUM(f.gross_profit), 0)",
        "order_count": "COUNT(DISTINCT f.sales_order_detail_id)",
    }.get(kpi, "COALESCE(SUM(f.line_total), 0)")

    base_query = f"""
        SELECT d.date, {select_val} AS value, p.category
        FROM dw.fact_sales f
        JOIN dw.dim_date d ON f.date_key = d.date_key
        JOIN dw.dim_product p ON f.product_key = p.product_key AND p.is_current = true
        WHERE p.category IN (:cat1, :cat2)
          AND d.date BETWEEN :start_date AND :end_date
        GROUP BY d.date, p.category
        ORDER BY d.date
    """

    int_date = pd.Timestamp(intervention_date)
    start_all = int_date - pd.Timedelta(days=pre_period_days)
    end_all = int_date + pd.Timedelta(days=post_period_days)

    with engine.connect() as conn:
        df = pd.read_sql(
            text(base_query),
            conn,
            params={
                "cat1": treatment_category,
                "cat2": control_category,
                "start_date": start_all,
                "end_date": end_all,
            },
        )

    df_treat = df[df["category"] == treatment_category].copy()
    df_control = df[df["category"] == control_category].copy()

    def avg_period(d, start_dt, mid_dt, end_dt):
        pre = d[(d["date"] >= start_dt) & (d["date"] < mid_dt)]["value"].mean()
        post = d[(d["date"] >= mid_dt) & (d["date"] <= end_dt)]["value"].mean()
        return pre or 0, post or 0

    treat_pre, treat_post = avg_period(df_treat, start_all, int_date, end_all)
    control_pre, control_post = avg_period(df_control, start_all, int_date, end_all)

    delta_treat = treat_post - treat_pre
    delta_control = control_post - control_pre
    did_estimate = delta_treat - delta_control

    treat_change = ((treat_post - treat_pre) / treat_pre * 100) if treat_pre > 0 else 0
    control_change = ((control_post - control_pre) / control_pre * 100) if control_pre > 0 else 0

    n = min(len(df_treat), len(df_control))
    t_stat, p_value = stats.ttest_ind(
        df_treat[df_treat["date"] >= int_date]["value"].fillna(0),
        df_control[df_control["date"] >= int_date]["value"].fillna(0),
        alternative="two-sided",
    ) if n > 1 else (0, 1.0)

    std_err = np.sqrt(
        np.var(df_treat["value"].fillna(0)) / max(len(df_treat), 1)
        + np.var(df_control["value"].fillna(0)) / max(len(df_control), 1)
    )
    ci_lower = did_estimate - 1.96 * std_err
    ci_upper = did_estimate + 1.96 * std_err

    return {
        "treatment": treatment_category,
        "control": control_category,
        "kpi": kpi,
        "intervention_date": intervention_date,
        "treatment_pre_avg": round(treat_pre, 2),
        "treatment_post_avg": round(treat_post, 2),
        "treatment_change_pct": round(treat_change, 2),
        "control_pre_avg": round(control_pre, 2),
        "control_post_avg": round(control_post, 2),
        "control_change_pct": round(control_change, 2),
        "did_estimate": round(did_estimate, 2),
        "p_value": round(p_value, 6),
        "is_significant": p_value < 0.05,
        "ci_lower": round(ci_lower, 2),
        "ci_upper": round(ci_upper, 2),
        "effect_size": round(did_estimate / std_err, 4) if std_err > 0 else 0,
        "interpretation": _interpret_did(did_estimate, p_value, kpi, treatment_category),
        "calculated_at": datetime.now(),
    }


def _interpret_did(did_estimate: float, p_value: float, kpi: str, treatment: str) -> str:
    if p_value >= 0.05:
        return (f"Không có bằng chứng thống kê (p={p_value:.3f}) cho thấy "
                f"intervention trên {treatment} có tác động đến {kpi}")
    direction = "tăng" if did_estimate > 0 else "giảm"
    magnitude = "mạnh" if abs(did_estimate) > 10000 else (
        "trung bình" if abs(did_estimate) > 1000 else "nhẹ"
    )
    return (f"Có bằng chứng thống kê (p={p_value:.3f}) cho thấy intervention "
            f"trên {treatment} làm {direction} {kpi} ở mức {magnitude} "
            f"(DID estimate = {did_estimate:+.2f})")


def price_elasticity(
    engine: Engine,
    category: str | None = None,
    period: str = "monthly",
) -> dict:
    """Tính Price Elasticity of Demand (PED) dùng log-log regression.

    PED = %ΔQ / %ΔP, với log-log: ln(Q) = α + β * ln(P)
    """
    interval = "month" if period == "monthly" else "quarter"
    date_trunc = f"DATE_TRUNC('{interval}', d.date)"

    cat_filter = ""
    if category:
        cat_filter = f"AND p.category = '{category}'"

    query = f"""
        SELECT {date_trunc} AS period,
               AVG(f.unit_price) AS avg_price,
               SUM(f.order_qty) AS total_qty
        FROM dw.fact_sales f
        JOIN dw.dim_date d ON f.date_key = d.date_key
        JOIN dw.dim_product p ON f.product_key = p.product_key AND p.is_current = true
        WHERE f.unit_price > 0 AND f.order_qty > 0 {cat_filter}
        GROUP BY period
        HAVING SUM(f.order_qty) > 0
        ORDER BY period
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) < 5:
        return {"error": f"Not enough data ({len(df)} periods). Need at least 5."}

    df["ln_price"] = np.log(df["avg_price"])
    df["ln_qty"] = np.log(df["total_qty"])

    slope, intercept, r_value, p_value, std_err = stats.linregress(df["ln_price"], df["ln_qty"])

    category_label = category if category else "overall"
    elasticity_type = "elastic" if abs(slope) > 1 else (
        "inelastic" if abs(slope) < 1 else "unit elastic"
    )

    reliability = "cao" if (p_value < 0.05 and r_value**2 > 0.5) else (
        "thấp — dữ liệu không đủ biến động giá để ước lượng tin cậy" if p_value >= 0.05 else "trung bình"
    )

    return {
        "category": category_label,
        "elasticity": round(slope, 4),
        "r_squared": round(r_value ** 2, 4),
        "p_value": round(p_value, 6),
        "std_err": round(std_err, 4),
        "is_significant": p_value < 0.05,
        "elasticity_type": elasticity_type,
        "reliability": reliability,
        "interpretation": (
            f"Price Elasticity of Demand = {slope:.4f} ({elasticity_type}). "
            f"Giá tăng 1% → Demand {'giảm' if slope < 0 else 'tăng'} {abs(slope):.2f}% "
            f"(R²={r_value**2:.3f}, p={p_value:.4f}, độ tin cậy: {reliability})"
        ),
        "n_periods": len(df),
        "calculated_at": datetime.now(),
    }
