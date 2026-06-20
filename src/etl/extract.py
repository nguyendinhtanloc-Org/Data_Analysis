"""Extract module - Trích xuất dữ liệu từ MSSQL AdventureWorks.

Hỗ trợ hai chế độ:
  - Full load: Trích xuất toàn bộ bảng lần đầu.
  - Incremental load: Chỉ kéo bản ghi có ModifiedDate > watermark.

Mỗi dimension/fact có hàm extract riêng với JOIN query tối ưu,
tránh kéo dữ liệu dư thừa về Python rồi mới join.
"""
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import load_mssql_settings
from src.watermark import get_watermark, save_watermark

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def create_mssql_engine() -> Engine:
    """Tạo SQLAlchemy engine kết nối với Data Source (MSSQL)."""
    settings = load_mssql_settings()
    return create_engine(settings.connection_string())


# ---------------------------------------------------------------------------
# Hàm tiện ích nội bộ
# ---------------------------------------------------------------------------

def _run_query(engine: Engine, query: str, params: dict = None) -> pd.DataFrame:
    """Thực thi query và trả về DataFrame."""
    with engine.connect() as conn:
        if params:
            df = pd.read_sql_query(text(query), conn, params=params)
        else:
            df = pd.read_sql_query(query, conn)
    return df


def _build_watermark_clause(table_alias: str, table_key: str, use_incremental: bool) -> tuple[str, dict]:
    """
    Tạo mệnh đề WHERE cho watermark.

    Returns:
        (where_clause: str, params: dict)
    """
    if not use_incremental:
        return "", {}
    wm = get_watermark(table_key)
    if wm is None:
        return "", {}
    return f"AND {table_alias}.ModifiedDate > :watermark", {"watermark": wm}


# ---------------------------------------------------------------------------
# Extract - Raw tables (dùng nội bộ)
# ---------------------------------------------------------------------------

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
    logger.debug(f"extract_table: {schema}.{table_name}")
    with engine.connect() as conn:
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


# ---------------------------------------------------------------------------
# Extract - Dim_Product
# ---------------------------------------------------------------------------

def extract_dim_product(use_incremental: bool = True) -> pd.DataFrame:
    """
    Trích xuất dữ liệu cho Dim_Product từ MSSQL.

    JOIN: Production.Product + ProductSubcategory + ProductCategory
    """
    engine = create_mssql_engine()
    wm_clause, params = _build_watermark_clause("p", "Production.Product", use_incremental)

    query = f"""
        SELECT
            p.ProductID,
            p.Name,
            p.ListPrice,
            p.StandardCost,
            p.ModifiedDate,
            ps.Name AS SubcategoryName,
            pc.Name AS CategoryName
        FROM Production.Product p
        LEFT JOIN Production.ProductSubcategory ps
            ON p.ProductSubcategoryID = ps.ProductSubcategoryID
        LEFT JOIN Production.ProductCategory pc
            ON ps.ProductCategoryID = pc.ProductCategoryID
        WHERE 1=1
        {wm_clause}
    """
    logger.debug(f"extract_dim_product (incremental={use_incremental})")
    df = _run_query(engine, query, params if params else None)
    return df


# ---------------------------------------------------------------------------
# Extract - Dim_Customer
# ---------------------------------------------------------------------------

