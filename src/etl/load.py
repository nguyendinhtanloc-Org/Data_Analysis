"""Load module - Load dữ liệu từ DataFrame vào PostgreSQL DWH.

Nguyên tắc:
  - Toàn bộ quá trình load một pipeline được bọc trong một DB transaction.
  - Lỗi giữa chừng → ROLLBACK toàn bộ.
  - SCD Type 2 (dim_product): close bản ghi cũ, insert bản mới.
  - SCD Type 1 (dim_customer, dim_territory, dim_employee): UPSERT tại chỗ.
  - Fact tables: INSERT with ON CONFLICT DO NOTHING (idempotent).
"""
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Connection

from src.config import load_postgres_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def create_postgres_engine() -> Engine:
    """Tạo SQLAlchemy engine kết nối với Data Warehouse (PostgreSQL)."""
    settings = load_postgres_settings()
    return create_engine(settings.connection_string())


# ---------------------------------------------------------------------------
# Staging load (backward compat)
# ---------------------------------------------------------------------------

def load_to_staging(
    df: pd.DataFrame,
    table_name: str,
    schema: str = "staging",
    if_exists: str = "replace",
) -> None:
    """
    Load DataFrame vào một bảng staging trong Data Warehouse.

    Args:
        df: Dữ liệu cần load.
        table_name: Tên bảng đích.
        schema: Tên schema đích (mặc định là 'staging').
        if_exists: Hành vi khi bảng đã tồn tại ('fail', 'replace', 'append').
    """
    engine = create_postgres_engine()
    with engine.connect() as conn:
        df.to_sql(
            name=table_name,
            con=conn,
            schema=schema,
            if_exists=if_exists,
            index=False,
            chunksize=10000,
        )
        conn.commit()
        logger.info(f"Đã load {len(df):,} dòng vào {schema}.{table_name}")


def load_to_warehouse(
    df: pd.DataFrame,
    table_name: str,
    schema: str = "public",
    if_exists: str = "append",
) -> None:
    """
    Load DataFrame vào một bảng trong Data Warehouse chính (Fact/Dim tables).

    Args:
        df: Dữ liệu cần load.
        table_name: Tên bảng đích.
        schema: Tên schema đích (mặc định là 'public').
        if_exists: Hành vi khi bảng đã tồn tại ('fail', 'replace', 'append').
    """
    engine = create_postgres_engine()
    with engine.connect() as conn:
        df.to_sql(
            name=table_name,
            con=conn,
            schema=schema,
            if_exists=if_exists,
            index=False,
            chunksize=10000,
        )
        conn.commit()
        logger.info(f"Đã load {len(df):,} dòng vào {schema}.{table_name}")


# ---------------------------------------------------------------------------
# Helpers nội bộ
# ---------------------------------------------------------------------------

def _upsert_dim_scd1(
    conn: Connection,
    df: pd.DataFrame,
    table: str,
    schema: str,
    business_key: str,
    surrogate_key: str,
    update_cols: list[str],
) -> pd.DataFrame:
    """
    UPSERT SCD Type 1: cập nhật tại chỗ nếu đã tồn tại, insert nếu chưa có.

    Returns:
        pd.DataFrame: Dim table hiện tại trong DWH sau khi upsert (có surrogate key).
    """
    # Lấy dữ liệu hiện tại từ DWH
    existing_df = pd.read_sql(
        text(f'SELECT * FROM {schema}."{table}"'),
        conn,
    )

    now = datetime.now()
    inserted = 0
    updated = 0

    for _, row in df.iterrows():
        bk_val = row[business_key]
        existing_row = existing_df[existing_df[business_key] == bk_val]

        if existing_row.empty:
            # INSERT
            insert_data = {c: row[c] for c in update_cols + [business_key] if c in row.index}
            insert_data["_load_timestamp"] = now
            cols = ", ".join(f'"{k}"' for k in insert_data.keys())
            placeholders = ", ".join(f":{k}" for k in insert_data.keys())
            conn.execute(
                text(f'INSERT INTO {schema}."{table}" ({cols}) VALUES ({placeholders})'),
                insert_data,
            )
            inserted += 1
        else:
            # UPDATE
            sk_val = existing_row.iloc[0][surrogate_key]
            update_data = {c: row[c] for c in update_cols if c in row.index}
            update_data["_load_timestamp"] = now
            set_clause = ", ".join(f'"{k}" = :{k}' for k in update_data.keys())
            update_data[surrogate_key] = int(sk_val)
            conn.execute(
                text(f'UPDATE {schema}."{table}" SET {set_clause} WHERE "{surrogate_key}" = :{surrogate_key}'),
                update_data,
            )
            updated += 1

    logger.info(f"  {schema}.{table} SCD1: {inserted} inserted, {updated} updated")

    # Trả về bảng dim với surrogate key
    return pd.read_sql(text(f'SELECT * FROM {schema}."{table}"'), conn)


