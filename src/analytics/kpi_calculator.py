import logging
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


KPI_DEFINITIONS = {
    "revenue": {
        "query": """
            SELECT COALESCE(SUM(f.line_total), 0) AS value
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
        """,
    },
    "gross_profit": {
        "query": """
            SELECT COALESCE(SUM(f.gross_profit), 0) AS value
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
        """,
    },
    "gross_margin_pct": {
        "query": """
            SELECT CASE
                WHEN SUM(f.line_total) = 0 THEN 0
                ELSE SUM(f.gross_profit) * 100.0 / SUM(f.line_total)
            END AS value
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
        """,
    },
    "order_count": {
        "query": """
            SELECT COUNT(DISTINCT f.sales_order_id) AS value
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
        """,
    },
    "total_customers": {
        "query": """
            SELECT COUNT(DISTINCT f.customer_key) AS value
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
        """,
    },
    "revenue_per_order": {
        "query": """
            SELECT CASE
                WHEN COUNT(DISTINCT f.sales_order_id) = 0 THEN 0
                ELSE SUM(f.line_total) / COUNT(DISTINCT f.sales_order_id)
            END AS value
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
        """,
    },
    "revenue_per_customer": {
        "query": """
            SELECT CASE
                WHEN COUNT(DISTINCT f.customer_key) = 0 THEN 0
                ELSE SUM(f.line_total) / COUNT(DISTINCT f.customer_key)
            END AS value
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            WHERE d.date BETWEEN :start_date AND :end_date
        """,
    },
    "inventory_turnover": {
        "query": """
            WITH sales_cogs AS (
                SELECT COALESCE(SUM(f.standard_cost * f.order_qty), 0) AS total_cogs
                FROM dw.fact_sales f
                JOIN dw.dim_date d ON f.date_key = d.date_key
                WHERE d.date BETWEEN :start_date AND :end_date
            ),
            avg_inventory AS (
                SELECT COALESCE(AVG(i.quantity * p.standard_cost), 0) AS avg_inv_value
                FROM dw.fact_inventory i
                JOIN dw.dim_date d ON i.date_key = d.date_key
                JOIN dw.dim_product p ON i.product_key = p.product_key
                    AND p.valid_from::date <= d.date
                    AND (p.valid_to IS NULL OR p.valid_to::date > d.date)
                WHERE d.date BETWEEN :start_date AND :end_date
            )
            SELECT CASE
                WHEN (SELECT avg_inv_value FROM avg_inventory) = 0 THEN 0
                ELSE (SELECT total_cogs FROM sales_cogs) / (SELECT avg_inv_value FROM avg_inventory)
            END AS value
        """,
    },
    "repeat_customer_rate": {
        "query": """
            WITH period_customers AS (
                SELECT DISTINCT f.customer_key
                FROM dw.fact_sales f
                JOIN dw.dim_date d ON f.date_key = d.date_key
                WHERE d.date BETWEEN :start_date AND :end_date
            ),
            lookback_start AS (
                SELECT (CAST(:start_date AS date) - INTERVAL '12 months')::date AS lb_date
            ),
            previous_customers AS (
                SELECT DISTINCT f.customer_key
                FROM dw.fact_sales f
                JOIN dw.dim_date d ON f.date_key = d.date_key
                CROSS JOIN lookback_start ls
                WHERE d.date >= ls.lb_date AND d.date < CAST(:start_date AS date)
            )
            SELECT CASE
                WHEN (SELECT COUNT(*) FROM period_customers) = 0 THEN 0
                ELSE (
                    SELECT COUNT(*) * 100.0 / (SELECT COUNT(*) FROM period_customers)
                    FROM period_customers pc
                    WHERE EXISTS (
                        SELECT 1 FROM previous_customers prev
                        WHERE prev.customer_key = pc.customer_key
                    )
                )
            END AS value
        """,
    },
    "hhi_revenue_concentration": {
        "query": """
            WITH category_revenue AS (
                SELECT p.category, SUM(f.line_total) AS revenue
                FROM dw.fact_sales f
                JOIN dw.dim_date d ON f.date_key = d.date_key
                JOIN dw.dim_product p ON f.product_key = p.product_key
                WHERE d.date BETWEEN :start_date AND :end_date
                    AND p.category IS NOT NULL
                GROUP BY p.category
        ),
        total_revenue AS (
            SELECT SUM(revenue) AS total FROM category_revenue
        )
        SELECT CASE
            WHEN (SELECT total FROM total_revenue) = 0 THEN 0
            ELSE (
                SELECT SUM((revenue / (SELECT total FROM total_revenue)) *
                           (revenue / (SELECT total FROM total_revenue)))
                FROM category_revenue
            )
        END AS value
    """,
    },
}


