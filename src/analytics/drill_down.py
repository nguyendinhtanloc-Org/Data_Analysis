"""Drill-down Diagnosis - Đi sâu từng lớp để tìm nguyên nhân gốc rễ.

Hierarchy:
  KPI tổng thể
    → Theo Category (Bikes, Clothing, Accessories)
      → Theo Subcategory (Road Bikes, Mountain Bikes, ...)
        → Theo Sản phẩm (Sport-100, ...)
          → Theo khu vực / khách hàng

Mỗi cấp đều tính được:
  - abs_change: chênh lệch tuyệt đối
  - pct_change: chênh lệch %
  - contribution: đóng góp vào thay đổi tổng thể
  - is_driver: True nếu contribution > threshold
"""
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.analytics.contribution import (
    _get_dimension_kpi,
    save_period_comparison,
)

logger = logging.getLogger(__name__)

DRILL_DOWN_HIERARCHY = {
    "overall": [
        "category",
        "territory",
        "customer_type",
    ],
    "category": ["subcategory"],
    "subcategory": ["product"],
    "territory": ["country"],
}


def drill_down(
    engine: Engine,
    kpi_name: str,
    curr_start: str,
    curr_end: str,
    prev_start: str,
    prev_end: str,
    dimension: str = "category",
    filter_value: Optional[str] = None,
    contribution_threshold: float = 5.0,
    max_depth: int = 3,
) -> list[dict]:
    """Drill-down từ dimension hiện tại xuống các cấp con.

    Args:
        engine: SQLAlchemy engine.
        kpi_name: Tên KPI.
        curr_start, curr_end: Kỳ hiện tại.
        prev_start, prev_end: Kỳ trước.
        dimension: Dimension hiện tại ('overall', 'category', ...).
        filter_value: Giá trị cần drill xuống (vd: 'Clothing').
        contribution_threshold: Ngưỡng % để đánh dấu là driver.
        max_depth: Số cấp tối đa.

    Returns:
        list[dict]: Chuỗi drill-down, mỗi phần tử là 1 cấp.
    """
    results = []
    _drill_down_recursive(
        engine, kpi_name, curr_start, curr_end, prev_start, prev_end,
        dimension, filter_value, contribution_threshold, max_depth,
        0, results,
    )
    return results


def _drill_down_recursive(
    engine: Engine,
    kpi_name: str,
    curr_start: str,
    curr_end: str,
    prev_start: str,
    prev_end: str,
    dimension: str,
    filter_value: Optional[str],
    threshold: float,
    max_depth: int,
    depth: int,
    results: list,
) -> None:
    if depth >= max_depth:
        return

    children = _get_children(engine, kpi_name, curr_start, curr_end, prev_start, prev_end, dimension, filter_value)

    if children is None or children.empty:
        return

    for _, child in children.iterrows():
        entry = {
            "level": depth,
            "dimension": dimension,
            "dimension_value": child.get("dimension_value", filter_value),
            "curr_value": float(child["value_curr"]),
            "prev_value": float(child["value_prev"]),
            "abs_change": float(child["abs_change"]),
            "pct_change": round(float(child["pct_change"]), 2),
            "contribution_pct": round(float(child["contribution_pct"]), 2),
            "is_driver": abs(float(child["contribution_pct"])) >= threshold,
            "calculated_at": datetime.now(),
        }
        results.append(entry)

        top_drivers = children[abs(children["contribution_pct"]) >= threshold]

        next_dim = DRILL_DOWN_HIERARCHY.get(dimension)
        if next_dim and len(next_dim) > 0:
            next_dim_name = next_dim[0] if isinstance(next_dim, list) else next_dim
        else:
            continue

        for _, driver in top_drivers.iterrows():
            _drill_down_recursive(
                engine, kpi_name, curr_start, curr_end, prev_start, prev_end,
                next_dim_name, driver["dimension_value"], threshold, max_depth,
                depth + 1, results,
            )


