import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.config import load_postgres_settings


def create_postgres_engine() -> Engine:
    """Tạo SQLAlchemy engine kết nối với Data Warehouse (PostgreSQL)."""
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


def load_to_staging(df: pd.DataFrame, table_name: str, schema: str = "staging", if_exists: str = "replace") -> None:
    """
    Load DataFrame vào một bảng staging trong Data Warehouse.
    
    Args:
        df (pd.DataFrame): Dữ liệu cần load.
        table_name (str): Tên bảng đích.
        schema (str): Tên schema đích (mặc định là 'staging').
        if_exists (str): Hành vi khi bảng đã tồn tại ('fail', 'replace', 'append').
    """
    engine = create_postgres_engine()
    
    with engine.connect() as conn:
        # Sử dụng pandas to_sql để load dữ liệu
        # Khuyến nghị sử dụng method='multi' hoặc chunksize cho dữ liệu lớn,
        # nhưng với staging ban đầu ta để mặc định hoặc chunksize=10000
        df.to_sql(
            name=table_name,
            con=conn,
            schema=schema,
            if_exists=if_exists,
            index=False,
            chunksize=10000
        )
        print(f"Đã load {len(df)} dòng vào {schema}.{table_name} thành công.")


def load_to_warehouse(df: pd.DataFrame, table_name: str, schema: str = "public", if_exists: str = "append") -> None:
    """
    Load DataFrame vào một bảng trong Data Warehouse chính (ví dụ Fact/Dim tables).
    
    Args:
        df (pd.DataFrame): Dữ liệu cần load.
        table_name (str): Tên bảng đích.
        schema (str): Tên schema đích (mặc định là 'public').
        if_exists (str): Hành vi khi bảng đã tồn tại ('fail', 'replace', 'append').
    """
    engine = create_postgres_engine()
    
    with engine.connect() as conn:
        df.to_sql(
            name=table_name,
            con=conn,
            schema=schema,
            if_exists=if_exists,
            index=False,
            chunksize=10000
        )
        print(f"Đã load {len(df)} dòng vào {schema}.{table_name} thành công.")
