# Luồng Code của Data Engineer (ETL Pipeline)

## Giới thiệu

Người Data Engineer chịu trách nhiệm xây dựng và vận hành đường ống ETL (Extract - Transform - Load) để lấy dữ liệu từ MSSQL AdventureWorks, biến đổi, và nạp vào PostgreSQL Data Warehouse.

## Các file liên quan

| File | Mục đích |
|------|----------|
| `src/etl/etl.py` | Điểm vào chính, phân tích tham số dòng lệnh, điều phối |
| `src/etl/pipeline.py` | Điều phối toàn bộ ETL theo thứ tự |
| `src/etl/extract.py` | Trích xuất dữ liệu từ MSSQL |
| `src/etl/transform.py` | Biến đổi dữ liệu thông qua các hàm chuẩn hóa, lookup, tính toán |
| `src/etl/load.py` | Nạp dữ liệu đã biến đổi vào PostgreSQL |
| `src/etl/validation.py` | Kiểm tra dữ liệu 3 lớp: trước load, sau load, và cross-check với OLTP |
| `src/watermark.py` | Quản lý watermark cho incremental load (đọc/ghi file config.json) |
| `src/config.py` | Cấu hình kết nối CSDL (PostgreSQL, MSSQL) |
| `src/log_utils.py` | Cấu hình logging JSON (tuỳ chọn) |
| `scripts/init_dw_tables.py` | Tạo bảng DDL cho dw/mart schema |
| `scripts/init_db.sh` | Shell script tạo database PostgreSQL |

## Cách chạy

```bash
python src/etl/etl.py --test          # Kiểm tra kết nối
python src/etl/etl.py --full          # Full load (lần đầu)
python src/etl/etl.py                 # Incremental load (mặc định)
python src/etl/etl.py --reset         # Reset watermark + full load
python src/etl/etl.py --refresh       # Xoá fact cũ + full load (sau khi sửa transform)
python src/etl/etl.py --snapshot      # Chỉ chạy KPI snapshot
```

## Luồng thực thi chi tiết

### 1. Khởi động (etl.main)

`etl.py` đọc tham số dòng lệnh, nếu không có watermark nào thì tự động chuyển sang chế độ full load. Sau đó gọi `run_full_etl_pipeline()` trong `pipeline.py`.

### 2. Trích xuất (extract_all)

`extract_all()` trong `extract.py` đọc lần lượt toàn bộ bảng nguồn từ MSSQL. Mỗi bảng có một hàm riêng:

- `extract_dim_product()`: JOIN 3 bảng Production.Product, Production.ProductSubcategory, Production.ProductCategory. Trả về 504 dòng.
- `extract_dim_customer()`: JOIN Customer, Person, Store, SalesTerritory, CountryRegion. Trả về 19.820 dòng.
- `extract_dim_territory()`: Đọc từ Sales.SalesTerritory. Trả về 10 dòng.
- `extract_dim_employee()`: JOIN Employee, Person, DepartmentHistory, Department. Trả về 290 dòng.
- `extract_fact_sales()`: JOIN SalesOrderDetail, SalesOrderHeader, Product. Trả về 121.317 dòng.
- `extract_fact_inventory()`: Đọc từ Production.ProductInventory, luôn full load (không dùng watermark vì là bảng snapshot).

Chế độ incremental dùng watermark để lọc bằng ModifiedDate. Chế độ full load bỏ qua watermark.

### 3. Biến đổi (transform)

`pipeline.py` gọi tuần tự các hàm transform:

- `transform_dim_date(start_year=2010, end_year=2029)`: Tạo bảng dim_date từ 2010 đến năm hiện tại + 3.
- `transform_dim_product()`: Chuẩn hóa tên cột, map category/subcategory.
- `transform_dim_territory()`: Chuẩn hóa tên cột.
- `transform_dim_employee()`: Chuẩn hóa tên cột, parse hire_date.
- `transform_dim_customer()`: Chuẩn hóa tên cột, map territory_id.
- `transform_fact_sales()`: Thực hiện các bước:
  - Chuẩn hóa tên cột (`standardize_column_names`)
  - Loại bỏ duplicate theo ModifiedDate
  - Loại bỏ bản ghi có ProductID/CustomerID/TerritoryID NULL
  - Loại bỏ bản ghi có unit_price, standard_cost, order_qty không hợp lệ
  - Tạo date_key từ OrderDate (định dạng YYYYMMDD)
  - Tra surrogate key cho product (SCD2 valid-range matching), customer, territory, employee
  - Tính gross_profit = linetotal - (standard_cost * order_qty)