def _load_dim_scd2(
    conn: Connection,
    df: pd.DataFrame,
    table: str,
    schema: str,
    business_key: str,
    track_cols: list[str],
) -> pd.DataFrame:
    """
    Load SCD Type 2:
    - Nếu business_key chưa tồn tại → INSERT mới (is_current=True)
    - Nếu đã tồn tại nhưng track_cols thay đổi → close bản cũ, INSERT bản mới
    - Nếu không thay đổi → bỏ qua

    Returns:
        pd.DataFrame: Dim table hiện tại sau khi load (có surrogate key).
    """
    existing_df = pd.read_sql(
        text(f'SELECT * FROM {schema}."{table}"'),
        conn,
    )
    now = datetime.now()
    inserted = 0
    closed = 0

    for _, row in df.iterrows():
        bk_val = row[business_key]
        current_rows = existing_df[
            (existing_df[business_key] == bk_val) & (existing_df["is_current"] == True)
        ]

        if current_rows.empty:
            # INSERT mới
            _insert_scd2_row(conn, schema, table, row, now)
            inserted += 1
        else:
            curr = current_rows.iloc[0]
            # Kiểm tra thay đổi
            changed = any(
                str(row[col]) != str(curr[col])
                for col in track_cols
                if col in row.index and col in curr.index
            )
            if changed:
                # Close bản cũ
                sk_val = int(curr["product_key"])
                conn.execute(
                    text(
                        f'UPDATE {schema}."{table}" SET valid_to = :vt, is_current = false '
                        f'WHERE product_key = :pk'
                    ),
                    {"vt": now, "pk": sk_val},
                )
                closed += 1
                # Insert bản mới
                _insert_scd2_row(conn, schema, table, row, now)
                inserted += 1

    logger.info(f"  {schema}.{table} SCD2: {inserted} inserted, {closed} closed")

    return pd.read_sql(text(f'SELECT * FROM {schema}."{table}" WHERE is_current = true'), conn)


def _insert_scd2_row(
    conn: Connection,
    schema: str,
    table: str,
    row: pd.Series,
    now: datetime,
) -> None:
    """Insert một bản ghi SCD Type 2 mới."""
    data = {
        "product_id": int(row["product_id"]),
        "name": str(row["name"])[:100],
        "subcategory": str(row["subcategory"])[:100] if pd.notna(row.get("subcategory")) else None,
        "category": str(row["category"])[:100] if pd.notna(row.get("category")) else None,
        "list_price": float(row["list_price"]),
        "standard_cost": float(row["standard_cost"]),
        "valid_from": now,
        "valid_to": None,
        "is_current": True,
        "_load_timestamp": now,
    }
    conn.execute(
        text("""
            INSERT INTO dw.dim_product
                (product_id, name, subcategory, category, list_price, standard_cost,
                 valid_from, valid_to, is_current, _load_timestamp)
            VALUES
                (:product_id, :name, :subcategory, :category, :list_price, :standard_cost,
                 :valid_from, :valid_to, :is_current, :_load_timestamp)
        """),
        data,
    )


