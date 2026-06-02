"""ETL skeleton cho đồ án Data Warehouse.

File này đóng vai trò điểm khởi chạy cho ETL. Phần cấu hình DB đã được tách
riêng sang `src/config.py` để các bước ETL sau này có thể tái sử dụng.
"""
from sqlalchemy import create_engine, text

from src.config import load_database_settings


def create_db_engine():
    """Tạo SQLAlchemy engine từ cấu hình chung của dự án."""

    settings = load_database_settings()
    return create_engine(settings.connection_string())


engine = create_db_engine()


def test_connection():
    """Chạy truy vấn đơn giản để xác nhận kết nối DB hoạt động."""

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        return result.scalar()


if __name__ == "__main__":
    print("Test connection:", test_connection())
