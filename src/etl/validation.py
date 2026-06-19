import pandas as pd


def check_missing_values(df: pd.DataFrame, columns: list) -> bool:
    """
    Kiểm tra xem các cột chỉ định có giá trị null hay không.
    Thường dùng cho primary keys hoặc các cột bắt buộc.
    
    Args:
        df (pd.DataFrame): Dữ liệu cần kiểm tra.
        columns (list): Danh sách các cột cần kiểm tra.
        
    Returns:
        bool: True nếu dữ liệu hợp lệ (không có null), False nếu có null.
    """
    for col in columns:
        if df[col].isnull().any():
            print(f"[CẢNH BÁO] Cột '{col}' chứa giá trị null.")
            return False
    return True


def check_unique_constraints(df: pd.DataFrame, columns: list) -> bool:
    """
    Kiểm tra tính duy nhất của một hoặc một nhóm cột.
    
    Args:
        df (pd.DataFrame): Dữ liệu cần kiểm tra.
        columns (list): Danh sách các cột kết hợp lại phải là duy nhất.
        
    Returns:
        bool: True nếu dữ liệu hợp lệ, False nếu có vi phạm (duplicate).
    """
    if df.duplicated(subset=columns).any():
        print(f"[CẢNH BÁO] Phát hiện dữ liệu trùng lặp trên các cột: {columns}.")
        return False
    return True


def validate_staging_data(df: pd.DataFrame, pk_columns: list = None) -> bool:
    """
    Chạy chuỗi các bước kiểm tra dữ liệu tiêu chuẩn.
    
    Args:
        df (pd.DataFrame): Dữ liệu cần kiểm tra.
        pk_columns (list): Cột Primary Key để check not null và unique.
        
    Returns:
        bool: True nếu tất cả các bài test đều pass.
    """
    is_valid = True
    
    if pk_columns:
        if not check_missing_values(df, pk_columns):
            is_valid = False
            
        if not check_unique_constraints(df, pk_columns):
            is_valid = False
            
    # Thêm các bài kiểm tra khác nếu cần (kiểm tra miền giá trị, định dạng ngày tháng...)
    
    return is_valid
