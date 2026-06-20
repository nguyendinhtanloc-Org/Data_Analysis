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
from datetime import datetime

from sqlalchemy import create_engine

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
    run_standard_transformations,
)
from src.etl.validation import (
    validate_pre_load,
    validate_post_load,
    validate_cross_check,
    validate_staging_data,
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
    load_to_staging,
)
from src.watermark import save_run_status

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

    try:
        # ==================================================================
        # BƯỚC 1: EXTRACT
        # ==================================================================
        logger.info("\n[1/6] EXTRACT ...")
        raw_data = extract_all(use_incremental=use_incremental)

        # ==================================================================
        # BƯỚC 2: TRANSFORM
        # ==================================================================
        logger.info("\n[2/6] TRANSFORM ...")

        df_dim_date = transform_dim_date(start_year=2000, end_year=2030)
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
        # BƯỚC 4: LOAD DIMENSIONS
        # ==================================================================
        logger.info("\n[4/6] LOAD DIMENSIONS ...")

        # 4a. Dim_Date (không phụ thuộc)
        logger.info("  Loading dim_date ...")
        load_dim_date(df_dim_date, pg_engine)

        # 4b. Dim_Territory
        logger.info("  Loading dim_territory ...")
        loaded_dim_territory = load_dim_territory(df_dim_territory, pg_engine)

        # 4c. Dim_Employee
        logger.info("  Loading dim_employee ...")
        loaded_dim_employee = load_dim_employee(df_dim_employee, pg_engine)

        # 4d. Dim_Product (SCD Type 2)
        logger.info("  Loading dim_product (SCD2) ...")
        loaded_dim_product = load_dim_product(df_dim_product, pg_engine)

        # 4e. Dim_Customer
        logger.info("  Loading dim_customer ...")
        loaded_dim_customer = load_dim_customer(df_dim_customer, pg_engine)

        # ==================================================================
        # BƯỚC 5: TRANSFORM + LOAD FACTS
        # ==================================================================
        logger.info("\n[5/6] LOAD FACTS ...")

        # 5a. Fact_Sales
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
            n_sales = load_fact_sales(df_fact_sales, pg_engine)
        else:
            logger.info("  fact_sales: không có data mới")

        # 5b. Fact_Inventory
        if len(raw_data["fact_inventory"]) > 0:
            logger.info("  Transforming fact_inventory ...")
            df_fact_inventory = transform_fact_inventory(
                df_raw=raw_data["fact_inventory"],
                dim_product=loaded_dim_product,
            )
            logger.info("  Loading fact_inventory ...")
            n_inv = load_fact_inventory(df_fact_inventory, pg_engine)
        else:
            logger.info("  fact_inventory: không có data mới")

        # ==================================================================
        # BƯỚC 6: POST-LOAD VALIDATION + CROSS-CHECK
        # ==================================================================
        logger.info("\n[6/6] POST-LOAD VALIDATION ...")
        is_post_valid = validate_post_load(pg_engine)

        if is_post_valid:
            logger.info("\n  Cross-check DWH vs OLTP ...")
            is_cross_valid = validate_cross_check(pg_engine, ms_engine)
        else:
            is_cross_valid = False
            logger.warning("  Post-load validation FAIL — bỏ qua cross-check")

        # ==================================================================
        # KẾT QUẢ
        # ==================================================================
        overall_valid = is_post_valid and is_cross_valid
        status = "SUCCESS" if overall_valid else "SUCCESS_WITH_WARNINGS"
        save_run_status(status)

        # Cập nhật watermark sau lần chạy thành công
        update_extract_watermarks()

        logger.info(f"\n{'='*60}")
        logger.info(f"  Pipeline hoàn tất - Status: {status}")
        logger.info(f"  Thời gian kết thúc: {datetime.now()}")
        logger.info(f"{'='*60}\n")

        return True

    except Exception as e:
        logger.error(f"\n{'='*60}")
        logger.error(f"  PIPELINE LỖI: {e}")
        logger.error(f"{'='*60}")
        save_run_status(f"FAILED: {str(e)[:200]}")
        raise


# ---------------------------------------------------------------------------
# Pipeline đơn (backward compat - dùng cho pipeline.py cũ style)
# ---------------------------------------------------------------------------

def run_pipeline(table_name: str, schema_source: str = "Sales", pk_columns: list = None):
    """
    Chạy một pipeline hoàn chỉnh (Extract → Transform → Validate → Load) cho một bảng.

    Args:
        table_name (str): Tên bảng trong nguồn (AdventureWorks).
        schema_source (str): Tên schema nguồn.
        pk_columns (list): Primary Key dùng để validate.
    """
    from src.etl.extract import extract_table

    logger.info(f"Bắt đầu pipeline cho bảng: {schema_source}.{table_name}")

    # 1. EXTRACT
    logger.info("Đang trích xuất dữ liệu từ MSSQL...")
    try:
        df = extract_table(table_name=table_name, schema=schema_source)
        logger.info(f"Trích xuất thành công {len(df):,} dòng.")
    except Exception as e:
        logger.error(f"Lỗi Extract: {e}")
        return

    # 2. TRANSFORM
    logger.info("Đang biến đổi dữ liệu...")
    try:
        df_transformed = run_standard_transformations(df, source_system="AdventureWorks2022")
        logger.info("Biến đổi thành công.")
    except Exception as e:
        logger.error(f"Lỗi Transform: {e}")
        return

    # 3. VALIDATE
    logger.info("Đang kiểm tra tính hợp lệ của dữ liệu...")
    if pk_columns:
        normalized_pks = [col.lower() for col in pk_columns]
        is_valid = validate_staging_data(df_transformed, pk_columns=normalized_pks)
        if not is_valid:
            logger.warning("Dữ liệu không vượt qua vòng kiểm tra (Validation). Dừng load.")
            return
    logger.info("Dữ liệu hợp lệ.")

    # 4. LOAD
    logger.info("Đang load dữ liệu vào Data Warehouse (Staging)...")
    staging_table_name = f"stg_{schema_source.lower()}_{table_name.lower()}"
    try:
        load_to_staging(df_transformed, table_name=staging_table_name, schema="staging", if_exists="replace")
        logger.info(f"Hoàn tất load vào bảng: staging.{staging_table_name}")
    except Exception as e:
        logger.error(f"Lỗi Load: {e}")
        return

    logger.info("Pipeline hoàn tất thành công.\n")


if __name__ == "__main__":
    # Ví dụ chạy thử pipeline cho bảng Sales.Store
    run_pipeline("Store", schema_source="Sales", pk_columns=["BusinessEntityID"])
