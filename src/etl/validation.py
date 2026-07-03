"""Validation module - Kiểm tra dữ liệu 3 lớp.

Lớp 1 - Pre-load:
  - Row count sau Extract > 0 (trừ incremental có thể 0 nếu không có data mới)
  - Các cột bắt buộc không được rỗng hoàn toàn

Lớp 2 - Post-load:
  - Orphan record check (FK không tồn tại trong Dim)
  - Row count staging vs DWH khớp
  - Null ở cột FK trong Fact phải = 0

Lớp 3 - Cross-check:
  - SUM(line_total) DWH vs OLTP khớp 100%
  - COUNT(sales_order_detail_id) khớp 100%
"""
import logging

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)


# ===========================================================================
# Lớp 1: Pre-load Validation
# ===========================================================================

def check_missing_values(df: pd.DataFrame, columns: list) -> bool:
    """
    Kiểm tra xem các cột chỉ định có giá trị null hay không.

    Args:
        df: Dữ liệu cần kiểm tra.
        columns: Danh sách các cột cần kiểm tra.

    Returns:
        bool: True nếu hợp lệ (không có null), False nếu có null.
    """
    valid = True
    for col in columns:
        if col not in df.columns:
            logger.warning(f"  [Pre-load] Cột '{col}' không tồn tại trong DataFrame.")
            valid = False
            continue
        null_count = df[col].isnull().sum()
        if null_count > 0:
            logger.warning(f"  [Pre-load] Cột '{col}' có {null_count} giá trị null.")
            valid = False
    return valid


def check_unique_constraints(df: pd.DataFrame, columns: list) -> bool:
    """
    Kiểm tra tính duy nhất của một hoặc một nhóm cột.

    Args:
        df: Dữ liệu cần kiểm tra.
        columns: Danh sách cột cần unique.

    Returns:
        bool: True nếu hợp lệ, False nếu có duplicate.
    """
    existing_cols = [c for c in columns if c in df.columns]
    if not existing_cols:
        return True
    dup_count = df.duplicated(subset=existing_cols).sum()
    if dup_count > 0:
        logger.warning(f"  [Pre-load] Phát hiện {dup_count} bản ghi trùng trên: {existing_cols}")
        return False
    return True


def validate_pre_load(
    data: dict[str, pd.DataFrame],
    allow_empty_incremental: bool = True,
) -> bool:
    """
    Lớp 1: Kiểm tra trước khi load.

    Args:
        data: Dict {'ten_bang': DataFrame}
        allow_empty_incremental: Nếu True, bảng rỗng là chấp nhận được (incremental không có data mới).

    Returns:
        bool: True nếu pass tất cả.
    """
    logger.info("=== Pre-load Validation ===")
    all_valid = True

    for name, df in data.items():
        if df is None or len(df) == 0:
            if allow_empty_incremental:
                logger.info(f"  [Pre-load] {name}: 0 rows (incremental - không có data mới, bỏ qua)")
                continue
            else:
                logger.error(f"  [Pre-load] FAIL: {name} trả về 0 bản ghi bất ngờ!")
                all_valid = False
            continue
        logger.info(f"  [Pre-load] {name}: {len(df):,} rows ✓")

    return all_valid


# ===========================================================================
# Lớp 2: Post-load Validation
# ===========================================================================

def validate_post_load(pg_engine: Engine, conn: Connection = None) -> bool:
    """
    Lớp 2: Kiểm tra sau khi load vào DWH.

    Kiểm tra:
    1. Null ở cột FK bắt buộc trong Fact_Sales
    2. Orphan FK (fact record không tìm được dim record tương ứng)
    3. Row count staging vs DWH (log để theo dõi)

    Args:
        pg_engine: SQLAlchemy engine kết nối PostgreSQL DWH.
        conn: Connection hiện tại (transaction). Nếu None, tạo connection mới.

    Returns:
        bool: True nếu pass tất cả.
    """
    logger.info("=== Post-load Validation ===")
    all_valid = True

    checks = [
        ("Fact_Sales: NULL date_key", "SELECT COUNT(*) FROM dw.fact_sales WHERE date_key IS NULL", 0, "eq"),
        ("Fact_Sales: NULL product_key", "SELECT COUNT(*) FROM dw.fact_sales WHERE product_key IS NULL", 0, "eq"),
        ("Fact_Sales: NULL customer_key", "SELECT COUNT(*) FROM dw.fact_sales WHERE customer_key IS NULL", 0, "eq"),
        ("Fact_Sales: NULL territory_key", "SELECT COUNT(*) FROM dw.fact_sales WHERE territory_key IS NULL", 0, "eq"),
        ("Fact_Sales: Orphan product_key",
         "SELECT COUNT(*) FROM dw.fact_sales f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product d WHERE d.product_key = f.product_key)", 0, "eq"),
        ("Fact_Sales: Orphan customer_key",
         "SELECT COUNT(*) FROM dw.fact_sales f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_customer d WHERE d.customer_key = f.customer_key)", 0, "eq"),
        ("Fact_Sales: Orphan territory_key",
         "SELECT COUNT(*) FROM dw.fact_sales f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_territory d WHERE d.territory_key = f.territory_key)", 0, "eq"),
        ("Fact_Sales: Orphan date_key",
         "SELECT COUNT(*) FROM dw.fact_sales f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_date d WHERE d.date_key = f.date_key)", 0, "eq"),
        ("Fact_Inventory: Orphan product_key",
         "SELECT COUNT(*) FROM dw.fact_inventory f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product d WHERE d.product_key = f.product_key)", 0, "eq"),
    ]

    if conn is None:
        conn = pg_engine.connect()
    for desc, query, expected, cmp in checks:
        try:
            result = conn.execute(text(query)).scalar()
            if cmp == "eq" and result == expected:
                logger.info(f"  [Post-load] {desc}: {result} ✓")
            else:
                logger.error(f"  [Post-load] FAIL: {desc}: {result} (expected {expected})")
                all_valid = False
        except Exception as e:
            logger.error(f"  [Post-load] Lỗi khi chạy check '{desc}': {e}")
            all_valid = False

    return all_valid


