# Kiến trúc ETL Pipeline — AdventureWorks → PostgreSQL DWH

## Tổng quan

```
MSSQL (AdventureWorks2022)          PostgreSQL (adventureworks_dw)
┌──────────────────────────┐         ┌──────────────────────────────┐
│  Sales.SalesOrderDetail  │         │  dw.fact_sales   121,317 rows│
│  Sales.SalesOrderHeader  │──ETL──► │  dw.fact_inventory  432 rows │
│  Production.Product      │         │  dw.dim_product     504 rows │
│  Sales.Customer          │         │  dw.dim_customer 19,820 rows │
│  Sales.SalesTerritory    │         │  dw.dim_territory    10 rows │
│  HumanResources.Employee │         │  dw.dim_employee    290 rows │
│  + 7 bảng join phụ       │         │  dw.dim_date     11,323 rows │
└──────────────────────────┘         └──────────────────────────────┘
```

---

## 1. Kiến trúc file (Module Design)

```
src/
├── config.py          ← Cấu hình kết nối DB (Postgres + MSSQL)
├── watermark.py       ← Quản lý incremental load state
└── etl/
    ├── etl.py         ← Entry point (CLI: --full / --reset / --test)
    ├── pipeline.py    ← Orchestrator điều phối thứ tự
    ├── extract.py     ← Kết nối MSSQL, chạy JOIN queries
    ├── transform.py   ← Làm sạch, tính toán, chuẩn hóa
    ├── validation.py  ← 3-layer kiểm tra chất lượng
    └── load.py        ← Ghi vào PostgreSQL DWH

config.json            ← Lưu watermark timestamp (incremental state)
```

> **Nguyên tắc thiết kế:** Mỗi file có một trách nhiệm duy nhất (Single Responsibility). `etl.py` chỉ biết gọi `pipeline.py` — không biết gì về SQL hay DataFrame.

---

## 2. Luồng dữ liệu chi tiết (Detailed ETL Workflow)

Quy trình ETL được kích hoạt từ file entry point `src/etl/etl.py` và điều phối bởi `src/etl/pipeline.py`. Toàn bộ luồng dữ liệu được chia làm 6 bước chính dưới đây:

### [1] Bước Trích xuất (EXTRACT Layer - `extract.py`)
Mục đích là kết nối tới nguồn dữ liệu Microsoft SQL Server (`AdventureWorks2022`), trích xuất dữ liệu thô thông qua các câu lệnh SQL JOIN tối ưu để giảm tải lượng dữ liệu truyền qua mạng. Quy trình này hỗ trợ hai chế độ chạy:
* **Full Load (`--full`):** Truy vấn toàn bộ dữ liệu hiện có trong nguồn.
* **Incremental Load (Mặc định):** Sử dụng mệnh đề `WHERE ModifiedDate > :watermark` (với giá trị `:watermark` được đọc ra từ `config.json`). Nếu một bảng không tìm thấy watermark từ trước, nó sẽ mặc định tự động chạy Full Load cho bảng đó.

Chi tiết các truy vấn trích xuất:
1. **`extract_dim_product`**: Thực hiện `LEFT JOIN` giữa `Production.Product (p)`, `Production.ProductSubcategory (ps)` và `Production.ProductCategory (pc)` để thu thập thông tin danh mục của sản phẩm. Lọc theo watermark trên cột `p.ModifiedDate`.
2. **`extract_dim_customer`**: Kết nối `Sales.Customer (c)` với `Person.Person (p)`, `Sales.Store (s)`, `Sales.SalesTerritory (st)`, `Person.StateProvince (sp)` và `Person.CountryRegion (cr)`.
   * Phân loại khách hàng: Nếu `c.PersonID` không NULL thì `customer_type = 'Individual'` và tên được ghép từ `FirstName + MiddleName + LastName`; ngược lại nếu `c.StoreID` không NULL thì `customer_type = 'Store'` và tên lấy từ `s.Name`. Lọc theo watermark trên cột `c.ModifiedDate`.