def extract_dim_customer(use_incremental: bool = True) -> pd.DataFrame:
    """
    Trích xuất dữ liệu cho Dim_Customer từ MSSQL.

    JOIN: Sales.Customer + Person.Person + Sales.Store + Person.StateProvince + Person.CountryRegion
    customer_type: 'Individual' nếu có PersonID, 'Store' nếu có StoreID
    """
    engine = create_mssql_engine()
    wm_clause, params = _build_watermark_clause("c", "Sales.Customer", use_incremental)

    query = f"""
        SELECT
            c.CustomerID,
            CASE
                WHEN c.PersonID IS NOT NULL
                    THEN ISNULL(p.FirstName + ' ', '') + ISNULL(p.MiddleName + ' ', '') + ISNULL(p.LastName, '')
                WHEN c.StoreID IS NOT NULL
                    THEN s.Name
                ELSE NULL
            END AS FullName,
            CASE
                WHEN c.PersonID IS NOT NULL THEN 'Individual'
                WHEN c.StoreID IS NOT NULL THEN 'Store'
                ELSE 'Unknown'
            END AS CustomerType,
            cr.Name AS Country,
            sp.Name AS StateProvince,
            c.TerritoryID,
            c.ModifiedDate
        FROM Sales.Customer c
        LEFT JOIN Person.Person p ON c.PersonID = p.BusinessEntityID
        LEFT JOIN Sales.Store s ON c.StoreID = s.BusinessEntityID
        LEFT JOIN Sales.SalesTerritory st ON c.TerritoryID = st.TerritoryID
        LEFT JOIN Person.StateProvince sp ON st.TerritoryID = sp.TerritoryID
        LEFT JOIN Person.CountryRegion cr ON sp.CountryRegionCode = cr.CountryRegionCode
        WHERE 1=1
        {wm_clause}
    """
    logger.debug(f"extract_dim_customer (incremental={use_incremental})")
    df = _run_query(engine, query, params if params else None)
    return df


# ---------------------------------------------------------------------------
# Extract - Dim_Territory
# ---------------------------------------------------------------------------

def extract_dim_territory(use_incremental: bool = True) -> pd.DataFrame:
    """
    Trích xuất dữ liệu cho Dim_Territory từ MSSQL.

    Source: Sales.SalesTerritory
    """
    engine = create_mssql_engine()
    wm_clause, params = _build_watermark_clause("st", "Sales.SalesTerritory", use_incremental)

    query = f"""
        SELECT
            st.TerritoryID,
            st.Name AS TerritoryName,
            st.CountryRegionCode,
            cr.Name AS CountryRegion,
            st.[Group] AS GroupName,
            st.ModifiedDate
        FROM Sales.SalesTerritory st
        LEFT JOIN Person.CountryRegion cr ON st.CountryRegionCode = cr.CountryRegionCode
        WHERE 1=1
        {wm_clause}
    """
    logger.debug(f"extract_dim_territory (incremental={use_incremental})")
    df = _run_query(engine, query, params if params else None)
    return df


# ---------------------------------------------------------------------------
# Extract - Dim_Employee
# ---------------------------------------------------------------------------

def extract_dim_employee(use_incremental: bool = True) -> pd.DataFrame:
    """
    Trích xuất dữ liệu cho Dim_Employee từ MSSQL.

    JOIN: HumanResources.Employee + Person.Person + EmployeeDepartmentHistory + Department
    Chỉ lấy current department (EndDate IS NULL).
    """
    engine = create_mssql_engine()
    wm_clause, params = _build_watermark_clause("e", "HumanResources.Employee", use_incremental)

    query = f"""
        SELECT
            e.BusinessEntityID AS EmployeeID,
            ISNULL(p.FirstName + ' ', '') + ISNULL(p.MiddleName + ' ', '') + ISNULL(p.LastName, '') AS FullName,
            e.JobTitle,
            d.Name AS Department,
            e.HireDate,
            e.ModifiedDate
        FROM HumanResources.Employee e
        INNER JOIN Person.Person p ON e.BusinessEntityID = p.BusinessEntityID
        LEFT JOIN HumanResources.EmployeeDepartmentHistory edh
            ON e.BusinessEntityID = edh.BusinessEntityID AND edh.EndDate IS NULL
        LEFT JOIN HumanResources.Department d ON edh.DepartmentID = d.DepartmentID
        WHERE 1=1
        {wm_clause}
    """
    logger.debug(f"extract_dim_employee (incremental={use_incremental})")
    df = _run_query(engine, query, params if params else None)
    return df


# ---------------------------------------------------------------------------
# Extract - Fact_Sales
# ---------------------------------------------------------------------------