# ---------------------------------------------------------------------------
# Public load functions (dùng trong pipeline)
# ---------------------------------------------------------------------------

def load_dim_date(df: pd.DataFrame, engine: Engine) -> None:
    """Load Dim_Date vào DWH. INSERT ON CONFLICT DO NOTHING (idempotent)."""
    if df is None or len(df) == 0:
        return
    with engine.connect() as conn:
        for _, row in df.iterrows():
            conn.execute(
                text("""
                    INSERT INTO dw.dim_date (date_key, date, day, month, quarter, year, is_weekend)
                    VALUES (:date_key, :date, :day, :month, :quarter, :year, :is_weekend)
                    ON CONFLICT (date_key) DO NOTHING
                """),
                {
                    "date_key": int(row["date_key"]),
                    "date": row["date"],
                    "day": int(row["day"]),
                    "month": int(row["month"]),
                    "quarter": int(row["quarter"]),
                    "year": int(row["year"]),
                    "is_weekend": bool(row["is_weekend"]),
                },
            )
        conn.commit()
    logger.info(f"load_dim_date: {len(df):,} rows loaded")


def load_dim_product(df: pd.DataFrame, engine: Engine) -> pd.DataFrame:
    """
    Load Dim_Product với SCD Type 2.

    Returns:
        pd.DataFrame: Bản ghi current trong DWH sau khi load (dùng để lookup surrogate key).
    """
    if df is None or len(df) == 0:
        logger.info("load_dim_product: no data to load")
        with engine.connect() as conn:
            return pd.read_sql(
                text("SELECT * FROM dw.dim_product WHERE is_current = true"), conn
            )

    with engine.begin() as conn:
        result = _load_dim_scd2(
            conn=conn,
            df=df,
            table="dim_product",
            schema="dw",
            business_key="product_id",
            track_cols=["name", "list_price", "standard_cost"],
        )
    logger.info(f"load_dim_product: {len(df):,} records processed")
    return result


def load_dim_territory(df: pd.DataFrame, engine: Engine) -> pd.DataFrame:
    """
    Load Dim_Territory với SCD Type 1.

    Returns:
        pd.DataFrame: Toàn bộ dim sau khi load.
    """
    if df is None or len(df) == 0:
        logger.info("load_dim_territory: no data to load")
        with engine.connect() as conn:
            return pd.read_sql(text("SELECT * FROM dw.dim_territory"), conn)

    with engine.begin() as conn:
        result = _upsert_dim_scd1(
            conn=conn,
            df=df,
            table="dim_territory",
            schema="dw",
            business_key="territory_id",
            surrogate_key="territory_key",
            update_cols=["territory_name", "country_region", "group_name"],
        )
    logger.info(f"load_dim_territory: {len(df):,} records processed")
    return result


def load_dim_employee(df: pd.DataFrame, engine: Engine) -> pd.DataFrame:
    """
    Load Dim_Employee với SCD Type 1.

    Returns:
        pd.DataFrame: Toàn bộ dim sau khi load.
    """
    if df is None or len(df) == 0:
        logger.info("load_dim_employee: no data to load")
        with engine.connect() as conn:
            return pd.read_sql(text("SELECT * FROM dw.dim_employee"), conn)

    with engine.begin() as conn:
        result = _upsert_dim_scd1(
            conn=conn,
            df=df,
            table="dim_employee",
            schema="dw",
            business_key="employee_id",
            surrogate_key="employee_key",
            update_cols=["full_name", "job_title", "department", "hire_date"],
        )
    logger.info(f"load_dim_employee: {len(df):,} records processed")
    return result