3. **`extract_dim_territory`**: Truy xuất trực tiếp từ `Sales.SalesTerritory (st)` kết hợp `LEFT JOIN` với `Person.CountryRegion (cr)` để lấy tên quốc gia. Lọc theo watermark trên `st.ModifiedDate`.
4. **`extract_dim_employee`**: Thực hiện `INNER JOIN` giữa `HumanResources.Employee (e)` và `Person.Person (p)`. Để xác định phòng ban hiện tại của nhân viên, thực hiện `LEFT JOIN` với `HumanResources.EmployeeDepartmentHistory (edh)` kèm điều kiện lọc `edh.EndDate IS NULL` (chỉ lấy bộ phận đang làm việc), sau đó nối với `HumanResources.Department (d)`. Lọc theo watermark trên `e.ModifiedDate`.
5. **`extract_fact_sales`**: Kết nối `Sales.SalesOrderDetail (sod)` với `Sales.SalesOrderHeader (soh)` để lấy các trường thông tin chung như ngày đặt hàng (`OrderDate`), khách hàng (`CustomerID`), và khu vực (`TerritoryID`). Nối với `Production.Product (p)` để lấy giá vốn tiêu chuẩn (`StandardCost`) tại thời điểm bán hàng. Lọc theo watermark trên `sod.ModifiedDate`.
6. **`extract_fact_inventory`**: Trích xuất snapshot tồn kho từ bảng `Production.ProductInventory (pi)` liên kết với bảng `Production.WorkOrder (wo)` để gom nhóm và tính tổng số lượng đang đặt hàng (`ordered_qty`) và số lượng bị hỏng (`scrapped_qty`). Lấy giá trị `MAX(pi.ModifiedDate)` làm watermark.

---

### [2] Bước Biến đổi (TRANSFORM Layer - `transform.py`)
Thực hiện làm sạch dữ liệu (Data Cleaning), kiểm tra chất lượng (Data Quality Rules), xử lý giá trị khuyết (Null Handling), và tính toán các cột phái sinh (Derived Metrics):

1. **Chuẩn hóa tên cột (Normalization):** Chuyển toàn bộ tên cột sang chữ thường (lowercase), loại bỏ khoảng trắng dư thừa và thay thế bằng ký tự gạch dưới (`_`).
2. **Loại bỏ bản ghi trùng lặp (Deduplication):** Sử dụng hàm `deduplicate_by_modified()`. Gom nhóm dữ liệu theo khóa tự nhiên (Business Key) của từng chiều, sắp xếp theo `ModifiedDate` giảm dần và chỉ giữ lại bản ghi mới nhất.
3. **Áp dụng các quy tắc chất lượng dữ liệu (Data Quality Rules):**
   * **`dim_product`**: Loại bỏ (DROP) các bản ghi có giá bán (`list_price`) hoặc giá vốn (`standard_cost`) nhỏ hơn 0 hoặc NULL. Nếu danh mục phụ (`subcategory`) hoặc danh mục chính (`category`) bị NULL, điền giá trị `'Unknown'`.
   * **`dim_customer`**: Điền giá trị `'Unknown'` cho các cột `full_name`, `customer_type`, `country`, `state_province` bị khuyết thiếu.
   * **`dim_territory`**: Điền `'Unknown'` nếu thông tin khu vực hoặc quốc gia bị NULL.
   * **`dim_employee`**: Loại bỏ (DROP) các nhân viên không có ngày vào làm (`hire_date`). Điền `'Unknown'` cho các trường `full_name`, `job_title`, `department` bị NULL.
   * **`fact_sales`**: Loại bỏ (DROP) toàn bộ bản ghi có khóa ngoại gốc bị NULL (`ProductID`, `CustomerID`, `TerritoryID`). Loại bỏ bản ghi có `unit_price < 0`, `standard_cost < 0`, hoặc `order_qty <= 0`.
4. **Tính toán chỉ số phái sinh (Derived Columns):**
   * **`date_key`**: Được tính bằng cách chuyển đổi ngày đặt hàng `OrderDate` thành kiểu số nguyên định dạng `YYYYMMDD` (ví dụ `2026-06-20` -> `20260620`) để liên kết nhanh với bảng chiều thời gian `dim_date`.
   * **`gross_profit`** (Lợi nhuận gộp): Tính toán trực tiếp tại lớp transform bằng công thức:
     `gross_profit = line_total - (standard_cost * order_qty)`