DIMENSION_KPIS = {
    "revenue_by_territory": {
        "dimension": "territory",
        "query": """
            SELECT t.territory_name AS dimension_value,
                   COALESCE(SUM(f.line_total), 0) AS value,
                   COUNT(DISTINCT f.sales_order_detail_id) AS row_count
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            JOIN dw.dim_territory t ON f.territory_key = t.territory_key
            WHERE d.date BETWEEN :start_date AND :end_date
            GROUP BY t.territory_name
        """,
    },
    "revenue_by_category": {
        "dimension": "category",
        "query": """
            SELECT p.category AS dimension_value,
                   COALESCE(SUM(f.line_total), 0) AS value,
                   COUNT(DISTINCT f.sales_order_detail_id) AS row_count
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            JOIN dw.dim_product p ON f.product_key = p.product_key
            WHERE d.date BETWEEN :start_date AND :end_date
                AND p.category IS NOT NULL
            GROUP BY p.category
        """,
    },
    "margin_by_category": {
        "dimension": "category",
        "query": """
            SELECT p.category AS dimension_value,
                   CASE
                       WHEN SUM(f.line_total) = 0 THEN 0
                       ELSE SUM(f.gross_profit) * 100.0 / SUM(f.line_total)
                   END AS value,
                   COUNT(DISTINCT f.sales_order_detail_id) AS row_count
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            JOIN dw.dim_product p ON f.product_key = p.product_key
            WHERE d.date BETWEEN :start_date AND :end_date
                AND p.category IS NOT NULL
            GROUP BY p.category
        """,
    },
    "revenue_by_customer_type": {
        "dimension": "customer_type",
        "query": """
            SELECT c.customer_type AS dimension_value,
                   COALESCE(SUM(f.line_total), 0) AS value,
                   COUNT(DISTINCT f.sales_order_detail_id) AS row_count
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            JOIN dw.dim_customer c ON f.customer_key = c.customer_key
            WHERE d.date BETWEEN :start_date AND :end_date
            GROUP BY c.customer_type
        """,
    },
    "inventory_turnover_by_category": {
        "dimension": "category",
        "query": """
            WITH sales_cogs AS (
                SELECT p.category,
                       COALESCE(SUM(f.standard_cost * f.order_qty), 0) AS total_cogs
                FROM dw.fact_sales f
                JOIN dw.dim_date d ON f.date_key = d.date_key
                JOIN dw.dim_product p ON f.product_key = p.product_key
                WHERE d.date BETWEEN :start_date AND :end_date
                GROUP BY p.category
            ),
            avg_inventory AS (
                SELECT p.category,
                       COALESCE(AVG(i.quantity * p.standard_cost), 0) AS avg_inv_value
                FROM dw.fact_inventory i
                JOIN dw.dim_date d ON i.date_key = d.date_key
                JOIN dw.dim_product p ON i.product_key = p.product_key
                    AND p.valid_from::date <= d.date
                    AND (p.valid_to IS NULL OR p.valid_to::date > d.date)
                WHERE d.date BETWEEN :start_date AND :end_date
                GROUP BY p.category
            )
            SELECT sc.category AS dimension_value,
                   CASE WHEN ai.avg_inv_value = 0 THEN 0
                        ELSE sc.total_cogs / ai.avg_inv_value
                   END AS value,
                   0 AS row_count
            FROM sales_cogs sc
            JOIN avg_inventory ai ON sc.category = ai.category
        """,
    },
    "revenue_by_product": {
        "dimension": "product",
        "query": """
            SELECT p.name AS dimension_value,
                   COALESCE(SUM(f.line_total), 0) AS value,
                   COUNT(DISTINCT f.sales_order_detail_id) AS row_count
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            JOIN dw.dim_product p ON f.product_key = p.product_key
            WHERE d.date BETWEEN :start_date AND :end_date
                AND p.category IS NOT NULL
            GROUP BY p.name
            ORDER BY value DESC
        """,
    },
    "repeat_rate_by_customer_type": {
        "dimension": "customer_type",
        "query": """
            WITH period_customers AS (
                SELECT DISTINCT f.customer_key, c.customer_type
                FROM dw.fact_sales f
                JOIN dw.dim_date d ON f.date_key = d.date_key
                JOIN dw.dim_customer c ON f.customer_key = c.customer_key
                WHERE d.date BETWEEN :start_date AND :end_date
            ),
            lookback_start AS (
                SELECT (CAST(:start_date AS date) - INTERVAL '12 months')::date AS lb_date
            ),
            previous_customers AS (
                SELECT DISTINCT f.customer_key
                FROM dw.fact_sales f
                JOIN dw.dim_date d ON f.date_key = d.date_key
                CROSS JOIN lookback_start ls
                WHERE d.date >= ls.lb_date AND d.date < CAST(:start_date AS date)
            ),
            by_type AS (
                SELECT pc.customer_type,
                       COUNT(*) AS total_customers,
                       SUM(CASE WHEN prev.customer_key IS NOT NULL THEN 1 ELSE 0 END) AS retained
                FROM period_customers pc
                LEFT JOIN previous_customers prev ON pc.customer_key = prev.customer_key
                GROUP BY pc.customer_type
            )
            SELECT customer_type AS dimension_value,
                   CASE WHEN total_customers = 0 THEN 0
                        ELSE retained * 100.0 / total_customers
                   END AS value,
                   0 AS row_count
            FROM by_type
        """,
    },
}


