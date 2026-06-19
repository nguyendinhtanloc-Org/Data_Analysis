import logging

from src.etl.extract import extract_table
from src.etl.transform import run_standard_transformations
from src.etl.validation import validate_staging_data
from src.etl.load import load_to_staging


# Cấu hình logging cơ bản
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_pipeline(table_name: str, schema_source: str = "Sales", pk_columns: list = None):
    """
    Chạy một pipeline hoàn chỉnh (Extract -> Transform -> Validate -> Load) cho một bảng.
    
    Args:
        table_name (str): Tên bảng trong nguồn (AdventureWorks).
        schema_source (str): Tên schema nguồn.
        pk_columns (list): Primary Key dùng để validate.
    """
    logger.info(f"Bắt đầu pipeline cho bảng: {schema_source}.{table_name}")
    
    # 1. EXTRACT
    logger.info("Đang trích xuất dữ liệu từ MSSQL...")
    try:
        df = extract_table(table_name=table_name, schema=schema_source)
        logger.info(f"Trích xuất thành công {len(df)} dòng.")
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
    # Lưu ý: Do transform đã chuẩn hóa tên cột thành chữ thường, 
    # nên ta cần đảm bảo pk_columns truyền vào là định dạng chuẩn hóa.
    if pk_columns:
        normalized_pks = [col.lower() for col in pk_columns]
        is_valid = validate_staging_data(df_transformed, pk_columns=normalized_pks)
        if not is_valid:
            logger.warning("Dữ liệu không vượt qua vòng kiểm tra (Validation). Dừng load.")
            # Quyết định: có thể vẫn load vào một bảng "lỗi" hoặc dừng hoàn toàn.
            # Trong pipeline đơn giản này, ta chọn dừng.
            return
    logger.info("Dữ liệu hợp lệ.")

    # 4. LOAD
    logger.info("Đang load dữ liệu vào Data Warehouse (Staging)...")
    # Đặt tên bảng staging theo chuẩn: stg_[schema]_[table_name]
    staging_table_name = f"stg_{schema_source.lower()}_{table_name.lower()}"
    try:
        load_to_staging(df_transformed, table_name=staging_table_name, schema="public", if_exists="replace")
        logger.info(f"Hoàn tất load vào bảng: public.{staging_table_name}")
    except Exception as e:
        logger.error(f"Lỗi Load: {e}")
        return

    logger.info("Pipeline hoàn tất thành công.\n")


if __name__ == "__main__":
    # Ví dụ chạy thử pipeline cho bảng Sales.Store
    # Chú ý: Cần chắc chắn database đích đã được khởi tạo và MSSQL đã có dữ liệu
    run_pipeline("Store", schema_source="Sales", pk_columns=["BusinessEntityID"])