5. **Surrogate Key Mapping (Tra cứu khóa thay thế):**
   * Đối với bảng sự kiện (`fact_sales` và `fact_inventory`), thay thế các mã tự nhiên (Business Keys như `ProductID`, `CustomerID`, v.v.) bằng các khóa thay thế tự tăng (`product_key`, `customer_key`, `territory_key`, `employee_key`) được tra cứu trực tiếp từ các bảng chiều tương ứng đã nạp vào DWH trước đó.
   * Riêng đối với `dim_product` (áp dụng SCD Type 2), tra cứu khóa thay thế `product_key` của bản ghi đang có hiệu lực (`is_current = True`).
6. **Thêm dấu thời gian nạp dữ liệu (Audit columns):** Thêm trường `_load_timestamp` bằng thời gian chạy hiện tại của hệ thống.

---

### [3] Bước Kiểm định trước khi nạp (PRE-LOAD VALIDATION Layer - `validation.py`)
Trước khi thực hiện bất kỳ thao tác ghi nào vào cơ sở dữ liệu Data Warehouse:
* Kiểm tra xem các DataFrame kết quả sau bước Transform có bị rỗng (`empty`) hay không. Nếu rỗng, hệ thống sẽ log cảnh báo nhưng tiếp tục chạy.
* Kiểm tra tính toàn vẹn của cấu trúc dữ liệu (`validate_schema`): So khớp danh sách cột của DataFrame sau biến đổi với danh sách cột được cấu hình trước của bảng đích trong Postgres DWH. Nếu thiếu cột bắt buộc, tiến trình ETL sẽ lập tức dừng và báo lỗi để tránh làm hỏng cấu trúc cơ sở dữ liệu.

---

### [4] Bước Nạp các bảng chiều (LOAD DIMENSIONS Layer - `load.py`)
Tiến trình ghi dữ liệu được thực hiện tuần tự theo đúng thứ tự phụ thuộc khóa ngoại: `dim_date` -> `dim_territory` -> `dim_employee` -> `dim_product` -> `dim_customer`. Toàn bộ quá trình nạp được đặt trong một Database Transaction:

* **Sinh dữ liệu tĩnh cho `dim_date`:** Tự động tạo dữ liệu thời gian cho 20 năm (từ 2010 đến 2030) và lưu vào cơ sở dữ liệu nếu chưa có.
* **Xử lý SCD Type 1 (cho `dim_customer`, `dim_territory`, `dim_employee`):**
   * Sử dụng câu lệnh Upsert (`INSERT ... ON CONFLICT (...) DO UPDATE`).
   * Nếu mã tự nhiên của bản ghi (ví dụ `customer_id`) chưa tồn tại trong DWH, hệ thống tiến hành `INSERT`.
   * Nếu mã tự nhiên đã tồn tại, hệ thống chạy `UPDATE` để ghi đè dữ liệu mới nhất vào dòng đó mà không lưu lại lịch sử thay đổi.
* **Xử lý SCD Type 2 (cho `dim_product`):**
   * Đối với từng sản phẩm nạp vào, hệ thống đối chiếu với dòng hiện tại đang có hiệu lực (`is_current = True`) trong cơ sở dữ liệu.
   * Nếu sản phẩm chưa từng xuất hiện: Tiến hành `INSERT` bản ghi mới với `valid_from = current_timestamp`, `valid_to = NULL`, và `is_current = True`.
   * Nếu sản phẩm đã tồn tại nhưng có sự thay đổi ở các trường giám sát (`name`, `subcategory`, `category`, `list_price`, `standard_cost`):
     1. **Đóng bản ghi cũ:** `UPDATE` dòng cũ thành `is_current = False` và đặt `valid_to = current_timestamp`.
     2. **Mở bản ghi mới:** `INSERT` một dòng mới chứa thông tin đã thay đổi, tạo ra `product_key` mới, đặt `valid_from = current_timestamp`, `valid_to = NULL`, và `is_current = True`.
   * Nếu sản phẩm đã tồn tại và thông tin không có gì thay đổi: Bỏ qua (không thực hiện ghi để tránh rác dữ liệu).

---

