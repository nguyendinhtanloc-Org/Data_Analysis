"""Cấu hình dùng chung cho đồ án Data Warehouse.

Module này gom toàn bộ phần đọc biến môi trường và tạo kết nối DB vào một chỗ
để các bước ETL khác có thể tái sử dụng mà không lặp code.
"""
from dataclasses import dataclass
import os
from urllib.parse import quote_plus


@dataclass(frozen=True)
class DatabaseSettings:
    """Thông tin kết nối cơ sở dữ liệu.

    Các giá trị không nhạy cảm có thể có giá trị mặc định để hỗ trợ local dev.
    Mật khẩu là biến bắt buộc để tránh hardcode secret trong code.
    """

    user: str
    password: str
    host: str
    port: str
    name: str

    def connection_string(self) -> str:
        """Trả về connection string tương thích SQLAlchemy."""

        safe_user = quote_plus(self.user)
        safe_password = quote_plus(self.password)
        return (
            f"postgresql+psycopg2://{safe_user}:{safe_password}"
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


def load_database_settings() -> DatabaseSettings:
    """Tạo cấu hình DB từ biến môi trường."""

    return DatabaseSettings(
        user=get_env("POSTGRES_USER", "postgres"),
        password=get_required_env("POSTGRES_PASSWORD"),
        host=get_env("POSTGRES_HOST", "localhost"),
        port=get_env("POSTGRES_PORT", "5432"),
        name=get_env("POSTGRES_DB", "adventureworks"),
    )