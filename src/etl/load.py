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
    existing_df = pd.read_sql(
        text(f'SELECT * FROM {schema}."{table}"'),
        conn,
    )

    now = datetime.now()
    BATCH = 1000

    # Merge logic: split incoming rows into insert vs update
    existing_bk = set(existing_df[business_key].values)
    insert_rows = []
    update_rows = []

    for _, row in df.iterrows():
        bk_val = row[business_key]
        if bk_val in existing_bk:
            update_rows.append(row)
        else:
            insert_rows.append(row)

    # Batch INSERT
    if insert_rows:
        insert_batch = []
        for row in insert_rows:
            d = {c: row[c] for c in update_cols + [business_key] if c in row.index}
            d["_load_timestamp"] = now
            insert_batch.append(d)
        for i in range(0, len(insert_batch), BATCH):
            batch = insert_batch[i:i + BATCH]
            cols = ", ".join(f'"{k}"' for k in batch[0].keys())
            placeholders = ", ".join(f":{k}" for k in batch[0].keys())
            conn.execute(
                text(f'INSERT INTO {schema}."{table}" ({cols}) VALUES ({placeholders})'),
                batch,
            )

    # Batch UPDATE
    if update_rows:
        update_batch = []
        sk_values = existing_df.set_index(business_key)[surrogate_key].to_dict()
        for row in update_rows:
            bk_val = row[business_key]
            d = {c: row[c] for c in update_cols if c in row.index}
            d["_load_timestamp"] = now
            d[surrogate_key] = int(sk_values.get(bk_val, 0))
            update_batch.append(d)
        for i in range(0, len(update_batch), BATCH):
            batch = update_batch[i:i + BATCH]
            set_clause = ", ".join(f'"{k}" = :{k}' for k in update_cols + ["_load_timestamp"])
            conn.execute(
                text(f'UPDATE {schema}."{table}" SET {set_clause} WHERE "{surrogate_key}" = :{surrogate_key}'),
                batch,
            )

    logger.info(f"  {schema}.{table} SCD1: {len(insert_rows)} inserted, {len(update_rows)} updated")
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

    # Build lookup: business_key → current row
    current_map = {}
    for _, r in existing_df.iterrows():
        if r["is_current"]:
            current_map[r[business_key]] = r

    now = datetime.now()
    FAR_PAST = datetime(1900, 1, 1)
    BATCH = 1000
    close_batch = []
    insert_batch = []
    inserted = 0
    closed = 0

    for _, row in df.iterrows():
        bk_val = row[business_key]
        curr = current_map.get(bk_val)

        if curr is None:
            insert_batch.append((row, now))
            inserted += 1
        else:
            changed = any(
                str(row[col]) != str(curr[col])
                for col in track_cols
                if col in row.index and col in curr.index
            )
            if changed:
                close_batch.append(int(curr[surrogate_key]))
                insert_batch.append((row, now))
                inserted += 1
                closed += 1

    # Batch close old records
    if close_batch:
        for i in range(0, len(close_batch), BATCH):
            batch = close_batch[i:i + BATCH]
            conn.execute(
                text(f'UPDATE {schema}."{table}" SET valid_to = :vt, is_current = false '
                     f'WHERE "{surrogate_key}" = ANY(:pks)'),
                {"vt": now, "pks": batch},
            )

    # Batch insert new records
    if insert_batch:
        insert_rows = []
        for row, ts in insert_batch:
            d = {
                "product_id": int(row["product_id"]),
                "name": str(row["name"])[:100],
                "subcategory": str(row["subcategory"])[:100] if pd.notna(row.get("subcategory")) else None,
                "category": str(row["category"])[:100] if pd.notna(row.get("category")) else None,
                "list_price": float(row["list_price"]),
                "standard_cost": float(row["standard_cost"]),
                "valid_from": FAR_PAST if existing_df.empty else ts,
                "valid_to": None,
                "is_current": True,
                "_load_timestamp": ts,
            }
            insert_rows.append(d)
        for i in range(0, len(insert_rows), BATCH):
            batch = insert_rows[i:i + BATCH]
            conn.execute(
                text("""
                    INSERT INTO dw.dim_product
                        (product_id, name, subcategory, category, list_price, standard_cost,
                         valid_from, valid_to, is_current, _load_timestamp)
                    VALUES
                        (:product_id, :name, :subcategory, :category, :list_price, :standard_cost,
                         :valid_from, :valid_to, :is_current, :_load_timestamp)
                """),
                batch,
            )

    logger.info(f"  {schema}.{table} SCD2: {inserted} inserted, {closed} closed")
    return pd.read_sql(text(f'SELECT * FROM {schema}."{table}"'), conn)


# ---------------------------------------------------------------------------
# Public load functions (dùng trong pipeline)
# ---------------------------------------------------------------------------