### [5] Bước Nạp các bảng sự kiện (LOAD FACTS Layer - `load.py`)
Sau khi các bảng chiều đã được nạp xong và các khóa thay thế (`Surrogate Keys`) đã được ánh xạ chính xác:
* **`fact_sales`**: Nạp dữ liệu giao dịch bán hàng theo cơ chế Idempotent (không trùng lặp). Sử dụng câu lệnh `INSERT INTO dw.fact_sales ... ON CONFLICT (sales_order_detail_id) DO NOTHING`. Giúp đảm bảo dữ liệu bán hàng không bị nhân đôi kể cả khi chạy lại pipeline nhiều lần trên cùng một khoảng thời gian.
* **`fact_inventory`**: Nạp dữ liệu snapshot hàng tồn kho tại ngày chạy ETL hiện tại.

---

### [6] Bước Kiểm định sau khi nạp (POST-LOAD VALIDATION & CROSS-CHECK Layer - `validation.py`)
Khi kết thúc thao tác nạp dữ liệu, hệ thống tự động chạy các bộ kiểm tra chất lượng sau cùng:
1. **Post-load Validation (9 checks):**
   * Kiểm tra xem có cột khóa ngoại nào trong bảng `fact_sales` bị nhận giá trị `NULL` hay không (đảm bảo tính toàn vẹn tham chiếu).
   * Kiểm tra lỗi "mồ côi" (Orphan FKs) - đảm bảo mọi khóa ngoại liên kết từ `fact_sales` đến các bảng `dim_product`, `dim_customer`, `dim_territory`, `dim_employee` đều thực sự tồn tại trong các bảng chiều tương ứng.
2. **Cross-check (2 checks):**
   * **Đối chiếu số lượng bản ghi (COUNT):** So sánh tổng số dòng trong bảng `fact_sales` của DWH với số dòng gốc trích xuất từ bảng `Sales.SalesOrderDetail` của MSSQL (có tính đến bộ lọc watermark).
   * **Đối chiếu giá trị tài chính (SUM):** Tính tổng số tiền giao dịch (`SUM(line_total)`) trong DWH và đối chiếu với dữ liệu gốc của MSSQL.
   * Nếu bất kỳ bộ kiểm định nào trong bước này bị thất bại, một Exception sẽ được ném ra, kích hoạt cơ chế **ROLLBACK** để hoàn trả DWH về trạng thái sạch ban đầu. Nếu thành công, giao dịch được **COMMIT** và watermark mới được lưu lại vào `config.json`.

## 3. Incremental Load (Watermark Pattern)

```
config.json (trước lần 1):          config.json (sau lần 1):
{                                    {
  "watermarks": {                      "watermarks": {
    "Sales.SalesOrderDetail": null,      "Sales.SalesOrderDetail": "2026-06-19T16:52:29",
    "Production.Product": null,          "Production.Product": "2026-06-19T16:52:29",
    ...                                  ...
  }                                    },
}                                      "last_run_status": "SUCCESS"
                                     }

Lần 2 chạy (incremental):
  WHERE ModifiedDate > '2026-06-19T16:52:29'
  → Chỉ kéo rows mới/thay đổi
  → Thời gian chạy: vài giây thay vì 2 phút

Giới hạn: Hard delete trong MSSQL không bắt được
(record bị xóa ở nguồn vẫn còn trong DWH)
```

---

## 4. Star Schema trong DWH

Dưới đây là thiết kế Star Schema chi tiết với đầy đủ 2 bảng sự kiện (`fact_sales`, `fact_inventory`) và 5 bảng chiều (`dim_date`, `dim_product`, `dim_customer`, `dim_territory`, `dim_employee`), cùng với tất cả các trường dữ liệu, ràng buộc khóa chính/khóa ngoại và cột audit timestamp tương ứng với cấu trúc DWH thực tế hiện tại.