def load_dim_customer(df: pd.DataFrame, engine: Engine) -> pd.DataFrame:
    """
    Load Dim_Customer với SCD Type 1.

    Returns:
        pd.DataFrame: Toàn bộ dim sau khi load.
    """
    if df is None or len(df) == 0:
        logger.info("load_dim_customer: no data to load")
        with engine.connect() as conn:
            return pd.read_sql(text("SELECT * FROM dw.dim_customer"), conn)

    with engine.begin() as conn:
        result = _upsert_dim_scd1(
            conn=conn,
            df=df,
            table="dim_customer",
            schema="dw",
            business_key="customer_id",
            surrogate_key="customer_key",
            update_cols=["full_name", "customer_type", "country", "state_province", "territory_id"],
        )
    logger.info(f"load_dim_customer: {len(df):,} records processed")
    return result


def load_fact_sales(df: pd.DataFrame, engine: Engine) -> int:
    """
    Load Fact_Sales vào DWH. Idempotent (ON CONFLICT DO NOTHING).

    Returns:
        int: Số bản ghi đã load.
    """
    if df is None or len(df) == 0:
        logger.info("load_fact_sales: no data to load")
        return 0

    loaded = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute(
                    text("""
                        INSERT INTO dw.fact_sales (
                            sales_order_detail_id, date_key, product_key, customer_key,
                            territory_key, employee_key, order_qty, unit_price,
                            unit_price_discount, line_total, standard_cost, gross_profit,
                            _load_timestamp
                        ) VALUES (
                            :sales_order_detail_id, :date_key, :product_key, :customer_key,
                            :territory_key, :employee_key, :order_qty, :unit_price,
                            :unit_price_discount, :line_total, :standard_cost, :gross_profit,
                            :_load_timestamp
                        )
                        ON CONFLICT (sales_order_detail_id) DO NOTHING
                    """),
                    {
                        "sales_order_detail_id": int(row["sales_order_detail_id"]),
                        "date_key": int(row["date_key"]),
                        "product_key": int(row["product_key"]),
                        "customer_key": int(row["customer_key"]),
                        "territory_key": int(row["territory_key"]),
                        "employee_key": int(row["employee_key"]) if pd.notna(row["employee_key"]) else None,
                        "order_qty": int(row["order_qty"]),
                        "unit_price": float(row["unit_price"]),
                        "unit_price_discount": float(row["unit_price_discount"]),
                        "line_total": float(row["line_total"]),
                        "standard_cost": float(row["standard_cost"]),
                        "gross_profit": float(row["gross_profit"]),
                        "_load_timestamp": row.get("_load_timestamp", datetime.now()),
                    },
                )
                loaded += 1
            except Exception as e:
                logger.error(f"  Lỗi insert fact_sales row {row.get('sales_order_detail_id')}: {e}")
                raise

    logger.info(f"load_fact_sales: {loaded:,} rows loaded")
    return loaded


def load_fact_inventory(df: pd.DataFrame, engine: Engine) -> int:
    """
    Load Fact_Inventory vào DWH. Idempotent (ON CONFLICT date_key+product_key DO NOTHING).

    Returns:
        int: Số bản ghi đã load.
    """
    if df is None or len(df) == 0:
        logger.info("load_fact_inventory: no data to load")
        return 0

    loaded = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute(
                    text("""
                        INSERT INTO dw.fact_inventory (
                            date_key, product_key, quantity, ordered_qty, scrapped_qty,
                            _load_timestamp
                        ) VALUES (
                            :date_key, :product_key, :quantity, :ordered_qty, :scrapped_qty,
                            :_load_timestamp
                        )
                    """),
                    {
                        "date_key": int(row["date_key"]),
                        "product_key": int(row["product_key"]),
                        "quantity": int(row["quantity"]),
                        "ordered_qty": int(row["ordered_qty"]) if "ordered_qty" in row and pd.notna(row["ordered_qty"]) else None,
                        "scrapped_qty": int(row["scrapped_qty"]) if "scrapped_qty" in row and pd.notna(row["scrapped_qty"]) else None,
                        "_load_timestamp": row.get("_load_timestamp", datetime.now()),
                    },
                )
                loaded += 1
            except Exception as e:
                logger.error(f"  Lỗi insert fact_inventory: {e}")
                raise

    logger.info(f"load_fact_inventory: {loaded:,} rows loaded")
    return loaded
