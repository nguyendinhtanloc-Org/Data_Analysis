# Data Warehouse & Business Analytics với Integrated Machine Learning

Dự án xây dựng **Kho dữ liệu (Data Warehouse)** dạng Star Schema kết hợp **Machine Learning** (K-Means RFM, Isolation Forest) và **Advanced Analytics** (Causal Inference, Contribution Analysis, Drill-down Diagnosis, Early Warning System) để phân tích hiệu quả kinh doanh toàn diện.

---

## 🏗️ Kiến trúc tổng thể

```
MSSQL (AdventureWorks)                    PostgreSQL (DWH)
┌──────────────────────┐    ETL Pipeline    ┌──────────────────────┐
│ Sales.SalesOrderDet  │ ────────────────→ │ dw.fact_sales        │
│ Production.Product   │                   │ dw.fact_inventory    │
│ Sales.Customer       │                   ├──────────────────────┤
│ Sales.SalesTerritory │                   │ dw.dim_date          │
│ HumanResources.Emp   │                   │ dw.dim_product (SCD2)│
│ Production.ProductInv│                   │ dw.dim_customer      │
└──────────────────────┘                   │ dw.dim_territory     │
                                           │ dw.dim_employee      │
                                           ├──────────────────────┤
                                           │ dw.ml_customer_seg   │
                                           │ dw.ml_inventory_any  │
                                           │ dw.decision_support  │
                                           ├──────────────────────┤
                                           │ mart.kpi_snapshot    │ ← MỚI
                                           │ mart.rfm_snapshot    │ ← MỚI
                                           │ mart.customer_migr.  │ ← MỚI
                                           │ mart.period_compare  │ ← MỚI
                                            └──────────────────────┘
                                                      │
                                           ┌───────────┴───────────┐
                                           │    Metabase BI        │
                                           │  (3 Dashboards)       │
                                           └───────────────────────┘
```

---

## 🚀 Quick Start

### 1. Thiết lập cấu hình

```bash
# Sao chép cấu hình
cp .env.example .env
# Sửa file .env — đặc biệt là MSSQL_PASSWORD (mạnh: >=8 ký tự, hoa+thường+số+đb)
```

> **Lưu ý**: Project chạy **hoàn toàn trên Docker**. Không cần cài Python local hay virtualenv.
> Container `etl` đã có sẵn đầy đủ dependencies (Python 3.11 + pandas + scikit-learn + statsmodels...).

### 2. Build & Khởi động hạ tầng

```bash
# Build image ETL (chạy 1 lần đầu hoặc khi thêm dependency)
make build

# Khởi động Docker (Postgres + MSSQL + Metabase + ETL)
make up

# Tạo database + restore dữ liệu mẫu
make init-db
make restore-db

# Kiểm tra kết nối
make test-conn
```

### 3. Chạy ETL Pipeline

```bash
# Full load (lần đầu)
make etl-full

# Incremental load (các lần sau)
make etl
```

### 4. Chạy Machine Learning

```bash
make ml              # Chạy toàn bộ ML pipeline
```

### 5. Chạy Analytics & Snapshot

> **Lưu ý**: Dữ liệu AdventureWorks chỉ có từ 2010-2014. Dùng `period=2014Q2` (có data) thay vì 2024Q4 (rỗng).

```bash
# Snapshot KPI (tự động tính các kỳ chưa có)
make snapshot

# Phân tích đóng góp (ví dụ Q2/2014 vs Q1/2014)
make analytics-contribution period=2014Q2

# Drill-down diagnosis: Overall → Category → Subcategory → Product
make analytics-drilldown period=2014Q2

# Causal inference (Price Elasticity - ko cần period)
make analytics-causal

# Toàn bộ analytics
make analytics-all period=2014Q2
```

### 6. Chạy phân tích nâng cao

```bash
# Customer Migration (RFM theo từng quý 2013-2014)
make ml-migration

# Early Warning System (churn risk + inventory risk)
make ml-early-warning

# Decision Support (Insight Engine tổng hợp)
make ml-decision
```

