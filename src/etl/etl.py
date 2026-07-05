"""ETL Entry Point - Điểm khởi chạy chính của Data Warehouse ETL Pipeline.

Cách chạy:
    # Full load (lần đầu tiên hoặc reset toàn bộ)
    python -m src.etl.etl --full

    # Incremental load (mặc định, dựa trên watermark trong config.json)
    python -m src.etl.etl

    # Reset watermark và chạy full load
    python -m src.etl.etl --reset

    # Test kết nối
    python -m src.etl.etl --test

Phần cấu hình DB được tách riêng sang src/config.py.
Watermark được quản lý trong config.json ở thư mục gốc.
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.config import load_postgres_settings
from src.watermark import reset_all_watermarks

load_dotenv()

if os.getenv("LOG_FORMAT", "").lower() == "json":
    from src.log_utils import setup_logging
    setup_logging()
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
logger = logging.getLogger(__name__)


def create_db_engine():
    """Tạo SQLAlchemy engine kết nối với Data Warehouse (PostgreSQL)."""
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


engine = create_db_engine()


def test_connection() -> bool:
    """Chạy truy vấn đơn giản để xác nhận kết nối DB hoạt động."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            val = result.scalar()
            logger.info(f"Kết nối PostgreSQL thành công (SELECT 1 = {val})")
            return True
    except Exception as e:
        logger.error(f"Không thể kết nối PostgreSQL: {e}")
        return False


def test_mssql_connection() -> bool:
    """Kiểm tra kết nối MSSQL."""
    try:
        from src.etl.extract import create_mssql_engine
        ms_engine = create_mssql_engine()
        with ms_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            val = result.scalar()
            logger.info(f"Kết nối MSSQL thành công (SELECT 1 = {val})")
            return True
    except Exception as e:
        logger.error(f"Không thể kết nối MSSQL: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Data Warehouse ETL Pipeline (MSSQL AdventureWorks → PostgreSQL)"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Chạy Full Load (bỏ qua watermark, kéo toàn bộ dữ liệu)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset toàn bộ watermark về None, sau đó chạy Full Load",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Chỉ kiểm tra kết nối DB, không chạy ETL",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Chỉ chạy snapshot KPI (không chạy ETL)",
    )
    parser.add_argument(
        "--analytics",
        choices=["kpi", "contribution", "drilldown", "causal", "all"],
        default=None,
        help="Chạy phân tích nâng cao",
    )
    parser.add_argument(
        "--period",
        default="2014Q2",
        help="Period key cho analytics (vd: 2014Q2). AdventureWorks data covers 2010-2014.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh fact data: xoá fact_sales/inventory trong range rồi full load lại. Dùng sau khi sửa transform logic.",
    )
    args = parser.parse_args()

    # --- Chỉ test kết nối ---
    if args.test:
        pg_ok = test_connection()
        ms_ok = test_mssql_connection()
        if pg_ok and ms_ok:
            logger.info("✓ Cả hai kết nối đều thành công.")
            sys.exit(0)
        else:
            logger.error("✗ Kiểm tra kết nối thất bại.")
            sys.exit(1)

    # --- Chỉ chạy snapshot ---
    if args.snapshot:
        from src.analytics.snapshot_manager import run_kpi_snapshot
        logger.info("Chạy KPI snapshot...")
        rows = run_kpi_snapshot(engine, snapshot_type="Q")
        logger.info(f"KPI Snapshot hoàn tất: {rows} rows")
        sys.exit(0)

    # --- Chạy analytics độc lập ---
    if args.analytics:
        if args.analytics == "kpi" or args.analytics == "all":
            from src.analytics.snapshot_manager import run_kpi_snapshot
            logger.info(f"Chạy KPI snapshot cho period {args.period}...")
            run_kpi_snapshot(engine, snapshot_type="Q")

        if args.analytics == "contribution" or args.analytics == "all":
            from src.analytics.contribution import contribution_breakdown, save_period_comparison
            logger.info(f"Chạy contribution analysis...")
            parts = args.period.split("Q")
            year, q = int(parts[0]), int(parts[1])
            from src.analytics.kpi_calculator import get_quarter_boundaries, get_period_key
            c_start, c_end = get_quarter_boundaries(year, q)
            if q == 1:
                p_start, p_end = get_quarter_boundaries(year - 1, 4)
            else:
                p_start, p_end = get_quarter_boundaries(year, q - 1)
            for dim in ["category", "territory", "customer_type"]:
                results = contribution_breakdown(engine, "revenue", c_start, c_end, p_start, p_end, dim)
                save_period_comparison(engine, results)
                logger.info(f"  Contribution ({dim}): {len(results)} rows")

        if args.analytics == "drilldown" or args.analytics == "all":
            from src.analytics.drill_down import drill_down
            logger.info(f"Chạy drill-down analysis...")
            parts = args.period.split("Q")
            year, q = int(parts[0]), int(parts[1])
            from src.analytics.kpi_calculator import get_quarter_boundaries
            c_start, c_end = get_quarter_boundaries(year, q)
            if q == 1:
                p_start, p_end = get_quarter_boundaries(year - 1, 4)
            else:
                p_start, p_end = get_quarter_boundaries(year, q - 1)
            results = drill_down(engine, "revenue", c_start, c_end, p_start, p_end)
            logger.info(f"Drill-down: {len(results)} insights generated")

        if args.analytics == "causal" or args.analytics == "all":
            from src.analytics.causal import price_elasticity
            logger.info(f"Chạy causal analysis...")
            for cat in ["Bikes", "Clothing", "Accessories", None]:
                result = price_elasticity(engine, category=cat)
                logger.info(f"  PED ({cat or 'overall'}): {result.get('interpretation', result.get('error', 'N/A'))}")

        sys.exit(0)

    # --- Refresh: xoá fact cũ trước khi full load (dùng sau khi sửa transform) ---
    if args.refresh:
        logger.info("Xoá fact_sales và fact_inventory...")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM dw.fact_sales"))
            conn.execute(text("DELETE FROM dw.fact_inventory"))
        logger.info("Fact tables cleared. Tiếp theo sẽ chạy full load.")
        use_incremental = False
    elif args.reset:
        logger.info("Reset toàn bộ watermark...")
        reset_all_watermarks()
        use_incremental = False
    elif args.full:
        use_incremental = False
    else:
        use_incremental = True
        # Auto-detect first run: nếu chưa có watermark nào, chạy full load
        from src.watermark import get_watermark
        has_any_watermark = any(
            get_watermark(k) is not None
            for k in ["Sales.SalesOrderHeader", "Sales.SalesOrderDetail",
                       "Production.ProductInventory"]
        )
        if not has_any_watermark:
            logger.info("Chưa có watermark — chạy full load mặc định cho lần đầu")
            use_incremental = False

    # --- Import pipeline ở đây để tránh circular import ---
    from src.etl.pipeline import run_full_etl_pipeline

    # --- Chạy pipeline ---
    success = run_full_etl_pipeline(use_incremental=use_incremental)

    if success:
        logger.info("ETL Pipeline hoàn tất thành công.")
        sys.exit(0)
    else:
        logger.error("ETL Pipeline thất bại.")
        sys.exit(1)


if __name__ == "__main__":
    main()