- `transform_fact_inventory()`: Chuẩn hóa, tra surrogate key cho product, tạo date_key từ snapshot_date

### 4. Kiểm tra trước load (validate_pre_load)

Kiểm tra số dòng > 0 cho mỗi bảng. Incremental mode cho phép 0 dòng.

### 5. Nạp dữ liệu (load) trong 1 transaction

Toàn bộ nạp trong `with pg_engine.begin() as conn:` để đảm bảo tính nhất quán. Nếu lỗi thì ROLLBACK toàn bộ.

**Nạp Dimension:**

- `load_dim_date()`: INSERT ON CONFLICT DO NOTHING. Luôn thử insert (không skip nếu bảng đã có dữ liệu).
- `load_dim_territory()`, `load_dim_employee()`, `load_dim_customer()`: SCD Type 1. UPDATE nếu business_key đã tồn tại, INSERT nếu chưa.
- `load_dim_product()`: SCD Type 2. Close bản ghi cũ (set valid_to, is_current=false) và insert bản ghi mới khi có thay đổi track_cols (name, list_price, standard_cost).

**Nạp Fact:**

- `load_fact_sales()`: INSERT ON CONFLICT (sales_order_detail_id) DO NOTHING. Xử lý employee_key nullable (chuyển NaN thành None).
- `load_fact_inventory()`: INSERT ON CONFLICT (product_key, date_key, COALESCE(location_id, -1)) DO NOTHING.

**Sau khi nạp xong:**
- `ANALYZE` 6 bảng (fact_sales, fact_inventory, dim_product, dim_customer, dim_territory, dim_employee) để query planner không bị degrade.
- `refresh_daily_sales_agg()`: Xoá và insert lại bảng tổng hợp mart.daily_sales_agg.

### 6. Kiểm tra sau load (validate_post_load)

Dùng chung connection với transaction hiện tại để kiểm tra:
- NULL ở các cột FK trong fact_sales
- Orphan FK (fact record không tìm được dim record tương ứng)
- Cả 9 check đều yêu cầu kết quả = 0

### 7. Cross-check DWH vs OLTP (validate_cross_check)

So sánh SUM(line_total) và COUNT(sales_order_detail_id) giữa PostgreSQL DWH và MSSQL OLTP. Yêu cầu khớp 100% (sai lệch tối đa 0.01 do floating point).

### 8. Commit và snapshot

Nếu validation pass, transaction COMMIT. Sau đó chạy `run_kpi_snapshot()` bên ngoài transaction để không rollback dim/fact nếu snapshot lỗi.

## Kiến trúc SCD

| Bảng | Loại SCD | Cơ chế |
|------|----------|--------|
| dim_product | Type 2 | Close + Insert khi có thay đổi |
| dim_customer | Type 1 | Upsert tại chỗ |
| dim_territory | Type 1 | Upsert tại chỗ |
| dim_employee | Type 1 | Upsert tại chỗ |
| dim_date | Static | ON CONFLICT DO NOTHING |
| fact_sales | Append | ON CONFLICT DO NOTHING |
| fact_inventory | Append | ON CONFLICT DO NOTHING |

## Watermark management

- Watermark được lưu trong `config.json` dưới dạng ISO datetime.
- Ghi watermark sử dụng `fcntl.flock(LOCK_EX)` để tránh race condition khi nhiều tiến trình ETL chạy đồng thời.
- Sau mỗi pipeline thành công, `update_extract_watermarks()` cập nhật watermark cho 13 bảng nguồn bằng `SELECT NOW()` từ PostgreSQL (tránh container clock drift).