---

## 📚 Tài liệu chi tiết

### ETL Pipeline (`src/etl/`)
| Module | Chức năng |
|---|---|
| `extract.py` | Trích xuất dữ liệu từ MSSQL với incremental watermark |
| `transform.py` | Chuẩn hóa, DQ rules, sinh surrogate key, gross_profit |
| `load.py` | Load vào PostgreSQL, SCD Type 1 & 2, idempotent insert |
| `pipeline.py` | Điều phối toàn bộ pipeline 7 bước (extract → transform → validate → load dims → load facts → validate → snapshot) |
| `validation.py` | 3-layer validation (pre-load, post-load, cross-check) |
| `etl.py` | CLI entry point với các flag `--full`, `--reset`, `--snapshot`, `--analytics` |

### Machine Learning (`src/ml/`)
| Module | Chức năng |
|---|---|
| `clustering.py` | K-Means RFM Customer Segmentation (Silhouette score, auto K) |
| `anomaly.py` | Isolation Forest Inventory Anomaly Detection |
| `decision_support.py` | **Insight Engine**: Tổng hợp từ ML + KPI snapshot + migration |
| `migration.py` | **Customer Migration**: RFM từng quý, tracking cluster churn/new/downgraded |
| `early_warning.py` | **Early Warning**: Phát hiện churn risk, inventory risk từ leading indicators |

### Advanced Analytics (`src/analytics/`)
| Module | Chức năng |
|---|---|
| `kpi_calculator.py` | **KPI Engine**: Tính 7+ KPI với time-bound, hỗ trợ dimension |
| `snapshot_manager.py` | **Snapshot Manager**: Auto-detect kỳ mới, UPSERT vào mart schema |
| `contribution.py` | **Contribution Analysis**: Phân rã ΔKPI = Σ(weight×Δrate) + mix effect |
| `drill_down.py` | **Drill-down**: Overall → Category → Subcategory → Product |
| `insight_generator.py` | **Insight Generator**: Tự động sinh text: phát hiện → nguyên nhân → evidence → đề xuất |
| `causal.py` | **Causal Inference**: Difference-in-Differences, Price Elasticity (log-log) |
| `hypothesis_tester.py` | **Statistical Tests**: t-test, Chi-square, Mann-Kendall trend, Cohen's d |

### Mart Layer (`mart` schema)
| Table | Chức năng |
|---|---|
| `mart.kpi_snapshot` | Lưu KPI time-series theo quý/tháng/năm (unique: kpi + period + dimension) |
| `mart.rfm_snapshot` | RFM cluster distribution từng kỳ |
| `mart.customer_migration` | Tracking từng KH di chuyển giữa cluster qua các kỳ |
| `mart.period_comparison` | Period-over-period comparison với p-value và effect size |

---

## 📊 Metabase Dashboards

Sau khi chạy ETL + ML + Analytics, mở Metabase tại `http://localhost:3000`.

3 dashboards chính:
1. **Business Performance Overview** (KPI time-series từ `mart.kpi_snapshot`)
2. **Product & Customer Analytics** (RFM segments + migration từ `mart.*`)
3. **Inventory & Operational Decision Support** (anomalies + early warning)

---

## 🔬 Phân tích sâu - Root Cause Analysis

Hệ thống hỗ trợ **4 tầng phân tích nguyên nhân**:

```
Tầng 1: Phát hiện vấn đề
  └─ KPI snapshot → trend anomaly (tăng/giảm đột biến >20%)

Tầng 2: Xác định yếu tố ảnh hưởng
  └─ Contribution Analysis → "Clothing đóng góp -60% vào Δmargin"

Tầng 3: Truy nguyên gốc rễ
  └─ Drill-down: Clothing → Sport Vest → "Discount từ 5% → 25%"

Tầng 4: Kiểm chứng nhân quả
  └─ Causal Inference (DiD, Price Elasticity) — bị disable mặc định do AdventureWorks
     không đủ biến động giá. Bỏ comment trong runner.py nếu dùng dữ liệu thật.
```