```mermaid
erDiagram
    dim_date {
        int date_key PK "YYYYMMDD"
        date date NOT_NULL
        int day NOT_NULL
        int month NOT_NULL
        int quarter NOT_NULL
        int year NOT_NULL
        boolean is_weekend NOT_NULL
    }

    dim_product {
        int product_key PK "SERIAL"
        int product_id NOT_NULL "Business Key"
        varchar name NOT_NULL
        varchar subcategory
        varchar category
        numeric list_price NOT_NULL
        numeric standard_cost NOT_NULL
        timestamp valid_from NOT_NULL
        timestamp valid_to
        boolean is_current NOT_NULL
        timestamp _load_timestamp
    }

    dim_customer {
        int customer_key PK "SERIAL"
        int customer_id NOT_NULL "Business Key"
        varchar full_name NOT_NULL
        varchar customer_type NOT_NULL "Individual / Store"
        varchar country
        varchar state_province
        int territory_id
        timestamp _load_timestamp
    }

    dim_territory {
        int territory_key PK "SERIAL"
        int territory_id NOT_NULL "Business Key"
        varchar territory_name NOT_NULL
        varchar country_region NOT_NULL
        varchar group_name NOT_NULL
        timestamp _load_timestamp
    }

    dim_employee {
        int employee_key PK "SERIAL"
        int employee_id NOT_NULL "Business Key"
        varchar full_name NOT_NULL
        varchar job_title NOT_NULL
        varchar department NOT_NULL
        date hire_date NOT_NULL
        timestamp _load_timestamp
    }

    fact_sales {
        int sales_order_detail_id PK "Business Key"
        int date_key FK "References dim_date"
        int product_key FK "References dim_product"
        int customer_key FK "References dim_customer"
        int territory_key FK "References dim_territory"
        int employee_key FK "References dim_employee (Nullable)"
        int order_qty NOT_NULL
        numeric unit_price NOT_NULL
        numeric unit_price_discount NOT_NULL
        numeric line_total NOT_NULL
        numeric standard_cost NOT_NULL
        numeric gross_profit NOT_NULL "line_total - (standard_cost * order_qty)"
        timestamp _load_timestamp
    }

    fact_inventory {
        int inventory_id PK "SERIAL"
        int date_key FK "References dim_date"
        int product_key FK "References dim_product"
        int quantity NOT_NULL
        int ordered_qty
        int scrapped_qty
        timestamp _load_timestamp
    }

    %% Relationships
    dim_date ||--o{ fact_sales : "sales_date"
    dim_product ||--o{ fact_sales : "product"
    dim_customer ||--o{ fact_sales : "customer"
    dim_territory ||--o{ fact_sales : "territory"
    dim_employee ||--o{ fact_sales : "sales_person"

    dim_date ||--o{ fact_inventory : "inventory_date"
    dim_product ||--o{ fact_inventory : "product"
```

---

## 5. Những quyết định thiết kế quan trọng

### gross_profit tính tại Transform, không tính trong SQL phân tích

```python
# Transform layer (Python):
df["gross_profit"] = df["line_total"] - (df["standard_cost"] * df["order_qty"])
```

**Lý do:** Đảm bảo con số nhất quán — mọi dashboard/report đều dùng cùng một logic tính toán, không ai tính lại theo cách riêng.

---

### Surrogate Key thay thế Natural Key

```
MSSQL:  ProductID = 711  (business key, có thể bị reuse)
DWH:    product_key = 487 (surrogate key, SERIAL tự tăng, ổn định)
```

**Lý do:** Business key có thể thay đổi hoặc bị reuse. Surrogate key bảo vệ tính toàn vẹn của lịch sử trong DWH.

---

### SCD Type 2 chỉ cho dim_product

Chỉ Product cần lịch sử thay đổi vì câu hỏi phân tích quan trọng là:
> *"Sản phẩm này lúc bán có giá bao nhiêu?"* (không phải giá hiện tại)

Fact_Sales lookup `product_key` của bản ghi **đang current tại thời điểm bán**, giữ đúng giá `list_price` và `standard_cost` tại lúc đó.

---

### DB Transaction bảo vệ tính toàn vẹn

```python
with engine.begin() as conn:   # BEGIN TRANSACTION
    # load dim_territory
    # load dim_employee
    # ...
# COMMIT khi không lỗi, ROLLBACK tự động khi có exception
```

Nếu ETL crash ở giữa (ví dụ mạng đứt khi đang load fact_sales), toàn bộ lần chạy bị rollback — DWH không bao giờ ở trạng thái nửa vời.

---

## 6. Kết quả thực tế sau 1 lần Full Load

| Metric | Giá trị |
|---|---|
| Thời gian chạy | ~2 phút |
| Tổng rows vào DWH | **153,196 rows** |
| Data quality drops | 0 (dataset sạch) |
| Orphan FK | 0 |
| COUNT cross-check | ✓ Khớp 100% |
| SUM cross-check | ✓ Khớp 100% ($109.8M) |
| Watermark saved | ✓ (incremental sẵn sàng) |

