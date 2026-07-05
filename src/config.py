"""Cấu hình dùng chung cho đồ án Data Warehouse.

Module này gom toàn bộ phần đọc biến môi trường và tạo kết nối DB vào một chỗ
để các bước ETL khác có thể tái sử dụng mà không lặp code.
"""
from dataclasses import dataclass
import os
from urllib.parse import quote_plus


@dataclass(frozen=True)
class PostgresSettings:
    """Thông tin kết nối PostgreSQL (Data Warehouse)."""

    user: str
    password: str
    host: str
    port: str
    name: str

    def connection_string(self) -> str:
        safe_user = quote_plus(self.user)
        safe_password = quote_plus(self.password)
        return (
            f"postgresql+psycopg2://{safe_user}:{safe_password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


@dataclass(frozen=True)
class MSSQLSettings:
    """Thông tin kết nối Microsoft SQL Server (OLTP Source)."""

    user: str
    password: str
    host: str
    port: str
    name: str

    def connection_string(self) -> str:
        safe_user = quote_plus(self.user)
        safe_password = quote_plus(self.password)
        # Yêu cầu pymssql. Cấu trúc URL: mssql+pymssql://<username>:<password>@<host>:<port>/<dbname>
        return (
            f"mssql+pymssql://{safe_user}:{safe_password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


def get_env(name: str, default: str) -> str:
    """Đọc biến môi trường với giá trị mặc định."""

    return os.getenv(name, default)


def get_required_env(name: str) -> str:
    """Đọc biến môi trường bắt buộc.

    Nếu thiếu cấu hình nhạy cảm, hàm này báo lỗi ngay để tránh chạy sai môi trường.
    """

    value = os.getenv(name)
    if not value:
        raise ValueError(f"Thiếu biến môi trường bắt buộc: {name}")
    return value


def load_postgres_settings() -> PostgresSettings:
    """Tạo cấu hình DB PostgreSQL từ biến môi trường."""

    return PostgresSettings(
        user=get_env("POSTGRES_USER", "postgres"),
        password=get_required_env("POSTGRES_PASSWORD"),
        host=get_env("POSTGRES_HOST", "localhost"),
        port=get_env("POSTGRES_PORT", "5432"),
        name=get_env("POSTGRES_DB", "adventureworks"),
    )


def load_mssql_settings() -> MSSQLSettings:
    """Tạo cấu hình DB MSSQL từ biến môi trường.
    
    Hỗ trợ cả MSSQL_DB (cũ) và ETL_SOURCE_DATABASE (mới).
    """
    db_name = os.getenv("ETL_SOURCE_DATABASE") or os.getenv("MSSQL_DB", "AdventureWorks2022")
    return MSSQLSettings(
        user=get_env("MSSQL_USER", "sa"),
        password=get_required_env("MSSQL_PASSWORD"),
        host=get_env("MSSQL_HOST", "localhost"),
        port=get_env("MSSQL_PORT", "1433"),
        name=db_name,
    )