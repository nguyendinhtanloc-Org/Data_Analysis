-- DDL script khởi tạo schema và các bảng cho Data Warehouse (PostgreSQL)
-- Được thiết kế bởi Data Architect (Thành viên A)

CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS staging;

-- 1. Dim_Date (Bảng chiều thời gian)
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key INT PRIMARY KEY, -- YYYYMMDD
    date DATE NOT NULL,
    day INT NOT NULL,
    month INT NOT NULL,
    quarter INT NOT NULL,
    year INT NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- 2. Dim_Product (Bảng chiều sản phẩm - SCD Type 2)
CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_key SERIAL PRIMARY KEY,
    product_id INT NOT NULL, -- Business Key gốc từ AdventureWorks
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

-- 3. Dim_Customer (Bảng chiều khách hàng - SCD Type 1)
CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_key SERIAL PRIMARY KEY,
    customer_id INT NOT NULL, -- Business Key gốc
    full_name VARCHAR(200) NOT NULL,
    customer_type VARCHAR(50) NOT NULL,
    country VARCHAR(100),
    state_province VARCHAR(100),
    territory_id INT,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Dim_Territory (Bảng chiều khu vực kinh doanh - SCD Type 1)
CREATE TABLE IF NOT EXISTS dw.dim_territory (
    territory_key SERIAL PRIMARY KEY,
    territory_id INT NOT NULL, -- Business Key gốc
    territory_name VARCHAR(100) NOT NULL,
    country_region VARCHAR(100) NOT NULL,
    group_name VARCHAR(100) NOT NULL,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Dim_Employee (Bảng chiều nhân viên bán hàng - SCD Type 1)
CREATE TABLE IF NOT EXISTS dw.dim_employee (
    employee_key SERIAL PRIMARY KEY,
    employee_id INT NOT NULL, -- Business Key gốc
    full_name VARCHAR(200) NOT NULL,
    job_title VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    hire_date DATE NOT NULL,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Fact_Sales (Bảng sự kiện doanh thu bán hàng)
CREATE TABLE IF NOT EXISTS dw.fact_sales (
    sales_order_detail_id INT PRIMARY KEY, -- Business Key
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

-- 7. Fact_Inventory (Bảng sự kiện hàng tồn kho snapshot)
CREATE TABLE IF NOT EXISTS dw.fact_inventory (
    inventory_id SERIAL PRIMARY KEY,
    date_key INT NOT NULL REFERENCES dw.dim_date(date_key),
    product_key INT NOT NULL REFERENCES dw.dim_product(product_key),
    quantity INT NOT NULL,
    ordered_qty INT,
    scrapped_qty INT,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. ML Customer Segments (K-Means on RFM)
CREATE TABLE IF NOT EXISTS dw.ml_customer_segments (
    customer_key INT NOT NULL,
    full_name VARCHAR(200),
    recency_days INT NOT NULL,
    frequency INT NOT NULL,
    monetary NUMERIC(15,2) NOT NULL,
    cluster_id INT NOT NULL,
    cluster_label VARCHAR(50) NOT NULL,
    silhouette_score NUMERIC(10,6),
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. ML Customer Clustering Metrics
CREATE TABLE IF NOT EXISTS dw.ml_customer_clustering_metrics (
    k INT NOT NULL,
    silhouette_score NUMERIC(10,6),
    inertia NUMERIC(20,6),
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. ML Inventory Anomaly Detection
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
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. Decision Support Recommendations
CREATE TABLE IF NOT EXISTS dw.decision_support (
    entity_type VARCHAR(50) NOT NULL,
    entity_key INT NOT NULL,
    signal_type VARCHAR(100) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    recommended_action TEXT NOT NULL,
    reason TEXT,
    _load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

