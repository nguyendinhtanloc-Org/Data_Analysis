"""Transform module - Biến đổi dữ liệu cho từng bảng DWH.

Bao gồm:
  - Sinh Dim_Date từ khoảng năm chỉ định
  - SCD Type 2 cho Dim_Product
  - SCD Type 1 cho Dim_Customer, Dim_Territory, Dim_Employee
  - Tính gross_profit tại bước Transform
  - Surrogate key mapping
  - Null handling theo Data Quality Rules
  - Deduplication (giữ bản ghi ModifiedDate mới nhất)
"""
import logging
from datetime import datetime, date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ===========================================================================
# Tiện ích chung
# ===========================================================================

def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Chuẩn hóa tên cột: thường, bỏ khoảng trắng, bỏ ký tự đặc biệt."""
    df = df.copy()
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace(r"[^\w]", "", regex=True)
    )
    return df


def add_load_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    """Thêm cột _load_timestamp."""
    df = df.copy()
    df["_load_timestamp"] = datetime.now()
    return df


def deduplicate_by_modified(df: pd.DataFrame, natural_key: str | list[str]) -> pd.DataFrame:
    """
    Loại bỏ bản ghi trùng natural key, giữ bản có ModifiedDate mới nhất.

    Args:
        df: DataFrame đầu vào.
        natural_key: Tên cột (hoặc danh sách cột) là natural key.
    """
    if isinstance(natural_key, str):
        natural_key = [natural_key]
    # Chuẩn hóa tên cột tham chiếu sang lowercase
    key_cols_lower = [k.lower() for k in natural_key]
    mod_col = next((c for c in df.columns if "modified" in c.lower() and "date" in c.lower()), None)
    if mod_col:
        df = df.sort_values(mod_col, ascending=False)
    df = df.drop_duplicates(subset=key_cols_lower, keep="first")
    return df.reset_index(drop=True)


def log_dropped_rows(original: pd.DataFrame, filtered: pd.DataFrame, reason: str) -> None:
    """Ghi log số bản ghi bị drop."""
    n_dropped = len(original) - len(filtered)
    if n_dropped > 0:
        logger.warning(f"  DROP {n_dropped} bản ghi: {reason}")


# ===========================================================================
# Dim_Date
# ===========================================================================

def transform_dim_date(start_year: int = 2010, end_year: int = 2030) -> pd.DataFrame:
    """
    Sinh bảng Dim_Date từ start_year đến end_year.

    Returns:
        pd.DataFrame với cột: date_key, date, day, month, quarter, year, is_weekend
    """
    dates = pd.date_range(
        start=f"{start_year}-01-01",
        end=f"{end_year}-12-31",
        freq="D"
    )
    df = pd.DataFrame({
        "date_key": dates.strftime("%Y%m%d").astype(int),
        "date": dates.date,
        "day": dates.day,
        "month": dates.month,
        "quarter": dates.quarter,
        "year": dates.year,
        "is_weekend": dates.dayofweek >= 5,
    })
    logger.info(f"transform_dim_date: {len(df):,} ngày ({start_year}→{end_year})")
    return df


# ===========================================================================
# Dim_Product (SCD Type 2)
# ===========================================================================

def transform_dim_product(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Transform dữ liệu cho Dim_Product.

    SCD Type 2: theo dõi thay đổi name, list_price, standard_cost.
    Bước này tạo "staging" records — việc so sánh với DWH hiện tại
    và đóng/mở bản ghi được xử lý trong load.py.

    Data Quality:
      - list_price < 0 hoặc NULL → DROP + log
      - standard_cost < 0 hoặc NULL → DROP + log
      - Duplicate ProductID → giữ ModifiedDate mới nhất

    Returns:
        pd.DataFrame chuẩn cho dim_product staging
    """
    df = standardize_column_names(df_raw).copy()
    original_count = len(df)

    # Dedup
    df = deduplicate_by_modified(df, "productid")

    # Drop invalid prices
    mask_price = (df["listprice"].isna()) | (df["listprice"] < 0)
    mask_cost = (df["standardcost"].isna()) | (df["standardcost"] < 0)
    invalid = mask_price | mask_cost
    log_dropped_rows(df, df[~invalid], "list_price hoặc standard_cost < 0 hoặc NULL")
    df = df[~invalid].copy()

    # Fill null subcategory / category
    df["subcategoryname"] = df["subcategoryname"].fillna("Unknown")
    df["categoryname"] = df["categoryname"].fillna("Unknown")

    # Rename sang schema DWH
    df = df.rename(columns={
        "productid": "product_id",
        "name": "name",
        "subcategoryname": "subcategory",
        "categoryname": "category",
        "listprice": "list_price",
        "standardcost": "standard_cost",
    })

    # Chọn cột cần thiết
    cols = ["product_id", "name", "subcategory", "category", "list_price", "standard_cost"]
    df = df[cols].copy()

    df = add_load_timestamp(df)
    logger.info(f"transform_dim_product: {original_count} → {len(df):,} rows")
    return df