def calculate_kpi(
    engine: Engine,
    kpi_name: str,
    start_date: str,
    end_date: str,
    dimension: str | None = None,
) -> pd.DataFrame:
    if dimension:
        if kpi_name not in DIMENSION_KPIS:
            raise ValueError(f"Dimension KPI '{kpi_name}' not found")
        kpi_def = DIMENSION_KPIS[kpi_name]
    else:
        if kpi_name not in KPI_DEFINITIONS:
            raise ValueError(f"KPI '{kpi_name}' not found")
        kpi_def = KPI_DEFINITIONS[kpi_name]

    with engine.connect() as conn:
        df = pd.read_sql(
            text(kpi_def["query"]),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )

    if dimension:
        df["dimension"] = dimension
        df["kpi_name"] = kpi_name
    else:
        df["dimension"] = "overall"
        df["dimension_value"] = "overall"
        df["kpi_name"] = kpi_name
        df["row_count"] = 0

    return df


def calculate_all_kpis(
    engine: Engine,
    start_date: str,
    end_date: str,
) -> list[dict]:
    results = []
    for kpi_name in KPI_DEFINITIONS:
        df = calculate_kpi(engine, kpi_name, start_date, end_date)
        row = df.iloc[0].to_dict()
        row["period_start"] = start_date
        row["period_end"] = end_date
        results.append(row)

    for kpi_name in DIMENSION_KPIS:
        dim = DIMENSION_KPIS[kpi_name]["dimension"]
        df = calculate_kpi(engine, kpi_name, start_date, end_date, dimension=dim)
        for _, row in df.iterrows():
            r = row.to_dict()
            r["period_start"] = start_date
            r["period_end"] = end_date
            results.append(r)

    return results


def get_quarter_boundaries(year: int, quarter: int) -> tuple[str, str]:
    quarters = {
        1: (f"{year}-01-01", f"{year}-03-31"),
        2: (f"{year}-04-01", f"{year}-06-30"),
        3: (f"{year}-07-01", f"{year}-09-30"),
        4: (f"{year}-10-01", f"{year}-12-31"),
    }
    return quarters[quarter]


def get_year_boundaries(year: int) -> tuple[str, str]:
    return (f"{year}-01-01", f"{year}-12-31")


def get_period_key(period_type: str, year: int, quarter: int | None = None) -> str:
    if period_type == "Y":
        return str(year)
    elif period_type == "Q":
        return f"{year}Q{quarter}"
    elif period_type == "M":
        return f"{year}{quarter:02d}"
    return str(year)
