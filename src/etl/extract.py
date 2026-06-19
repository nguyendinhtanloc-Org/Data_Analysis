import pandas as pd
from sqlalchemy import create_engine

from src.config import load_mssql_settings


def create_mssql_engine():
    """Tạo SQLAlchemy engine kết nối với Data Source (MSSQL)."""
    settings = load_mssql_settings()
    return create_engine(settings.connection_string())


def extract_table(table_name: str, schema: str = "dbo") -> pd.DataFrame:
    """
    Trích xuất toàn bộ dữ liệu từ một bảng trong MSSQL.
    
    Args:
        table_name (str): Tên bảng cần trích xuất.
        schema (str): Tên schema của bảng (mặc định là 'dbo').
        
    Returns:
        pd.DataFrame: DataFrame chứa dữ liệu từ bảng.
    """
    engine = create_mssql_engine()
    query = f"SELECT * FROM {schema}.{table_name}"
    
    with engine.connect() as conn:
        # Sử dụng pandas để đọc dữ liệu từ SQL vào DataFrame
        df = pd.read_sql_query(query, conn)
        
    return df


def extract_query(query: str) -> pd.DataFrame:
    """
    Trích xuất dữ liệu dựa trên một câu truy vấn SQL tùy ý.
    
    Args:
        query (str): Câu truy vấn SQL.
        
    Returns:
        pd.DataFrame: DataFrame chứa dữ liệu kết quả.
    """
    engine = create_mssql_engine()
    
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
        
    return df