---

> [!TIP]
> Lần sau khi chạy incremental (`python src/etl/etl.py` không có `--full`), pipeline sẽ chỉ kéo rows có `ModifiedDate` mới hơn watermark → thời gian chạy giảm từ 2 phút xuống còn vài giây nếu ít thay đổi.

> [!NOTE]
> **Điểm yếu đã biết:** Incremental load dùng `ModifiedDate` không bắt được hard delete trong MSSQL. Nếu cần sync delete, cần thêm CDC (Change Data Capture) hoặc soft-delete pattern.


---

## 7. Hướng dẫn thiết lập và khởi chạy Pipeline

Để một thành viên mới trong dự án khởi chạy toàn bộ quy trình ETL một cách trơn tru sau khi pull mã nguồn về, hãy hướng dẫn họ thực hiện lần lượt các bước sau:

### Bước 1: Tạo cấu hình môi trường (.env)
Tạo tệp cấu hình `.env` từ tệp mẫu:
```bash
cp .env.example .env
```
Mở tệp `.env` vừa tạo và chỉnh sửa các tham số kết nối (đặc biệt là mật khẩu `MSSQL_PASSWORD` phải là một mật khẩu mạnh bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt).

### Bước 2: Thiết lập môi trường ảo Python (Virtualenv)
Để cài đặt đầy đủ các thư viện Python (như Pandas, SQLAlchemy, pymssql, psycopg2, python-dotenv, v.v.):
```bash
make venv
```
*Lưu ý:* Môi trường ảo sẽ được khởi tạo trong thư mục `.venv/`.

### Bước 3: Khởi chạy hạ tầng Docker
Khởi chạy cơ sở dữ liệu Postgres (DWH) và SQL Server (OLTP):
```bash
make up
```
Đợi khoảng 1-2 phút cho đến khi cả hai container đạt trạng thái `healthy`. Kiểm tra trạng thái bằng lệnh:
```bash
make ps
```

### Bước 4: Khởi tạo database thô và khôi phục dữ liệu nguồn
* **Khởi tạo database PostgreSQL rỗng:**
  ```bash
  make init-db
  ```
* **Khôi phục database nguồn AdventureWorks2022 trên SQL Server:**
  ```bash
  make restore-db
  ```
* **Kiểm tra kết nối hệ thống:**
  ```bash
  make test-conn
  ```
  *(Nếu in ra `Test connection: 1` tức là kết nối giữa Python và hai cơ sở dữ liệu đã thông suốt)*

### Bước 5: Khởi tạo các bảng cấu trúc Data Warehouse (DWH)
Trước khi chạy ETL, ta cần khởi tạo schema `dw` và các bảng chiều, bảng sự kiện trong PostgreSQL DWH:
```bash
.venv/bin/python scripts/init_dw_tables.py
```

### Bước 6: Khởi chạy ETL Pipeline

#### Cách 1: Khởi chạy từ máy ngoài (Host machine)
Sử dụng môi trường ảo đã cấu hình:
* **Chạy Full Load lần đầu tiên** (xóa dữ liệu cũ, kéo lại toàn bộ):
  ```bash
  .venv/bin/python src/etl/etl.py --full
  ```
  *Hoặc bạn có thể dùng lệnh make:* `make etl` (mặc định sẽ chạy incremental, nếu muốn full load nên chạy trực tiếp với cờ `--full`).
* **Chạy Incremental Load** (các lần tiếp theo - chỉ lấy các bản ghi thay đổi từ sau watermark):
  ```bash
  .venv/bin/python src/etl/etl.py
  ```

#### Cách 2: Khởi chạy từ bên trong Docker Container `etl`
Nếu bạn không muốn cài đặt Python cục bộ trên máy mà muốn chạy trực tiếp bằng môi trường Docker:
1. Truy cập vào container `etl`:
   ```bash
   docker exec -it etl bash
   ```
2. Thực hiện chạy Full Load bên trong container:
   ```bash
   python src/etl/etl.py --full
   ```
3. Chạy Incremental Load ở các lần sau:
   ```bash
   python src/etl/etl.py
   ```