def extract_fact_sales(use_incremental: bool = True) -> pd.DataFrame:
    """
    Trích xuất dữ liệu cho Fact_Sales từ MSSQL.

    JOIN: Sales.SalesOrderDetail + SalesOrderHeader
    Lấy OrderDate từ Header để tạo date_key.
    """
    engine = create_mssql_engine()
    wm_clause, params = _build_watermark_clause("sod", "Sales.SalesOrderDetail", use_incremental)

    query = f"""
        SELECT
            sod.SalesOrderDetailID,
            soh.OrderDate,
            sod.ProductID,
            soh.CustomerID,
            soh.TerritoryID,
            soh.SalesPersonID,
            sod.OrderQty,
            sod.UnitPrice,
            sod.UnitPriceDiscount,
            CAST(sod.LineTotal AS DECIMAL(15,2)) AS LineTotal,
            p.StandardCost,
            sod.ModifiedDate
        FROM Sales.SalesOrderDetail sod
        INNER JOIN Sales.SalesOrderHeader soh ON sod.SalesOrderID = soh.SalesOrderID
        INNER JOIN Production.Product p ON sod.ProductID = p.ProductID
        WHERE 1=1
        {wm_clause}
    """
    logger.debug(f"extract_fact_sales (incremental={use_incremental})")
    df = _run_query(engine, query, params if params else None)
    return df


# ---------------------------------------------------------------------------
# Extract - Fact_Inventory
# ---------------------------------------------------------------------------

def extract_fact_inventory(use_incremental: bool = True) -> pd.DataFrame:
    """
    Trích xuất dữ liệu cho Fact_Inventory từ MSSQL.

    JOIN: Production.ProductInventory + WorkOrder (aggregate scrapped/ordered qty)
    Snapshot tại ngày chạy ETL.
    """
    engine = create_mssql_engine()
    wm_clause, params = _build_watermark_clause("pi", "Production.ProductInventory", use_incremental)

    query = f"""
        SELECT
            pi.ProductID,
            SUM(pi.Quantity) AS Quantity,
            SUM(ISNULL(wo.OrderQty, 0)) AS OrderedQty,
            SUM(ISNULL(wo.ScrappedQty, 0)) AS ScrappedQty,
            MAX(pi.ModifiedDate) AS ModifiedDate
        FROM Production.ProductInventory pi
        LEFT JOIN Production.WorkOrder wo ON pi.ProductID = wo.ProductID
        WHERE 1=1
        {wm_clause}
        GROUP BY pi.ProductID
    """
    logger.debug(f"extract_fact_inventory (incremental={use_incremental})")
    df = _run_query(engine, query, params if params else None)
    return df


# ---------------------------------------------------------------------------
# Extract tất cả (dùng trong pipeline)
# ---------------------------------------------------------------------------

def extract_all(use_incremental: bool = True) -> dict[str, pd.DataFrame]:
    """
    Trích xuất toàn bộ dữ liệu cần thiết.

    Args:
        use_incremental (bool): True = incremental, False = full load.

    Returns:
        dict[str, pd.DataFrame]: Dict với key là tên bảng.
    """
    mode = "incremental" if use_incremental else "full"
    logger.info(f"Bắt đầu extract ({mode} load)...")

    raw = {
        "dim_product": extract_dim_product(use_incremental),
        "dim_customer": extract_dim_customer(use_incremental),
        "dim_territory": extract_dim_territory(use_incremental),
        "dim_employee": extract_dim_employee(use_incremental),
        "fact_sales": extract_fact_sales(use_incremental),
        "fact_inventory": extract_fact_inventory(use_incremental),
    }

    for name, df in raw.items():
        logger.info(f"  Extracted {name}: {len(df):,} rows")

    return raw


def update_extract_watermarks() -> None:
    """Cập nhật watermark cho tất cả bảng nguồn lên thời điểm hiện tại."""
    now = datetime.now()
    tables = [
        "Sales.SalesOrderDetail", "Sales.SalesOrderHeader", "Production.Product",
        "Production.ProductSubcategory", "Production.ProductCategory",
        "Sales.Customer", "Person.Person", "Sales.SalesTerritory",
        "HumanResources.Employee", "HumanResources.EmployeeDepartmentHistory",
        "HumanResources.Department", "Production.ProductInventory",
        "Production.WorkOrder",
    ]
    for table in tables:
        save_watermark(table, now)
    logger.info(f"Đã cập nhật watermark cho {len(tables)} bảng → {now.isoformat()}")
