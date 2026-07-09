"""Pipeline orchestrator - Điều phối toàn bộ ETL pipeline.

Thứ tự load theo dependency:
  1. dim_date      (không phụ thuộc)
  2. dim_territory (không phụ thuộc)
  3. dim_employee  (không phụ thuộc)
  4. dim_product   (không phụ thuộc, SCD Type 2)
  5. dim_customer  (không phụ thuộc, SCD Type 1)
  6. fact_sales    (phụ thuộc tất cả dims)
  7. fact_inventory(phụ thuộc dim_product, dim_date)

Mỗi pipeline bọc trong DB transaction → ROLLBACK khi có lỗi.
"""
import logging
import os
from datetime import date, datetime
from typing import Optional

from sqlalchemy import create_engine, text

if os.getenv("LOG_FORMAT", "").lower() == "json":
    from src.log_utils import setup_logging as _setup
    _setup()

from src.etl.extract import (
    create_mssql_engine,
    extract_all,
    update_extract_watermarks,
)
from src.etl.transform import (
    transform_dim_date,
    transform_dim_product,
    transform_dim_territory,
    transform_dim_employee,
    transform_dim_customer,
    transform_fact_sales,
    transform_fact_inventory,
)
from src.etl.validation import (
    validate_pre_load,
    validate_post_load,
    validate_cross_check,
)
from src.etl.load import (
    create_postgres_engine,
    load_dim_date,
    load_dim_product,
    load_dim_territory,
    load_dim_employee,
    load_dim_customer,
    load_fact_sales,
    load_fact_inventory,
    refresh_daily_sales_agg,
)
from src.watermark import init_audit_tables, check_schema_version, save_run_status

# Cấu hình logging cơ bản
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline đầy đủ (dùng từ etl.py)
# ---------------------------------------------------------------------------

