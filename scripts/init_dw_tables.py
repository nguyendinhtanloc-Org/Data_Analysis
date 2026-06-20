"""Script khởi tạo schema và tables trong PostgreSQL DWH.

Chạy: python scripts/init_dw_tables.py
"""
import sys
import os

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.config import load_postgres_settings
from sqlalchemy import create_engine, text

DDL_SCRIPT = """
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS staging;

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
    quantity INT NOT NULL,
    ordered_qty INT,
    scrapped_qty INT,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
