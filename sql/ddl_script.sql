-- WARNING: Giữ đồng bộ với scripts/init_dw_tables.py.
-- CI sẽ kiểm tra số lượng bảng giữa 2 file.
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;

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

-- 7. Fact_Inventory (Bảng sự kiện hàng tồn kho snapshot)
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
    zero_sales_flag BOOLEAN NOT NULL DEFAULT FALSE,
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

-- 12. Mart KPI Snapshot: Lưu KPI theo từng kỳ (quý/tháng/năm)
CREATE TABLE IF NOT EXISTS mart.kpi_snapshot (
    snapshot_id   SERIAL PRIMARY KEY,
    kpi_name      VARCHAR(100) NOT NULL,
    period_type   VARCHAR(10) NOT NULL,   -- 'Q', 'M', 'Y'
    period_key    VARCHAR(10) NOT NULL,   -- '2024Q1', '202401', '2024'
    period_start  DATE NOT NULL,
    period_end    DATE NOT NULL,
    value         NUMERIC(18,4),
    dimension     VARCHAR(50)  DEFAULT 'overall',    -- 'territory', 'category', 'customer_type', ...
    dimension_value VARCHAR(100) DEFAULT 'overall',
    row_count     INT,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    etl_batch_id  VARCHAR(50),

    UNIQUE (kpi_name, period_type, period_key, dimension, dimension_value)
);

-- 13. Mart RFM Snapshot: RFM cluster distribution theo từng kỳ
CREATE TABLE IF NOT EXISTS mart.rfm_snapshot (
    snapshot_id   SERIAL PRIMARY KEY,
    period_key    VARCHAR(10) NOT NULL,    -- '2024Q1'
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

-- 14. Mart Customer Migration: Tracking khách hàng chuyển cluster
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

-- 15. Mart Period Comparison: So sánh period-over-period
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

-- Daily aggregated sales table (KPI performance — refresh from pipeline)
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

-- Indexes cho fact tables (query performance)
CREATE INDEX IF NOT EXISTS idx_fact_sales_date ON dw.fact_sales(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_date_product ON dw.fact_sales(date_key, product_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_date_territory ON dw.fact_sales(date_key, territory_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_product_date ON dw.fact_sales(product_key, date_key);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_product_date ON dw.fact_inventory(product_key, date_key);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_product_location_date ON dw.fact_inventory(product_key, location_id, date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_customer ON dw.fact_sales(customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_employee ON dw.fact_sales(employee_key);

-- Indexes cho mart schema
CREATE INDEX IF NOT EXISTS idx_kpi_snapshot_name_period ON mart.kpi_snapshot(kpi_name, period_key);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshot_period_type ON mart.kpi_snapshot(period_type, period_key);
CREATE INDEX IF NOT EXISTS idx_rfm_snapshot_period ON mart.rfm_snapshot(period_key);
CREATE INDEX IF NOT EXISTS idx_customer_migration_curr ON mart.customer_migration(curr_period_key);
CREATE INDEX IF NOT EXISTS idx_customer_migration_key ON mart.customer_migration(customer_key);
CREATE INDEX IF NOT EXISTS idx_period_comparison_kpi ON mart.period_comparison(kpi_name, curr_period_key);