# ===========================================================================
# Dim_Territory (SCD Type 1)
# ===========================================================================

def transform_dim_territory(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Transform dữ liệu cho Dim_Territory (SCD Type 1).

    Data Quality:
      - Duplicate TerritoryID → giữ ModifiedDate mới nhất
    """
    df = standardize_column_names(df_raw).copy()
    original_count = len(df)

    df = deduplicate_by_modified(df, "territoryid")

    # Fill nulls
    df["countryregion"] = df["countryregion"].fillna("Unknown")
    df["groupname"] = df["groupname"].fillna("Unknown")
    df["territoryname"] = df["territoryname"].fillna("Unknown")

    df = df.rename(columns={
        "territoryid": "territory_id",
        "territoryname": "territory_name",
        "countryregion": "country_region",
        "groupname": "group_name",
    })

    cols = ["territory_id", "territory_name", "country_region", "group_name"]
    df = df[cols].copy()
    df = add_load_timestamp(df)
    logger.info(f"transform_dim_territory: {original_count} → {len(df):,} rows")
    return df


# ===========================================================================
# Dim_Employee (SCD Type 1)
# ===========================================================================

def transform_dim_employee(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Transform dữ liệu cho Dim_Employee (SCD Type 1).

    Data Quality:
      - full_name NULL → Fill 'Unknown'
      - job_title NULL → Fill 'Unknown'
      - department NULL → Fill 'Unknown'
      - hire_date NULL → DROP (dữ liệu không hợp lệ)
      - Duplicate EmployeeID → giữ ModifiedDate mới nhất
    """
    df = standardize_column_names(df_raw).copy()
    original_count = len(df)

    df = deduplicate_by_modified(df, "employeeid")

    # Drop nếu hire_date null
    before_df = df.copy()
    df = df[df["hiredate"].notna()].copy()
    log_dropped_rows(before_df, df, "hire_date IS NULL")

    # Fill nulls
    df["fullname"] = df["fullname"].fillna("Unknown")
    df["jobtitle"] = df["jobtitle"].fillna("Unknown")
    df["department"] = df["department"].fillna("Unknown")

    df = df.rename(columns={
        "employeeid": "employee_id",
        "fullname": "full_name",
        "jobtitle": "job_title",
        "department": "department",
        "hiredate": "hire_date",
    })

    cols = ["employee_id", "full_name", "job_title", "department", "hire_date"]
    df = df[cols].copy()
    df = add_load_timestamp(df)
    logger.info(f"transform_dim_employee: {original_count} → {len(df):,} rows")
    return df


# ===========================================================================
# Dim_Customer (SCD Type 1)
# ===========================================================================

def transform_dim_customer(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Transform dữ liệu cho Dim_Customer (SCD Type 1).

    Data Quality:
      - full_name NULL → Fill 'Unknown'
      - customer_type NULL → Fill 'Unknown'
      - Duplicate CustomerID → giữ ModifiedDate mới nhất
    """
    df = standardize_column_names(df_raw).copy()
    original_count = len(df)

    df = deduplicate_by_modified(df, "customerid")

    # Fill nulls
    df["fullname"] = df["fullname"].fillna("Unknown")
    df["customertype"] = df["customertype"].fillna("Unknown")
    df["country"] = df["country"].fillna("Unknown")

    df = df.rename(columns={
        "customerid": "customer_id",
        "fullname": "full_name",
        "customertype": "customer_type",
        "country": "country",
        "territoryid": "territory_id",
    })

    cols = ["customer_id", "full_name", "customer_type", "country", "territory_id"]
    df = df[cols].copy()
    df = add_load_timestamp(df)
    logger.info(f"transform_dim_customer: {original_count} → {len(df):,} rows")
    return df


# ===========================================================================
# Fact_Sales
# ===========================================================================

def transform_fact_sales(
    df_raw: pd.DataFrame,
    dim_product: pd.DataFrame,
    dim_customer: pd.DataFrame,
    dim_territory: pd.DataFrame,
    dim_employee: pd.DataFrame,
) -> pd.DataFrame:
    """
    Transform dữ liệu cho Fact_Sales.

    Data Quality:
      - unit_price < 0 hoặc NULL → DROP + log
      - standard_cost < 0 hoặc NULL → DROP + log
      - order_qty <= 0 hoặc NULL → DROP + log
      - FK null (ProductID, CustomerID, TerritoryID) → DROP + log
      - Duplicate SalesOrderDetailID → giữ ModifiedDate mới nhất

    Derived:
      - date_key = int(OrderDate.strftime('%Y%m%d'))
      - gross_profit = line_total - (standard_cost * order_qty)
      - Surrogate key lookup: product_key, customer_key, territory_key, employee_key

    Args:
        df_raw: Raw extract từ MSSQL.
        dim_product: Dim_Product đã load vào DWH (có cột product_id, product_key).
        dim_customer: Dim_Customer đã load vào DWH (có cột customer_id, customer_key).
        dim_territory: Dim_Territory đã load vào DWH (có cột territory_id, territory_key).
        dim_employee: Dim_Employee đã load vào DWH (có cột employee_id, employee_key).
    """
    df = standardize_column_names(df_raw).copy()
    original_count = len(df)

    # Dedup
    df = deduplicate_by_modified(df, "salesorderdetailid")

    # --- Drop FK nulls ---
    fk_cols = {"productid": "ProductID", "customerid": "CustomerID", "territoryid": "TerritoryID"}
    for col, label in fk_cols.items():
        before = len(df)
        df = df[df[col].notna()].copy()
        if len(df) < before:
            logger.warning(f"  DROP {before - len(df)} bản ghi: {label} IS NULL (orphan FK)")

    # --- Drop invalid metrics ---
    before = len(df)
    mask_price = df["unitprice"].isna() | (df["unitprice"] < 0)
    df = df[~mask_price].copy()
    log_dropped_rows(pd.DataFrame(range(before)), pd.DataFrame(range(len(df))), "unit_price NULL hoặc < 0")

    before = len(df)
    mask_cost = df["standardcost"].isna() | (df["standardcost"] < 0)
    df = df[~mask_cost].copy()
    log_dropped_rows(pd.DataFrame(range(before)), pd.DataFrame(range(len(df))), "standard_cost NULL hoặc < 0")

    before = len(df)
    mask_qty = df["orderqty"].isna() | (df["orderqty"] <= 0)
    df = df[~mask_qty].copy()
    log_dropped_rows(pd.DataFrame(range(before)), pd.DataFrame(range(len(df))), "order_qty NULL hoặc <= 0")

    # --- date_key ---
    df["orderdate"] = pd.to_datetime(df["orderdate"])
    df["date_key"] = df["orderdate"].dt.strftime("%Y%m%d").astype(int)

    # --- Surrogate key lookup ---
    # Dim_Product: lookup theo valid range (SCD Type 2)
    # Build lookup: product_id -> list of (valid_from, valid_to, product_key, is_current, standard_cost)
    prod_versions = {}
    for _, prow in dim_product.iterrows():
        pid = int(prow["product_id"])
        prod_versions.setdefault(pid, []).append((
            prow["valid_from"], prow["valid_to"],
            int(prow["product_key"]),
            prow.get("is_current", False),
            float(prow["standard_cost"]),
        ))

    def _lookup_product_key(pid_val, orderdate_val):
        if pd.isna(pid_val):
            return pd.NA
        pid = int(pid_val)
        versions = prod_versions.get(pid)
        if not versions:
            logger.warning(f"  ProductID={pid} not found in dim_product — dropped")
            return pd.NA
        od = pd.Timestamp(orderdate_val)
        for vf, vt, pk, _, _ in versions:
            if vf <= od and (vt is None or vt > od):
                return pk
        fallback = None
        for _, _, pk, is_curr, _ in versions:
            if is_curr:
                fallback = pk
                break
        if fallback is None:
            fallback = versions[0][2]
        logger.warning(f"  ProductID={pid} no valid-range match for {od.date()} — using fallback product_key={fallback}")
        return fallback

    df["product_key"] = df.apply(
        lambda r: _lookup_product_key(r["productid"], r["orderdate"]), axis=1
    )

    # --- Overwrite standard_cost with historical SCD2 value ---
    # Extract's p.StandardCost is the *current* cost, not the cost at time of sale.
    # After product_key is resolved to the correct SCD2 version, use that version's cost.
    prod_cost_map = dim_product[["product_key", "standard_cost"]].drop_duplicates("product_key")
    cost_map = dict(zip(prod_cost_map["product_key"], prod_cost_map["standard_cost"]))
    df["standard_cost"] = df["product_key"].map(cost_map)
    df["gross_profit"] = (df["linetotal"] - df["standard_cost"] * df["orderqty"]).round(2)

    cust_map = dim_customer[["customer_id", "customer_key"]].drop_duplicates("customer_id")
    df = df.merge(cust_map, left_on="customerid", right_on="customer_id", how="left")

    terr_map = dim_territory[["territory_id", "territory_key"]].drop_duplicates("territory_id")
    df = df.merge(terr_map, left_on="territoryid", right_on="territory_id", how="left")

    emp_map = dim_employee[["employee_id", "employee_key"]].drop_duplicates("employee_id")
    df = df.merge(emp_map, left_on="salespersonid", right_on="employee_id", how="left")

    # --- Drop orphan FK sau lookup ---
    before = len(df)
    df = df[df["product_key"].notna() & df["customer_key"].notna() & df["territory_key"].notna()].copy()
    log_dropped_rows(pd.DataFrame(range(before)), pd.DataFrame(range(len(df))), "Orphan FK sau surrogate lookup")

    # --- Final columns ---
    df = df.rename(columns={
        "salesorderdetailid": "sales_order_detail_id",
        "salesorderid": "sales_order_id",
        "orderqty": "order_qty",
        "unitprice": "unit_price",
        "unitpricediscount": "unit_price_discount",
        "linetotal": "line_total",
    })
    # standard_cost was already mapped from SCD2 historical lookup above;
    # drop the original standardcost column to avoid duplicate column names
    if "standardcost" in df.columns:
        df = df.drop(columns=["standardcost"])

    cols = [
        "sales_order_detail_id", "sales_order_id", "date_key",
        "product_key", "customer_key", "territory_key", "employee_key",
        "order_qty", "unit_price", "unit_price_discount",
        "line_total", "standard_cost", "gross_profit",
    ]
    df = df[cols].copy()
    # Cast surrogate keys to int
    for k in ["product_key", "customer_key", "territory_key"]:
        df[k] = df[k].astype(int)
    # employee_key nullable
    df["employee_key"] = pd.array(df["employee_key"], dtype=pd.Int64Dtype())

    df = add_load_timestamp(df)
    logger.info(f"transform_fact_sales: {original_count} → {len(df):,} rows")
    return df


# ===========================================================================
# Fact_Inventory
# ===========================================================================

def transform_fact_inventory(
    df_raw: pd.DataFrame,
    dim_product: pd.DataFrame,
    snapshot_date: date | None = None,
) -> pd.DataFrame:
    """
    Transform dữ liệu cho Fact_Inventory (daily snapshot).

    Data Quality:
      - ProductID null → DROP + log
      - Quantity NULL → DROP + log

    Args:
        df_raw: Raw extract từ MSSQL (grouped by ProductID, LocationID).
        dim_product: Dim_Product đã load (có product_id, product_key).
        snapshot_date: Ngày snapshot. Nếu None, dùng từ cột SnapshotDate hoặc hôm nay.
    """
    df = standardize_column_names(df_raw).copy()
    original_count = len(df)

    # Drop null productid
    before = len(df)
    df = df[df["productid"].notna()].copy()
    log_dropped_rows(pd.DataFrame(range(before)), pd.DataFrame(range(len(df))), "ProductID IS NULL")

    # Drop null quantity
    before = len(df)
    df = df[df["quantity"].notna()].copy()
    log_dropped_rows(pd.DataFrame(range(before)), pd.DataFrame(range(len(df))), "Quantity IS NULL")

    # date_key: ưu tiên snapshot_date từ param, fallback về SnapshotDate từ extract
    if snapshot_date is None:
        date_col = next((c for c in df.columns if "snapshotdate" in c.lower()), None)
        if date_col and df[date_col].notna().any():
            snapshot_date = pd.to_datetime(df[date_col].max()).date()
        else:
            snapshot_date = date.today()
    date_key = int(snapshot_date.strftime("%Y%m%d"))
    df["date_key"] = date_key

    # Surrogate key lookup: SCD2 valid-range matching theo snapshot_date
    prod_versions = {}
    for _, prow in dim_product.iterrows():
        pid = int(prow["product_id"])
        prod_versions.setdefault(pid, []).append((
            prow["valid_from"], prow["valid_to"],
            int(prow["product_key"]),
        ))

    def _lookup_product_key(pid_val):
        if pd.isna(pid_val):
            return pd.NA
        pid = int(pid_val)
        versions = prod_versions.get(pid)
        if not versions:
            return pd.NA
        for vf, vt, pk in versions:
            vf_ts = pd.Timestamp(vf)
            vt_ts = pd.Timestamp(vt) if vt is not None else None
            vd = pd.Timestamp(snapshot_date)
            if vf_ts <= vd and (vt_ts is None or vt_ts > vd):
                return pk
        return versions[-1][2]

    df["product_key"] = df["productid"].apply(_lookup_product_key)

    before = len(df)
    df = df[df["product_key"].notna()].copy()
    log_dropped_rows(pd.DataFrame(range(before)), pd.DataFrame(range(len(df))), "Orphan product_key")

    df["location_id"] = df.get("locationid")
    df["location_id"] = df["location_id"].where(df["location_id"].notna(), None)
    df["location_id"] = pd.array(df["location_id"], dtype=pd.Int64Dtype())

    cols = ["date_key", "product_key", "location_id", "quantity"]
    df = df[[c for c in cols if c in df.columns]].copy()
    df["product_key"] = df["product_key"].astype(int)

    df = add_load_timestamp(df)
    logger.info(f"transform_fact_inventory: {original_count} → {len(df):,} rows")
    return df


# ===========================================================================
# run_standard_transformations (backward compat cho pipeline.py cũ)
# ===========================================================================

def run_standard_transformations(df: pd.DataFrame, source_system: str) -> pd.DataFrame:
    """
    Chạy chuỗi các bước biến đổi tiêu chuẩn (dùng cho pipeline đơn giản).

    Args:
        df: DataFrame đầu vào.
        source_system: Tên hệ thống nguồn.

    Returns:
        pd.DataFrame đã được chuẩn hóa.
    """
    df = standardize_column_names(df)
    df = df.drop_duplicates()
    df["_load_timestamp"] = datetime.now()
    df["_source_system"] = source_system
    return df
