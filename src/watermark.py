"""Quản lý watermark cho Incremental Load.

Module này đọc/ghi watermark timestamp từ file config.json,
dùng để xác định bản ghi mới cần extract trong incremental load.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Đường dẫn tới config.json ở thư mục gốc dự án
CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _load_config() -> dict:
    """Đọc toàn bộ config.json."""
    if not CONFIG_PATH.exists():
        logger.warning(f"Không tìm thấy {CONFIG_PATH}. Tạo config mặc định.")
        _save_config({"watermarks": {}, "last_run": None, "last_run_status": None})
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(config: dict) -> None:
    """Ghi toàn bộ config.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, default=str)


def get_watermark(table_key: str) -> datetime | None:
    """
    Lấy watermark datetime cho một bảng nguồn.

    Args:
        table_key (str): Tên bảng theo format 'Schema.Table', vd: 'Sales.SalesOrderDetail'

    Returns:
        datetime | None: Thời điểm watermark, hoặc None nếu chưa có (full load).
    """
    config = _load_config()
    watermarks = config.get("watermarks", {})
    value = watermarks.get(table_key)
    if value is None:
        return None
    return datetime.fromisoformat(value)


def save_watermark(table_key: str, dt: datetime) -> None:
    """
    Lưu watermark datetime cho một bảng nguồn.

    Args:
        table_key (str): Tên bảng theo format 'Schema.Table'
        dt (datetime): Thời điểm watermark mới
    """
    config = _load_config()
    if "watermarks" not in config:
        config["watermarks"] = {}
    config["watermarks"][table_key] = dt.isoformat()
    _save_config(config)
    logger.debug(f"Đã lưu watermark {table_key} = {dt.isoformat()}")


def save_run_status(status: str) -> None:
    """Lưu trạng thái lần chạy gần nhất."""
    config = _load_config()
    config["last_run"] = datetime.now().isoformat()
    config["last_run_status"] = status
    _save_config(config)


def reset_all_watermarks() -> None:
    """Reset toàn bộ watermark về None (dùng khi muốn chạy full load lại)."""
    config = _load_config()
    for key in config.get("watermarks", {}):
        config["watermarks"][key] = None
    _save_config(config)
    logger.info("Đã reset toàn bộ watermark về None.")
