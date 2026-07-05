"""Contribution Analysis - Phân rã đóng góp để truy tìm nguyên nhân.

Khi một KPI thay đổi giữa 2 kỳ, module này phân rã sự thay đổi
theo các dimension để xác định "ai là thủ phạm chính".

Công thức:
  ΔKPI = Σ(weight_i × Δrate_i) + Σ(Δweight_i × rate_avg_i)

  Trong đó:
    - weight_i: tỷ trọng của dimension value i trong kỳ hiện tại
    - Δrate_i: chênh lệch rate của dimension value i
    - Δweight_i: chênh lệch tỷ trọng
    - rate_avg_i: rate trung bình 2 kỳ
"""
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def contribution_breakdown(
    engine: Engine,
    kpi_name: str,
    curr_start: str,
    curr_end: str,
    prev_start: str,
    prev_end: str,
    dimension: str = "category",
) -> list[dict]:
    """Phân rã đóng góp của từng dimension value vào sự thay đổi KPI.

    Args:
        engine: SQLAlchemy engine.
        kpi_name: Tên KPI cần phân tích ('revenue', 'gross_margin_pct', ...).
        curr_start, curr_end: Biên thời gian kỳ hiện tại.
        prev_start, prev_end: Biên thời gian kỳ trước.
        dimension: Dimension để phân rã ('category', 'territory', 'customer_type').

    Returns:
        list[dict]: Mỗi phần tử là đóng góp của 1 dimension value.
    """
    dim_col, join_table, join_cond = _get_dimension_info(dimension)

    curr_data = _get_dimension_kpi(engine, kpi_name, curr_start, curr_end, dim_col, join_table, join_cond)
    prev_data = _get_dimension_kpi(engine, kpi_name, prev_start, prev_end, dim_col, join_table, join_cond)

    merged = pd.merge(
        curr_data, prev_data,
        on="dimension_value", how="outer", suffixes=("_curr", "_prev"),
    ).fillna(0)

    total_curr = merged["value_curr"].sum()
    total_prev = merged["value_prev"].sum()

    if total_prev == 0:
        logger.warning("Kỳ trước có total = 0, không thể tính contribution %")
        return []

    merged["weight_curr"] = merged["value_curr"] / total_curr if total_curr > 0 else 0
    merged["weight_prev"] = merged["value_prev"] / total_prev if total_prev > 0 else 0
    merged["rate_curr"] = merged["value_curr"]
    merged["rate_prev"] = merged["value_prev"]
    merged["abs_change"] = merged["value_curr"] - merged["value_prev"]
    merged["pct_change"] = (merged["abs_change"] / merged["value_prev"].replace(0, float("inf"))) * 100

    total_change = total_curr - total_prev
    merged["contribution_abs"] = merged["abs_change"]
    merged["contribution_pct"] = (merged["abs_change"] / abs(total_change) * 100) if total_change != 0 else 0

    # Mix-shift detection: Simpson's Paradox check
    # Nếu tổng thể thay đổi ngược dấu với hầu hết dimension values → mix-shift
    direction_overall = "up" if total_change >= 0 else "down"
    directions = merged["pct_change"].apply(lambda x: "up" if x >= 0 else "down")
    majority_direction = directions.mode().iloc[0] if not directions.empty else direction_overall
    mix_shift_warning = (majority_direction != direction_overall)

    merged = merged.sort_values("contribution_pct", ascending=False)

    results = []
    for _, row in merged.iterrows():
        results.append({
            "kpi_name": kpi_name,
            "curr_period_key": f"{curr_start[:4]}Q{(int(curr_start[5:7])-1)//3+1}",
            "prev_period_key": f"{prev_start[:4]}Q{(int(prev_start[5:7])-1)//3+1}",
            "dimension": dimension,
            "dimension_value": row["dimension_value"],
            "curr_value": float(row["value_curr"]),
            "prev_value": float(row["value_prev"]),
            "abs_change": float(row["abs_change"]),
            "pct_change": round(float(row["pct_change"]), 2) if row["pct_change"] != float("inf") else None,
            "contribution_pct": round(float(row["contribution_pct"]), 2),
            "total_change_pct": round(float(total_change / total_prev * 100), 2) if total_prev != 0 else 0,
            "mix_shift_warning": mix_shift_warning,
            "calculated_at": datetime.now(),
        })

    return results


def _get_dimension_info(dimension: str) -> tuple:
    mapping = {
        "category": ("p.category", "dw.dim_product p",
                      "f.product_key = p.product_key AND p.is_current = true"),
        "territory": ("t.territory_name", "dw.dim_territory t",
                      "f.territory_key = t.territory_key"),
        "customer_type": ("c.customer_type", "dw.dim_customer c",
                          "f.customer_key = c.customer_key"),
    }
    if dimension not in mapping:
        raise ValueError(f"Dimension '{dimension}' not supported. Use: {list(mapping.keys())}")
    return mapping[dimension]


def _get_dimension_kpi(
    engine: Engine,
    kpi_name: str,
    start_date: str,
    end_date: str,
    dim_col: str,
    join_table: str,
    join_cond: str,
) -> pd.DataFrame:
    if kpi_name == "revenue":
        select_expr = f"COALESCE(SUM(f.line_total), 0)"
    elif kpi_name == "gross_profit":
        select_expr = f"COALESCE(SUM(f.gross_profit), 0)"
    elif kpi_name == "gross_margin_pct":
        select_expr = f"""
            CASE WHEN SUM(f.line_total) = 0 THEN 0
                 ELSE SUM(f.gross_profit) * 100.0 / SUM(f.line_total)
            END
        """
    elif kpi_name == "order_count":
        select_expr = f"COUNT(DISTINCT f.sales_order_id)"
    else:
        select_expr = f"COALESCE(SUM(f.line_total), 0)"

    query = f"""
        SELECT {dim_col} AS dimension_value,
               {select_expr} AS value
        FROM dw.fact_sales f
        JOIN dw.dim_date d ON f.date_key = d.date_key
        JOIN {join_table} ON {join_cond}
        WHERE d.date BETWEEN :start_date AND :end_date
        GROUP BY {dim_col}
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text(query),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )
    return df


def save_period_comparison(engine: Engine, results: list[dict]) -> int:
    """Lưu kết quả period comparison vào mart.period_comparison."""
    if not results:
        return 0

    with engine.begin() as conn:
        for r in results:
            conn.execute(
                text("""
                    INSERT INTO mart.period_comparison
                        (kpi_name, curr_period_key, prev_period_key,
                         dimension, dimension_value,
                         curr_value, prev_value, abs_change, pct_change,
                         contribution_pct, calculated_at)
                    VALUES
                        (:kpi_name, :curr_period_key, :prev_period_key,
                         :dimension, :dimension_value,
                         :curr_value, :prev_value, :abs_change, :pct_change,
                         :contribution_pct, :calculated_at)
                    ON CONFLICT (kpi_name, curr_period_key, prev_period_key, dimension, dimension_value)
                    DO UPDATE SET
                        curr_value = EXCLUDED.curr_value,
                        prev_value = EXCLUDED.prev_value,
                        abs_change = EXCLUDED.abs_change,
                        pct_change = EXCLUDED.pct_change,
                        contribution_pct = EXCLUDED.contribution_pct,
                        calculated_at = EXCLUDED.calculated_at
                """),
                r,
            )
    return len(results)
