"""Quản lý watermark cho Incremental Load.

Module này đọc/ghi watermark từ bảng audit.etl_watermarks trong PostgreSQL,
thay vì file JSON như trước — đảm bảo atomicity, audit history, multi-process safe.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import load_postgres_settings

logger = logging.getLogger(__name__)


# ===========================================================================
# Audit schema & table initialization
# ===========================================================================

AUDIT_TABLES_DDL = [
    """
    CREATE SCHEMA IF NOT EXISTS audit
    """,
    """
    CREATE TABLE IF NOT EXISTS audit.etl_watermarks (
        table_name TEXT PRIMARY KEY,
        watermark TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit.pipeline_run (
        id SERIAL PRIMARY KEY,
        status TEXT NOT NULL,
        message TEXT,
        started_at TIMESTAMP DEFAULT NOW(),
        finished_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit.snapshot_watermark (
        period_key TEXT PRIMARY KEY,
        snapshot_type TEXT NOT NULL DEFAULT 'Q',
        calculated_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit.schema_version (
        version INTEGER PRIMARY KEY,
        description TEXT,
        applied_at TIMESTAMP DEFAULT NOW()
    )
    """,
]


def get_engine() -> Engine:
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


def init_audit_tables(engine: Optional[Engine] = None) -> None:
    """Tạo audit schema và các bảng nếu chưa tồn tại."""
    if engine is None:
        engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("COMMIT"))  # CREATE SCHEMA cần transaction riêng
        for ddl in AUDIT_TABLES_DDL:
            conn.execute(text(ddl))
        conn.execute(text("COMMIT"))


# ===========================================================================
# ETL watermarks
# ===========================================================================

def get_watermark(table_key: str, engine: Optional[Engine] = None) -> Optional[datetime]:
    """Lấy watermark datetime cho một bảng nguồn từ DB."""
    if engine is None:
        engine = get_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT watermark FROM audit.etl_watermarks WHERE table_name = :tk"),
                {"tk": table_key},
            ).fetchone()
            if row is None:
                return None
            val = row[0]
            if isinstance(val, str):
                return datetime.fromisoformat(val)
            if hasattr(val, "replace"):
                return val.replace(tzinfo=None)
            return val
    except Exception:
        return None


def save_watermark(table_key: str, dt: datetime, engine: Optional[Engine] = None) -> None:
    """Lưu watermark datetime cho một bảng nguồn vào DB."""
    if engine is None:
        engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO audit.etl_watermarks (table_name, watermark, updated_at)
                VALUES (:tk, :wm, NOW())
                ON CONFLICT (table_name) DO UPDATE SET
                    watermark = EXCLUDED.watermark,
                    updated_at = NOW()
            """),
            {"tk": table_key, "wm": dt},
        )
    logger.debug(f"Đã lưu watermark {table_key} = {dt.isoformat()}")


def save_run_status(status: str, message: str = "", engine: Optional[Engine] = None) -> None:
    """Lưu trạng thái lần chạy ETL gần nhất vào audit.pipeline_run."""
    if engine is None:
        engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO audit.pipeline_run (status, message, finished_at)
                VALUES (:st, :msg, NOW())
            """),
            {"st": status, "msg": message},
        )


def reset_all_watermarks(engine: Optional[Engine] = None) -> None:
    """Xoá toàn bộ watermark (dùng khi muốn chạy full load lại)."""
    if engine is None:
        engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit.etl_watermarks"))
    logger.info("Đã reset toàn bộ watermark.")


# ===========================================================================
# Snapshot watermarks (dùng cho KPI snapshot)
# ===========================================================================

def get_snapshot_watermark(engine: Optional[Engine] = None) -> Optional[str]:
    """Lấy watermark snapshot cuối cùng đã chạy."""
    if engine is None:
        engine = get_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT period_key FROM audit.snapshot_watermark ORDER BY period_key DESC LIMIT 1"),
            ).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def save_snapshot_watermark(period_key: str, snapshot_type: str = "Q", engine: Optional[Engine] = None) -> None:
    """Lưu watermark snapshot."""
    if engine is None:
        engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO audit.snapshot_watermark (period_key, snapshot_type, calculated_at)
                VALUES (:pk, :st, NOW())
                ON CONFLICT (period_key) DO UPDATE SET
                    snapshot_type = EXCLUDED.snapshot_type,
                    calculated_at = NOW()
            """),
            {"pk": period_key, "st": snapshot_type},
        )


# ===========================================================================
# Schema version
# ===========================================================================

SCHEMA_VERSION = 1


def get_schema_version(engine: Optional[Engine] = None) -> Optional[int]:
    """Lấy schema version hiện tại trong DB."""
    if engine is None:
        engine = get_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT MAX(version) FROM audit.schema_version"),
            ).fetchone()
            return row[0] if row and row[0] is not None else None
    except Exception:
        return None


def check_schema_version(engine: Optional[Engine] = None) -> bool:
    """Kiểm tra schema version có khớp với code hay không.

    Nếu DB chưa có version nào → insert version hiện tại (first run).
    Nếu DB version < code version → cảnh báo.
    Nếu DB version > code version → cảnh báo (có thể do rollback code).
    """
    if engine is None:
        engine = get_engine()
    db_version = get_schema_version(engine)
    if db_version is None:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO audit.schema_version (version, description) VALUES (:v, :desc)"),
                {"v": SCHEMA_VERSION, "desc": "Initial schema"},
            )
        logger.info(f"Schema version initialized to {SCHEMA_VERSION}")
        return True
    if db_version < SCHEMA_VERSION:
        logger.warning(f"Schema version mismatch: DB={db_version}, code={SCHEMA_VERSION}. Run migrations first.")
        return False
    if db_version > SCHEMA_VERSION:
        logger.warning(f"Schema version ahead: DB={db_version}, code={SCHEMA_VERSION}. Code may be outdated.")
    return True
