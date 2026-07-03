"""Script khởi tạo schema và tables trong PostgreSQL DWH.

Chạy: python scripts/init_dw_tables.py

WARNING: Giữ đồng bộ với sql/ddl_script.sql.
CI sẽ kiểm tra số lượng bảng giữa 2 file.
"""
from dotenv import load_dotenv
load_dotenv()

from src.config import load_postgres_settings
from sqlalchemy import create_engine, text

DDL_SCRIPT = """
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;

-- 1. Dim_Date
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key INT PRIMARY KEY,
    date DATE NOT NULL,
    day INT NOT NULL,
    month INT NOT NULL,
    quarter INT NOT NULL,
    year INT NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- 2. Dim_Product (SCD Type 2)
CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_key SERIAL PRIMARY KEY,
    product_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    category VARCHAR(100),
    list_price NUMERIC(15,2) NOT NULL,
    standard_cost NUMERIC(15,2) NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    is_current BOOLEAN NOT NULL,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Dim_Customer (SCD Type 1)
CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_key SERIAL PRIMARY KEY,
    customer_id INT NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    customer_type VARCHAR(50) NOT NULL,
    country VARCHAR(100),
    state_province VARCHAR(100),
    territory_id INT,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Dim_Territory (SCD Type 1)
CREATE TABLE IF NOT EXISTS dw.dim_territory (
    territory_key SERIAL PRIMARY KEY,
    territory_id INT NOT NULL,
    territory_name VARCHAR(100) NOT NULL,
    country_region VARCHAR(100) NOT NULL,
    group_name VARCHAR(100) NOT NULL,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Dim_Employee (SCD Type 1)
CREATE TABLE IF NOT EXISTS dw.dim_employee (
    employee_key SERIAL PRIMARY KEY,
    employee_id INT NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    job_title VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    hire_date DATE NOT NULL,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Fact_Sales
CREATE TABLE IF NOT EXISTS dw.fact_sales (
    sales_order_detail_id INT PRIMARY KEY,
    sales_order_id INT NOT NULL,
    date_key INT NOT NULL REFERENCES dw.dim_date(date_key),
    product_key INT NOT NULL REFERENCES dw.dim_product(product_key),
    customer_key INT NOT NULL REFERENCES dw.dim_customer(customer_key),
    territory_key INT NOT NULL REFERENCES dw.dim_territory(territory_key),
    employee_key INT REFERENCES dw.dim_employee(employee_key),
    order_qty INT NOT NULL,
    unit_price NUMERIC(15,2) NOT NULL,
    unit_price_discount NUMERIC(15,2) NOT NULL,
    line_total NUMERIC(15,2) NOT NULL,
    standard_cost NUMERIC(15,2) NOT NULL,
    gross_profit NUMERIC(15,2) NOT NULL,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Fact_Inventory
CREATE TABLE IF NOT EXISTS dw.fact_inventory (
    inventory_id SERIAL PRIMARY KEY,
    date_key INT NOT NULL REFERENCES dw.dim_date(date_key),
    product_key INT NOT NULL REFERENCES dw.dim_product(product_key),
    location_id INT,
    quantity INT NOT NULL,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_inventory
    ON dw.fact_inventory(product_key, date_key, COALESCE(location_id, -1));

-- Index tối ưu query cho Fact_Sales
CREATE INDEX IF NOT EXISTS idx_fact_sales_date_key     ON dw.fact_sales(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_product_key  ON dw.fact_sales(product_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_customer_key ON dw.fact_sales(customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_territory_key ON dw.fact_sales(territory_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_employee_key ON dw.fact_sales(employee_key);

-- Index tối ưu query cho Fact_Inventory
CREATE INDEX IF NOT EXISTS idx_fact_inv_date_key    ON dw.fact_inventory(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_inv_product_key ON dw.fact_inventory(product_key);

-- Index cho Dim_Product SCD2 lookup
CREATE INDEX IF NOT EXISTS idx_dim_product_id_current ON dw.dim_product(product_id, is_current);

-- Index cho Dim_Customer lookup
CREATE INDEX IF NOT EXISTS idx_dim_customer_id ON dw.dim_customer(customer_id);

-- Index cho Dim_Territory lookup
CREATE INDEX IF NOT EXISTS idx_dim_territory_id ON dw.dim_territory(territory_id);

-- Index cho Dim_Employee lookup
CREATE INDEX IF NOT EXISTS idx_dim_employee_id ON dw.dim_employee(employee_id);

-- ===========================================================================
-- MART SCHEMA: Snapshot Layer cho Time-series Analysis
-- ===========================================================================

CREATE TABLE IF NOT EXISTS mart.kpi_snapshot (
    snapshot_id   SERIAL PRIMARY KEY,
    kpi_name      VARCHAR(100) NOT NULL,
    period_type   VARCHAR(10) NOT NULL,
    period_key    VARCHAR(10) NOT NULL,
    period_start  DATE NOT NULL,
    period_end    DATE NOT NULL,
    value         NUMERIC(18,4),
    dimension     VARCHAR(50)  DEFAULT 'overall',
    dimension_value VARCHAR(100) DEFAULT 'overall',
    row_count     INT,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    etl_batch_id  VARCHAR(50),
    UNIQUE (kpi_name, period_type, period_key, dimension, dimension_value)
);

CREATE TABLE IF NOT EXISTS mart.rfm_snapshot (
    snapshot_id   SERIAL PRIMARY KEY,
    period_key    VARCHAR(10) NOT NULL,
    period_start  DATE NOT NULL,
    period_end    DATE NOT NULL,
    cluster_label VARCHAR(50) NOT NULL,
    customer_count INT NOT NULL,
    avg_recency   NUMERIC(10,2),
    avg_frequency NUMERIC(10,2),
    avg_monetary  NUMERIC(15,2),
    total_monetary NUMERIC(15,2),
    pct_of_total  NUMERIC(5,2),
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (period_key, cluster_label)
);

CREATE TABLE IF NOT EXISTS mart.customer_migration (
    migration_id    SERIAL PRIMARY KEY,
    customer_key    INT NOT NULL,
    prev_period_key VARCHAR(10) NOT NULL,
    curr_period_key VARCHAR(10) NOT NULL,
    prev_cluster    VARCHAR(50),
    curr_cluster    VARCHAR(50),
    prev_monetary   NUMERIC(15,2),
    curr_monetary   NUMERIC(15,2),
    is_churned      BOOLEAN DEFAULT FALSE,
    is_new          BOOLEAN DEFAULT FALSE,
    calculated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (customer_key, prev_period_key, curr_period_key)
);

CREATE TABLE IF NOT EXISTS mart.inventory_snapshot (
    snapshot_id          SERIAL PRIMARY KEY,
    period_key           VARCHAR(10) NOT NULL,
    period_start         DATE NOT NULL,
    period_end           DATE NOT NULL,
    product_key          INT NOT NULL,
    avg_quantity         NUMERIC(15,2),
    avg_inventory_value  NUMERIC(15,2),
    avg_dio              NUMERIC(10,2),
    anomaly_count        INT DEFAULT 0,
    anomaly_score_avg    NUMERIC(12,6),
    calculated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (period_key, product_key)
);

CREATE TABLE IF NOT EXISTS mart.daily_sales_agg (
    date_key INT PRIMARY KEY,
    date DATE NOT NULL,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month INT NOT NULL,
    order_count INT NOT NULL,
    item_count INT NOT NULL,
    total_qty INT NOT NULL,
    revenue NUMERIC(18,2) NOT NULL,
    gross_profit NUMERIC(18,2) NOT NULL,
    customer_count INT NOT NULL,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mart.period_comparison (
    comparison_id    SERIAL PRIMARY KEY,
    kpi_name         VARCHAR(100) NOT NULL,
    curr_period_key  VARCHAR(10) NOT NULL,
    prev_period_key  VARCHAR(10) NOT NULL,
    dimension        VARCHAR(50) DEFAULT 'overall',
    dimension_value  VARCHAR(100) DEFAULT 'overall',
    curr_value       NUMERIC(18,4),
    prev_value       NUMERIC(18,4),
    abs_change       NUMERIC(18,4),
    pct_change       NUMERIC(10,4),
    contribution_pct NUMERIC(10,4),
    is_significant   BOOLEAN,
    p_value          NUMERIC(10,6),
    effect_size      NUMERIC(10,4),
    calculated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (kpi_name, curr_period_key, prev_period_key, dimension, dimension_value)
);

CREATE INDEX IF NOT EXISTS idx_kpi_snapshot_name_period ON mart.kpi_snapshot(kpi_name, period_key);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshot_period_type ON mart.kpi_snapshot(period_type, period_key);
CREATE INDEX IF NOT EXISTS idx_rfm_snapshot_period ON mart.rfm_snapshot(period_key);
CREATE INDEX IF NOT EXISTS idx_customer_migration_curr ON mart.customer_migration(curr_period_key);
CREATE INDEX IF NOT EXISTS idx_customer_migration_key ON mart.customer_migration(customer_key);
CREATE INDEX IF NOT EXISTS idx_inventory_snapshot_period ON mart.inventory_snapshot(period_key);
CREATE INDEX IF NOT EXISTS idx_period_comparison_kpi ON mart.period_comparison(kpi_name, curr_period_key);

CREATE TABLE IF NOT EXISTS dw.ml_inventory_anomaly (
    product_key INT NOT NULL,
    product_name VARCHAR(100),
    category VARCHAR(100),
    subcategory VARCHAR(100),
    avg_quantity NUMERIC(15,2),
    std_quantity NUMERIC(15,2),
    max_quantity NUMERIC(15,2),
    inventory_value NUMERIC(15,2),
    units_sold NUMERIC(15,2),
    days_inventory_outstanding NUMERIC(15,2),
    anomaly_flag BOOLEAN NOT NULL,
    anomaly_score NUMERIC(12,6),
    zero_sales_flag BOOLEAN NOT NULL DEFAULT FALSE,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_dw_tables():
    s = load_postgres_settings()
    engine = create_engine(s.connection_string())

    print("=" * 55)
    print("  Khoi tao Data Warehouse Schema & Tables")
    print(f"  DB: {s.host}:{s.port}/{s.name}")
    print("=" * 55)

    # Tach tung statement - bo comment lines truoc
    raw_statements = DDL_SCRIPT.split(";")
    statements = []
    for raw in raw_statements:
        # Bo dong comment, giu cac dong SQL thuc su
        lines = [ln for ln in raw.split("\n") if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)

    # Chay tung statement trong transaction rieng de tranh cascade abort
    for stmt in statements:
        first_line = next(
            (ln.strip() for ln in stmt.split("\n") if ln.strip()),
            ""
        )
        if not first_line:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            print(f"  OK: {first_line[:70]}")
        except Exception as e:
            err_msg = str(e).split("\n")[0][:80]
            print(f"  SKIP: {first_line[:50]} => {err_msg}")

    print()
    print("Ket qua - Tables trong DWH:")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('dw', 'staging')
            ORDER BY table_schema, table_name
        """))
        rows = result.fetchall()
        for schema, tbl in rows:
            print(f"  {schema}.{tbl}")

    print()
    print("Ket qua - Indexes tren DW schema:")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT indexname, tablename
            FROM pg_indexes
            WHERE schemaname = 'dw'
            ORDER BY tablename, indexname
        """))
        rows = result.fetchall()
        for idx_name, tbl in rows:
            print(f"  {tbl}: {idx_name}")

    print()
    print("Hoan tat khoi tao DWH tables.")


if __name__ == "__main__":
    init_dw_tables()
