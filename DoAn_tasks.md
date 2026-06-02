# Phân công & Các bước tiếp theo (Tiếng Việt)

Dưới đây là đề xuất phân công theo vai trò đã ghi trong đồ án, kèm các bước công việc chi tiết để bắt đầu ngay:

## Tổng quan vai trò

- A — Data Architect: thiết kế Star Schema, bảng fact/dim, tạo SQL schema trong `sql/`.
- B — ETL Engineer: hiện thực ETL (extract, transform, load) trong `src/etl.py` và module con `src/etl/`.
- C — Analytics Engineer: viết notebook phân tích trong `notebooks/` trả lời Q1–Q5.
- D — BI & Reporting: triển khai dashboard trên Metabase, tạo câu hỏi và dashboards.

## Bước khởi tạo (mọi người phối hợp)

1. Khởi chạy hạ tầng:

```bash
make up
```

2. Tạo venv và cài dependency:

```bash
make venv
source .venv/bin/activate
```

3. Tạo DB và kiểm tra kết nối:

```bash
make init-db
make test-conn
```

## Nhiệm vụ chi tiết theo vai trò

### A — Data Architect (Tuần 1, ngày 1–2)
- Thiết kế Star Schema chi tiết cho `Fact_Sales` và `Fact_Inventory`.
- Viết file DDL trong `sql/schema.sql` để tạo schema.
- Chuẩn bị mapping từ AdventureWorks sang các dim/fact.

Deliverables: `sql/schema.sql`, ER diagram (image trong `reports/figures`)

### B — ETL Engineer (Tuần 1, ngày 2–6)
- Viết ETL extract từ nguồn (nếu SQL Server, chuẩn bị bước chuyển hoặc dùng dump).
- Implement transform: surrogate keys, SCD Type 2 cho sản phẩm, tính `gross_profit`.
- Load vào Postgres DW theo schema.

Deliverables: `src/etl.py`, `src/etl/transform.py`, scripts chạy ETL `make etl` (sau)

### C — Analytics Engineer (Tuần 2, ngày 1–4)
- Tạo notebook `notebooks/Q1_revenue_gross.ipynb`, `notebooks/Q2_pareto.ipynb`, ...
- Viết các chart hỗ trợ kiểm chứng giả thuyết H1–H5.

Deliverables: notebooks và CSV output trong `data/processed/`

### D — BI & Reporting (Tuần 2, ngày 3–6)
- Kết nối Metabase tới Postgres.
- Tạo bảng điều khiển: KPI, Product & Customer, Inventory.

Deliverables: Metabase dashboards (screenshots trong `reports/`)

## Checklist ngắn hạn (tuần 1)
- [ ] Docker Compose chạy ổn (Postgres + Metabase)
- [ ] Venv và dependencies cài xong
- [ ] Schema DDL bản đầu (A)
- [ ] Skeleton ETL hoạt động test-conn (B)
- [ ] Notebook setup (C)


---

Nếu bạn đồng ý với phân công này, tôi sẽ:
- tạo `sql/schema.sql` mẫu (DDL) theo Star Schema,
- hoàn thiện `src/etl.py` để có lộ trình ETL cơ bản,
- và tạo notebook template trong `notebooks/`.

Bạn muốn tôi bắt đầu bằng phần nào? (A: tạo DDL; B: hoàn thiện ETL skeleton; C: tạo notebook templates)