def run_full_etl_pipeline(use_incremental: bool = True) -> bool:
    """
    Chạy toàn bộ ETL pipeline từ đầu đến cuối.

    Luồng:
        Extract → Transform → Pre-load Validation
        → Load Dims → Load Facts
        → Post-load Validation → Cross-check
        → Save Watermark

    Args:
        use_incremental (bool):
            True  = incremental (dựa trên watermark trong config.json)
            False = full load (ignore watermark, kéo toàn bộ)

    Returns:
        bool: True nếu pipeline hoàn tất thành công.
    """
    mode = "INCREMENTAL" if use_incremental else "FULL"
    logger.info(f"{'='*60}")
    logger.info(f"  ETL Pipeline bắt đầu - Mode: {mode}")
    logger.info(f"  Thời gian: {datetime.now()}")
    logger.info(f"{'='*60}")

    pg_engine = create_postgres_engine()
    ms_engine = create_mssql_engine()

    # Khởi tạo audit tables + kiểm tra schema version
    init_audit_tables(pg_engine)
    if not check_schema_version(pg_engine):
        logger.error("Schema version mismatch — dừng pipeline. Chạy migration trước.")
        save_run_status("FAILED_SCHEMA_MISMATCH")
        return False

    # ==================================================================
    # BƯỚC 1: EXTRACT (read-only — không cần transaction)
    # ==================================================================
    logger.info("\n[1/6] EXTRACT ...")
    raw_data = extract_all(use_incremental=use_incremental)

    # ==================================================================
    # BƯỚC 2: TRANSFORM (in-memory — không cần transaction)
    # ==================================================================
    logger.info("\n[2/6] TRANSFORM ...")

    df_dim_date = transform_dim_date(start_year=2010, end_year=date.today().year + 3)
    df_dim_product = transform_dim_product(raw_data["dim_product"]) if len(raw_data["dim_product"]) > 0 else None
    df_dim_territory = transform_dim_territory(raw_data["dim_territory"]) if len(raw_data["dim_territory"]) > 0 else None
    df_dim_employee = transform_dim_employee(raw_data["dim_employee"]) if len(raw_data["dim_employee"]) > 0 else None
    df_dim_customer = transform_dim_customer(raw_data["dim_customer"]) if len(raw_data["dim_customer"]) > 0 else None

    # ==================================================================
    # BƯỚC 3: PRE-LOAD VALIDATION
    # ==================================================================
    logger.info("\n[3/6] PRE-LOAD VALIDATION ...")
    pre_data = {
        "dim_date": df_dim_date,
        "dim_product": df_dim_product,
        "dim_territory": df_dim_territory,
        "dim_employee": df_dim_employee,
        "dim_customer": df_dim_customer,
        "fact_sales_raw": raw_data["fact_sales"],
        "fact_inventory_raw": raw_data["fact_inventory"],
    }
    is_pre_valid = validate_pre_load(pre_data, allow_empty_incremental=use_incremental)
    if not is_pre_valid and not use_incremental:
        logger.error("Pre-load validation FAIL — dừng pipeline")
        save_run_status("FAILED_PRE_VALIDATION")
        return False

    # ==================================================================
    # BƯỚC 4–7: LOAD + VALIDATE trong 1 DB TRANSACTION
    # Nếu bất kỳ bước nào thất bại → ROLLBACK toàn bộ
    # ==================================================================
    try:
        with pg_engine.begin() as conn:
            # ----------------------------------------------------------
            # BƯỚC 4: LOAD DIMENSIONS
            # ----------------------------------------------------------
            logger.info("\n[4/6] LOAD DIMENSIONS ...")

            logger.info("  Loading dim_date ...")
            load_dim_date(df_dim_date, pg_engine, conn)

            logger.info("  Loading dim_territory ...")
            loaded_dim_territory = load_dim_territory(df_dim_territory, pg_engine, conn)

            logger.info("  Loading dim_employee ...")
            loaded_dim_employee = load_dim_employee(df_dim_employee, pg_engine, conn)

            logger.info("  Loading dim_product (SCD2) ...")
            loaded_dim_product = load_dim_product(df_dim_product, pg_engine, conn)

            logger.info("  Loading dim_customer ...")
            loaded_dim_customer = load_dim_customer(df_dim_customer, pg_engine, conn)

            # ----------------------------------------------------------
            # BƯỚC 5: TRANSFORM + LOAD FACTS
            # ----------------------------------------------------------
            logger.info("\n[5/6] LOAD FACTS ...")

            if len(raw_data["fact_sales"]) > 0:
                logger.info("  Transforming fact_sales ...")
                df_fact_sales = transform_fact_sales(
                    df_raw=raw_data["fact_sales"],
                    dim_product=loaded_dim_product,
                    dim_customer=loaded_dim_customer,
                    dim_territory=loaded_dim_territory,
                    dim_employee=loaded_dim_employee,
                )
                logger.info("  Loading fact_sales ...")
                n_sales = load_fact_sales(df_fact_sales, pg_engine, conn)
            else:
                logger.info("  fact_sales: không có data mới")

            if len(raw_data["fact_inventory"]) > 0:
                logger.info("  Transforming fact_inventory ...")
                run_date = date.today()
                df_fact_inventory = transform_fact_inventory(
                    df_raw=raw_data["fact_inventory"],
                    dim_product=loaded_dim_product,
                    snapshot_date=run_date,
                )
                logger.info("  Loading fact_inventory ...")
                n_inv = load_fact_inventory(df_fact_inventory, pg_engine, conn)
            else:
                logger.info("  fact_inventory: không có data mới")

            # ----------------------------------------------------------
            # BƯỚC 6: POST-LOAD VALIDATION + CROSS-CHECK
            # ----------------------------------------------------------
            logger.info("\n[6/6] POST-LOAD VALIDATION ...")
            is_post_valid = validate_post_load(pg_engine, conn=conn)

            if is_post_valid:
                logger.info("\n  Cross-check DWH vs OLTP ...")
                is_cross_valid = validate_cross_check(pg_engine, ms_engine, conn=conn)
            else:
                is_cross_valid = False
                logger.warning("  Post-load validation FAIL — bỏ qua cross-check")

            if not (is_post_valid and is_cross_valid):
                raise RuntimeError(
                    f"Validation thất bại: post_load={is_post_valid}, cross_check={is_cross_valid}. "
                    "ROLLBACK toàn bộ."
                )

            # Nếu đến đây mà không có exception → COMMIT tự động
            status = "SUCCESS"
            save_run_status(status)
            update_extract_watermarks(pg_engine=pg_engine)
            conn.execute(text("ANALYZE dw.fact_sales"))
            conn.execute(text("ANALYZE dw.fact_inventory"))
            conn.execute(text("ANALYZE dw.dim_product"))
            conn.execute(text("ANALYZE dw.dim_customer"))
            conn.execute(text("ANALYZE dw.dim_territory"))
            conn.execute(text("ANALYZE dw.dim_employee"))
            refresh_daily_sales_agg(pg_engine, conn=conn)

            logger.info(f"\n{'='*60}")
            logger.info(f"  Pipeline hoàn tất - Status: {status}")
            logger.info(f"  Thời gian kết thúc: {datetime.now()}")
            logger.info(f"{'='*60}\n")

            return True

    except Exception as e:
        logger.error(f"\n{'='*60}")
        logger.error(f"  PIPELINE LỖI: {e}")
        logger.error(f"  Transaction sẽ tự động ROLLBACK (pg_engine.begin() out of scope)")
        logger.error(f"{'='*60}")
        save_run_status(f"FAILED: {str(e)[:200]}")
        return False

    finally:
        # BƯỚC 7: SNAPSHOT (tính KPI và lưu vào mart schema)
        # Chạy sau transaction để không rollback dim/fact nếu snapshot lỗi
        logger.info("\n[7/7] ANALYTICS SNAPSHOT ...")
        try:
            from src.analytics.snapshot_manager import run_kpi_snapshot
            rows = run_kpi_snapshot(pg_engine, snapshot_type="Q")
            logger.info(f"  KPI Snapshot: {rows} rows written")
        except Exception as e:
            logger.warning(f"  Analytics snapshot không thành công (có thể bảng mart chưa tồn tại): {e}")


if __name__ == "__main__":
    pass