# ===========================================================================
# Lớp 3: Cross-check DWH vs OLTP
# ===========================================================================

def validate_cross_check(pg_engine: Engine, mssql_engine: Engine, conn: Connection = None) -> bool:
    """
    Lớp 3: So sánh aggregates giữa DWH (PostgreSQL) và OLTP (MSSQL).

    Kiểm tra:
    1. SUM(line_total) khớp 100%
    2. COUNT(sales_order_detail_id) khớp 100%

    Args:
        pg_engine: Engine PostgreSQL DWH.
        mssql_engine: Engine MSSQL OLTP.
        conn: Connection hiện tại (transaction). Nếu None, tạo connection mới.

    Returns:
        bool: True nếu pass tất cả.
    """
    logger.info("=== Cross-check Validation (DWH vs OLTP) ===")
    all_valid = True

    # Query DWH
    dwh_queries = {
        "count_sales": "SELECT COUNT(*) FROM dw.fact_sales",
        "sum_line_total": "SELECT COALESCE(SUM(line_total), 0) FROM dw.fact_sales",
        "sum_gross_profit": "SELECT COALESCE(SUM(gross_profit), 0) FROM dw.fact_sales",
        "count_by_year": """
            SELECT d.year, COUNT(f.sales_order_detail_id) as cnt
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            GROUP BY d.year ORDER BY d.year
        """,
    }

    # Query MSSQL
    oltp_queries = {
        "count_sales": """
            SELECT COUNT(sod.SalesOrderDetailID)
            FROM Sales.SalesOrderDetail sod
            INNER JOIN Sales.SalesOrderHeader soh ON sod.SalesOrderID = soh.SalesOrderID
            INNER JOIN Production.Product p ON sod.ProductID = p.ProductID
            WHERE sod.UnitPrice >= 0 AND p.StandardCost >= 0 AND sod.OrderQty > 0
        """,
        "sum_line_total": """
            SELECT COALESCE(SUM(CAST(sod.LineTotal AS DECIMAL(15,2))), 0)
            FROM Sales.SalesOrderDetail sod
            INNER JOIN Sales.SalesOrderHeader soh ON sod.SalesOrderID = soh.SalesOrderID
            INNER JOIN Production.Product p ON sod.ProductID = p.ProductID
            WHERE sod.UnitPrice >= 0 AND p.StandardCost >= 0 AND sod.OrderQty > 0
        """,
    }

    try:
        if conn is None:
            pg_conn = pg_engine.connect()
        else:
            pg_conn = conn
        dwh_count = pg_conn.execute(text(dwh_queries["count_sales"])).scalar()
        dwh_sum = float(pg_conn.execute(text(dwh_queries["sum_line_total"])).scalar())

        with mssql_engine.connect() as ms_conn:
            oltp_count = ms_conn.execute(text(oltp_queries["count_sales"])).scalar()
            oltp_sum = float(ms_conn.execute(text(oltp_queries["sum_line_total"])).scalar())

        # COUNT check
        if dwh_count == oltp_count:
            logger.info(f"  [Cross-check] COUNT(sales): DWH={dwh_count:,} = OLTP={oltp_count:,} ✓")
        else:
            logger.error(
                f"  [Cross-check] FAIL COUNT: DWH={dwh_count:,} ≠ OLTP={oltp_count:,} "
                f"(diff={abs(dwh_count - oltp_count):,})"
            )
            all_valid = False

        # SUM check (cho phép sai lệch tối đa 0.01 do floating point)
        diff = abs(dwh_sum - oltp_sum)
        if diff < 0.01:
            logger.info(f"  [Cross-check] SUM(line_total): DWH={dwh_sum:,.2f} ≈ OLTP={oltp_sum:,.2f} ✓")
        else:
            logger.error(
                f"  [Cross-check] FAIL SUM: DWH={dwh_sum:,.2f} ≠ OLTP={oltp_sum:,.2f} "
                f"(diff={diff:,.2f})"
            )
            all_valid = False

    except Exception as e:
        logger.error(f"  [Cross-check] Lỗi: {e}")
        all_valid = False

    return all_valid


# ===========================================================================
# validate_staging_data (backward compat)
# ===========================================================================

def validate_staging_data(df: pd.DataFrame, pk_columns: list = None) -> bool:
    """
    Chạy chuỗi các bước kiểm tra dữ liệu tiêu chuẩn (backward compatibility).

    Args:
        df: Dữ liệu cần kiểm tra.
        pk_columns: Cột Primary Key để check not null và unique.

    Returns:
        bool: True nếu tất cả các bài test đều pass.
    """
    is_valid = True
    if pk_columns:
        if not check_missing_values(df, pk_columns):
            is_valid = False
        if not check_unique_constraints(df, pk_columns):
            is_valid = False
    return is_valid