---

## 🧪 Các giả thuyết thống kê (Hypothesis Testing)

| Hypothesis | Test | Expected |
|---|---|---|
| H1: Discount có thực sự làm tăng doanh thu? | DiD | p < 0.05 |
| H2: Phân phối cluster thay đổi theo thời gian? | Chi-square | p < 0.05 |
| H3: Giá tăng → Demand giảm? | Log-log regression | PED < 0 |
| H4: Doanh thu Q4 cao hơn Q1 có ý nghĩa? | t-test + Cohen's d | p < 0.05, d > 0.5 |
| H5: Doanh thu có xu hướng tăng theo năm? | Mann-Kendall | τ > 0, p < 0.05 |

---

## 🐳 Docker

| Service | Image | Port | Chức năng |
|---|---|---|---|
| `postgres` | postgres:15 | 5432 | Data Warehouse |
| `mssql` | mssql:2022 | 1433 | OLTP Source (AdventureWorks) |
| `etl` | python:3.11-slim | - | ETL + ML + Analytics container |
| `metabase` | metabase:v0.50.1 | 3000 | BI Dashboard |

---

## 📁 Cấu trúc thư mục

```
.
├── config.json              # Watermark + snapshot watermark
├── docker-compose.yml       # 4 services
├── Dockerfile
├── Makefile                 # 30+ targets
├── pyproject.toml
├── requirements.txt
├── .env.example
│
├── data/
│   ├── raw/        (AdventureWorks2022.bak)
│   ├── processed/
│   └── external/
│
├── sql/
│   ├── ddl_script.sql       # DDL cho bảng dw + mart
│   └── schema_diagram.md
│
├── scripts/
│   ├── init_dw_tables.py    # Khởi tạo schema
│   └── ...
│
├── src/
│   ├── config.py            # Connection settings
│   ├── log_utils.py         # JSON structured logging
│   ├── watermark.py         # Incremental load management
│   │
│   ├── etl/                 # ETL Pipeline
│   │   ├── extract.py
│   │   ├── transform.py
│   │   ├── load.py
│   │   ├── pipeline.py
│   │   ├── validation.py
│   │   └── etl.py           # CLI entry point
│   │
│   ├── ml/                  # Machine Learning
│   │   ├── clustering.py
│   │   ├── anomaly.py
│   │   ├── decision_support.py
│   │   ├── migration.py
│   │   └── early_warning.py
│   │
│   ├── analytics/           # Advanced Analytics
│   │   ├── kpi_calculator.py
│   │   ├── snapshot_manager.py
│   │   ├── contribution.py
│   │   ├── drill_down.py
│   │   ├── insight_generator.py
│   │   ├── causal.py
│   │   ├── hypothesis_tester.py
│   │   └── runner.py
│   │
├── models/
│   ├── rfm_scaler.json      # StandardScaler params (trained)
│   └── rfm_centroids.npy    # K-Means centroids (trained)
│
├── notebooks/
├── reports/
│   └── dashboards/          # 3 Metabase dashboard docs
│
└── tests/
```

---

## 🔐 Bảo mật & Best Practices

- Mật khẩu trong `.env`, **không hardcode**
- Docker image pinned version (không `latest`)
- Python packages pinned version
- `.env` trong `.gitignore`
- Incremental load với watermark → không load lại dữ liệu cũ
- UPSERT với `ON CONFLICT` → idempotent
- 3-layer validation trước/sau load

---

## 📖 Tham khảo

- `proposal.md` — Đề xuất dự án chi tiết (10 câu hỏi phân tích, 8 hypotheses, 5 decision points)
- `etl_architecture.md` — Kiến trúc ETL chi tiết + Star Schema ERD
- `sql/schema_diagram.md` — Sơ đồ Star Schema
- `reports/dashboards/` — Tài liệu 3 Metabase dashboards