def _get_children(
    engine: Engine,
    kpi_name: str,
    curr_start: str,
    curr_end: str,
    prev_start: str,
    prev_end: str,
    dimension: str,
    filter_value: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    dim_col, join_table, join_cond = _get_drill_info(dimension, filter_value)

    if dim_col is None:
        return None

    def build_query(select_expr: str) -> str:
        where_clause = f"AND d.date BETWEEN :start_date AND :end_date"
        filter_clause = ""
        if filter_value and dimension != "overall":
            parts = filter_value.replace("'", "''")
            filter_clause = f"AND {_get_filter_col(dimension)} = '{parts}'"

        return f"""
            SELECT {dim_col} AS dimension_value,
                   {select_expr} AS value
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            JOIN {join_table} ON {join_cond}
            WHERE 1=1 {where_clause} {filter_clause}
            GROUP BY {dim_col}
        """

    if kpi_name == "revenue":
        select = "COALESCE(SUM(f.line_total), 0)"
    elif kpi_name == "gross_margin_pct":
        select = """
            CASE WHEN SUM(f.line_total) = 0 THEN 0
                 ELSE SUM(f.gross_profit) * 100.0 / SUM(f.line_total)
            END
        """
    else:
        select = "COALESCE(SUM(f.line_total), 0)"

    curr_query = build_query(select)
    prev_query = build_query(select)

    with engine.connect() as conn:
        curr_df = pd.read_sql(
            text(curr_query), conn,
            params={"start_date": curr_start, "end_date": curr_end},
        )
        prev_df = pd.read_sql(
            text(prev_query), conn,
            params={"start_date": prev_start, "end_date": prev_end},
        )

    if curr_df.empty and prev_df.empty:
        return None

    merged = pd.merge(
        curr_df, prev_df,
        on="dimension_value", how="outer", suffixes=("_curr", "_prev"),
    ).fillna(0)

    total_curr = merged["value_curr"].sum()
    total_prev = merged["value_prev"].sum()

    if total_prev == 0:
        return None

    merged["abs_change"] = merged["value_curr"] - merged["value_prev"]
    merged["pct_change"] = (
        (merged["abs_change"] / merged["value_prev"].replace(0, float("inf"))) * 100
    )
    total_change = total_curr - total_prev
    merged["contribution_pct"] = (
        (merged["abs_change"] / abs(total_change) * 100)
        if total_change != 0 else 0
    )

    return merged.sort_values("contribution_pct", ascending=False)


def _get_drill_info(dimension: str, filter_value: Optional[str] = None) -> tuple:
    mapping = {
        "overall": (
            "'overall'",
            "dw.dim_product p",
            "f.product_key = p.product_key AND p.is_current = true",
        ),
        "category": (
            "p.category",
            "dw.dim_product p",
            "f.product_key = p.product_key AND p.is_current = true",
        ),
        "subcategory": (
            "p.subcategory",
            "dw.dim_product p",
            "f.product_key = p.product_key AND p.is_current = true",
        ),
        "product": (
            "p.name",
            "dw.dim_product p",
            "f.product_key = p.product_key AND p.is_current = true",
        ),
        "territory": (
            "t.territory_name",
            "dw.dim_territory t",
            "f.territory_key = t.territory_key",
        ),
        "country": (
            "t.country_region",
            "dw.dim_territory t",
            "f.territory_key = t.territory_key",
        ),
        "customer_type": (
            "c.customer_type",
            "dw.dim_customer c",
            "f.customer_key = c.customer_key",
        ),
    }
    return mapping.get(dimension, (None, None, None))


def _get_filter_col(dimension: str) -> str:
    mapping = {
        "category": "p.category",
        "subcategory": "p.subcategory",
        "product": "p.name",
        "territory": "t.territory_name",
        "country": "t.country_region",
        "customer_type": "c.customer_type",
    }
    return mapping.get(dimension, "1=1")