def load_dim_date(df: pd.DataFrame, engine: Engine, conn: Connection = None) -> None:
    """Load Dim_Date vào DWH. INSERT ON CONFLICT DO NOTHING (idempotent).
    Luôn insert nếu date_key chưa tồn tại (không skip khi bảng đã có dữ liệu).

    Args:
        conn: Nếu được cung cấp, dùng connection này (cho single-transaction pipeline).
              Nếu None, tự tạo transaction riêng.
    """
    if df is None or len(df) == 0:
        return

    def _do_load(c: Connection):
        records = df.to_dict("records")
        BATCH = 1000
        for i in range(0, len(records), BATCH):
            batch = records[i:i + BATCH]
            c.execute(
                text("""
                    INSERT INTO dw.dim_date (date_key, date, day, month, quarter, year, is_weekend)
                    VALUES (:date_key, :date, :day, :month, :quarter, :year, :is_weekend)
                    ON CONFLICT (date_key) DO NOTHING
                """),
                batch,
            )

    if conn is not None:
        _do_load(conn)
    else:
        with engine.begin() as c:
            _do_load(c)
    logger.info(f"load_dim_date: {len(df):,} rows processed")


def load_dim_product(df: pd.DataFrame, engine: Engine, conn: Connection = None) -> pd.DataFrame:
    """
    Load Dim_Product với SCD Type 2.

    Args:
        conn: Nếu được cung cấp, dùng connection này (single-transaction pipeline).

    Returns:
        pd.DataFrame: Tất cả bản ghi dim_product (cho surrogate key lookup với valid range).
    """
    if df is None or len(df) == 0:
        logger.info("load_dim_product: no data to load")
        db_conn = conn if conn is not None else engine.connect()
        return pd.read_sql(text("SELECT * FROM dw.dim_product"), db_conn)

    def _do_load(c: Connection):
        return _load_dim_scd2(
            conn=c,
            df=df,
            table="dim_product",
            schema="dw",
            business_key="product_id",
            track_cols=["name", "list_price", "standard_cost"],
        )

    if conn is not None:
        result = _do_load(conn)
    else:
        with engine.begin() as c:
            result = _do_load(c)

    logger.info(f"load_dim_product: {len(df):,} records processed")
    return result


def load_dim_territory(df: pd.DataFrame, engine: Engine, conn: Connection = None) -> pd.DataFrame:
    if df is None or len(df) == 0:
        logger.info("load_dim_territory: no data to load")
        db_conn = conn if conn is not None else engine.connect()
        return pd.read_sql(text("SELECT * FROM dw.dim_territory"), db_conn)

    def _do_load(c: Connection):
        return _upsert_dim_scd1(
            conn=c, df=df, table="dim_territory", schema="dw",
            business_key="territory_id", surrogate_key="territory_key",
            update_cols=["territory_name", "country_region", "group_name"],
        )

    if conn is not None:
        result = _do_load(conn)
    else:
        with engine.begin() as c:
            result = _do_load(c)
    logger.info(f"load_dim_territory: {len(df):,} records processed")
    return result


def load_dim_employee(df: pd.DataFrame, engine: Engine, conn: Connection = None) -> pd.DataFrame:
    if df is None or len(df) == 0:
        logger.info("load_dim_employee: no data to load")
        db_conn = conn if conn is not None else engine.connect()
        return pd.read_sql(text("SELECT * FROM dw.dim_employee"), db_conn)

    def _do_load(c: Connection):
        return _upsert_dim_scd1(
            conn=c, df=df, table="dim_employee", schema="dw",
            business_key="employee_id", surrogate_key="employee_key",
            update_cols=["full_name", "job_title", "department", "hire_date"],
        )

    if conn is not None:
        result = _do_load(conn)
    else:
        with engine.begin() as c:
            result = _do_load(c)
    logger.info(f"load_dim_employee: {len(df):,} records processed")
    return result


def load_dim_customer(df: pd.DataFrame, engine: Engine, conn: Connection = None) -> pd.DataFrame:
    if df is None or len(df) == 0:
        logger.info("load_dim_customer: no data to load")
        db_conn = conn if conn is not None else engine.connect()
        return pd.read_sql(text("SELECT * FROM dw.dim_customer"), db_conn)

    def _do_load(c: Connection):
        return _upsert_dim_scd1(
            conn=c, df=df, table="dim_customer", schema="dw",
            business_key="customer_id", surrogate_key="customer_key",
            update_cols=["full_name", "customer_type", "country", "territory_id"],
        )

    if conn is not None:
        result = _do_load(conn)
    else:
        with engine.begin() as c:
            result = _do_load(c)
    logger.info(f"load_dim_customer: {len(df):,} records processed")
    return result


