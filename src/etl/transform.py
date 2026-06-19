import pandas as pd
from datetime import datetime


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Chuẩn hóa tên cột của DataFrame:
    - Chuyển thành chữ thường
    - Thay thế khoảng trắng bằng dấu gạch dưới
    - Bỏ các ký tự đặc biệt ở đầu và cuối
    """
    df = df.copy()
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace(r"[^\w\s]", "", regex=True)
    )
    return df


def add_metadata_columns(df: pd.DataFrame, source_system: str) -> pd.DataFrame:
    """
    Thêm các cột metadata cần thiết cho staging/data warehouse:
    - _load_timestamp: Thời điểm dữ liệu được load vào
    - _source_system: Hệ thống nguồn của dữ liệu
    """
    df = df.copy()
    df["_load_timestamp"] = datetime.now()
    df["_source_system"] = source_system
    return df


def basic_clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Thực hiện các bước làm sạch cơ bản:
    - Loại bỏ các dòng trùng lặp hoàn toàn
    - Các bước làm sạch chung khác có thể thêm vào đây
    """
    df = df.drop_duplicates()
    return df


def run_standard_transformations(df: pd.DataFrame, source_system: str) -> pd.DataFrame:
    """
    Chạy chuỗi các bước biến đổi tiêu chuẩn.
    """
    df = standardize_column_names(df)
    df = basic_clean(df)
    df = add_metadata_columns(df, source_system)
    return df
