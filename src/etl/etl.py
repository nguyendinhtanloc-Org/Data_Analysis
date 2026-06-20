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

# Thêm project root vào sys.path để import src.* hoạt động
# dù chạy bằng `python src/etl/etl.py` hay `python -m src.etl.etl`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
except ImportError:
    # Trong Docker container env vars đã được inject qua env_file
    load_dotenv = lambda: None  # noqa: E731

from sqlalchemy import create_engine, text

from src.config import load_postgres_settings
from src.watermark import reset_all_watermarks

# Load biến môi trường từ .env
load_dotenv()

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
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

    # --- Reset watermark ---
    if args.reset:
        logger.info("Reset toàn bộ watermark...")
        reset_all_watermarks()
        use_incremental = False
    elif args.full:
        use_incremental = False
    else:
        use_incremental = True

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