def _do_load_fact_sales(df: pd.DataFrame, conn: Connection) -> int:
    """Helper: load fact_sales rows using an existing connection."""
    df["_load_timestamp"] = df.get("_load_timestamp", datetime.now())
    mask_ek = df["employee_key"].notna()
    df["employee_key"] = df["employee_key"].astype(object)
    df.loc[mask_ek, "employee_key"] = df.loc[mask_ek, "employee_key"].astype(int)
    df.loc[~mask_ek, "employee_key"] = None

    records = df.to_dict("records")
    BATCH = 1000
    for i in range(0, len(records), BATCH):
        batch = records[i:i + BATCH]
        try:
            conn.execute(
                text("""
                    INSERT INTO dw.fact_sales (
                        sales_order_detail_id, sales_order_id, date_key, product_key, customer_key,
                        territory_key, employee_key, order_qty, unit_price,
                        unit_price_discount, line_total, standard_cost, gross_profit,
                        _load_timestamp
                    ) VALUES (
                        :sales_order_detail_id, :sales_order_id, :date_key, :product_key, :customer_key,
                        :territory_key, :employee_key, :order_qty, :unit_price,
                        :unit_price_discount, :line_total, :standard_cost, :gross_profit,
                        :_load_timestamp
                    )
                    ON CONFLICT (sales_order_detail_id) DO NOTHING
                """),
                batch,
            )
        except Exception as e:
            logger.error(f"  Lỗi batch insert fact_sales (rows {i}–{i + len(batch)}): {e}")
            raise
    return len(records)


def load_fact_sales(df: pd.DataFrame, engine: Engine, conn: Connection = None) -> int:
    if df is None or len(df) == 0:
        logger.info("load_fact_sales: no data to load")
        return 0

    if conn is not None:
        loaded = _do_load_fact_sales(df, conn)
    else:
        with engine.begin() as c:
            loaded = _do_load_fact_sales(df, c)
    logger.info(f"load_fact_sales: {loaded:,} rows loaded")
    return loaded


def _do_load_fact_inventory(df: pd.DataFrame, conn: Connection) -> int:
    """Helper: load fact_inventory rows using an existing connection."""
    records = df.to_dict("records")
    BATCH = 1000
    loaded = 0
    for i in range(0, len(records), BATCH):
        batch = records[i:i + BATCH]
        for r in batch:
            r["date_key"] = int(r["date_key"])
            r["product_key"] = int(r["product_key"])
            r["location_id"] = int(r["location_id"]) if pd.notna(r.get("location_id")) else None
            r["quantity"] = int(r["quantity"])
            r["_load_timestamp"] = r.get("_load_timestamp", datetime.now())
        try:
            conn.execute(
                text("""
                    INSERT INTO dw.fact_inventory (
                        date_key, product_key, location_id, quantity,
                        _load_timestamp
                    ) VALUES (
                        :date_key, :product_key, :location_id, :quantity,
                        :_load_timestamp
                    )
                    ON CONFLICT (product_key, date_key, COALESCE(location_id, -1)) DO NOTHING
                """),
                batch,
            )
            loaded += len(batch)
        except Exception as e:
            logger.error(f"  Lỗi batch insert fact_inventory (rows {i}–{i + len(batch)}): {e}")
            raise
    return loaded


def load_fact_inventory(df: pd.DataFrame, engine: Engine, conn: Connection = None) -> int:
    if df is None or len(df) == 0:
        logger.info("load_fact_inventory: no data to load")
        return 0

    if conn is not None:
        loaded = _do_load_fact_inventory(df, conn)
    else:
        with engine.begin() as c:
            loaded = _do_load_fact_inventory(df, c)
    logger.info(f"load_fact_inventory: {loaded:,} rows loaded")
    return loaded


def refresh_daily_sales_agg(engine: Engine, conn: Connection = None) -> None:
    """Refresh mart.daily_sales_agg từ fact_sales + dim_date."""
    def _do(c: Connection):
        c.execute(text("DELETE FROM mart.daily_sales_agg"))
        c.execute(text("""
            INSERT INTO mart.daily_sales_agg
                (date_key, date, year, quarter, month,
                 order_count, item_count, total_qty,
                 revenue, gross_profit, customer_count)
            SELECT
                f.date_key,
                d.date,
                d.year,
                d.quarter,
                d.month,
                COUNT(DISTINCT f.sales_order_id) AS order_count,
                COUNT(DISTINCT f.sales_order_detail_id) AS item_count,
                SUM(f.order_qty) AS total_qty,
                SUM(f.line_total) AS revenue,
                SUM(f.gross_profit) AS gross_profit,
                COUNT(DISTINCT f.customer_key) AS customer_count
            FROM dw.fact_sales f
            JOIN dw.dim_date d ON f.date_key = d.date_key
            GROUP BY f.date_key, d.date, d.year, d.quarter, d.month
        """))

    if conn is not None:
        _do(conn)
    else:
        with engine.begin() as c:
            _do(c)
    logger.info("refresh_daily_sales_agg: mart.daily_sales_agg refreshed")
