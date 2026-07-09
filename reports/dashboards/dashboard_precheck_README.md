# README — Dashboard Pre-check Report trước khi vẽ Metabase Dashboard

## 1. Mục đích

File này dùng để chứng minh rằng nhóm đã kiểm tra đầy đủ dữ liệu đầu ra trước khi vẽ lại dashboard Metabase theo yêu cầu mới của thầy.

Trọng tâm của lần kiểm tra này là đảm bảo dashboard không còn chỉ vẽ số liệu tổng toàn bộ dataset, mà dựa trên:

- Dữ liệu Data Warehouse đã load đúng.
- KPI snapshot theo period/quarter trong `mart.kpi_snapshot`.
- Phân tích so sánh kỳ trong `mart.period_comparison`.
- Output Machine Learning trong `dw.ml_customer_segments`, `dw.ml_inventory_anomaly`.
- Output Decision Support trong `dw.decision_support`.
- Metabase dashboard đọc đúng các bảng `dw.*` và `mart.*`.

---

## 2. Lý do phải pre-check trước khi vẽ dashboard

Nhận xét của thầy yêu cầu nhóm phải bổ sung tầng lưu snapshot KPI và phân tích theo thời gian. Vì vậy trước khi vẽ dashboard cần kiểm tra:

1. KPI có được tính theo kỳ không.
2. Mart layer có dữ liệu thật không.
3. ML output có được tạo bằng pipeline chuẩn không.
4. Dashboard có đọc đúng dữ liệu từ mart layer và ML output không.
5. Các biểu đồ không được vẽ từ bảng rỗng, dữ liệu 0 hoặc dữ liệu chạy thủ công không tái lập được.

Nếu bỏ qua bước này thì dashboard có thể hiển thị đẹp nhưng không chứng minh được logic phân tích phía sau.

---

## 3. Checklist tổng quan

| Nhóm kiểm tra | Trạng thái | Ý nghĩa |
|---|---:|---|
| Core DWH | Đạt | Dữ liệu fact/dim đã load đúng, không rỗng, không lỗi FK |
| Mart Layer | Đạt | Có KPI snapshot theo period, có comparison, có daily aggregate |
| ML Output | Đạt | Clustering, anomaly, migration, decision support chạy bằng `make` command |
| DDL / Init Script | Đạt | Các bảng `dw.ml_*` và `mart.*` đã nằm trong DDL/init script |
| Metabase Dashboard | Đạt | Đã tạo 3 dashboard (id=11,12,13) với 10+13+12 cards; tất cả trả dữ liệu; layout 5-6 rows; đa dạng biểu đồ (scalar, line, bar, pie, scatter, table) |

---

## 4. Core DWH Pre-check

### 4.1. Mục tiêu

Kiểm tra dữ liệu gốc trong Data Warehouse đã được load đúng trước khi tạo các bảng mart và dashboard.

### 4.2. Query kiểm tra

```sql
SELECT COUNT(*) FROM dw.fact_sales;
SELECT COUNT(*) FROM dw.fact_inventory;

SELECT MIN(d.date), MAX(d.date)
FROM dw.fact_sales f
JOIN dw.dim_date d ON f.date_key = d.date_key;
```

Kiểm tra khóa ngoại:

```sql
SELECT COUNT(*) FROM dw.fact_sales WHERE customer_key IS NULL;
SELECT COUNT(*) FROM dw.fact_sales WHERE product_key IS NULL;
SELECT COUNT(*) FROM dw.fact_sales WHERE territory_key IS NULL;
SELECT COUNT(*) FROM dw.fact_sales WHERE date_key IS NULL;

SELECT COUNT(*)
FROM dw.fact_sales f
LEFT JOIN dw.dim_customer c ON f.customer_key = c.customer_key
WHERE c.customer_key IS NULL;

SELECT COUNT(*)
FROM dw.fact_sales f
LEFT JOIN dw.dim_product p ON f.product_key = p.product_key
WHERE p.product_key IS NULL;
```

### 4.3. Kết quả đã kiểm tra

| Metric | Kết quả |
|---|---:|
| `dw.fact_sales` | 121,317 rows |
| `dw.fact_inventory` | 1,069 rows |
| Date range | 2011-05-31 → 2014-06-30 |
| Distinct sales orders | 31,465 |
| FK null/orphan | 0 |
| `sales_order_id` null | 0 |
| `location_id` null | 0 |

### 4.4. Kết luận

Core DWH đạt yêu cầu. Có thể dùng `dw.fact_sales`, `dw.fact_inventory` và các bảng dimension làm nền dữ liệu cho mart layer, ML output và dashboard.

---

## 5. Mart Layer Pre-check

### 5.1. Mục tiêu

Kiểm tra tầng `mart` đã đáp ứng yêu cầu của thầy về snapshot KPI theo kỳ và phân tích biến động.

Các bảng cần có:

- `mart.kpi_snapshot`
- `mart.period_comparison`
- `mart.daily_sales_agg`
- `mart.rfm_snapshot`
- `mart.customer_migration`
- `mart.inventory_snapshot`

### 5.2. Query kiểm tra số dòng

```sql
SELECT 'mart.kpi_snapshot' AS table_name,
       COUNT(*) AS rows,
       COUNT(DISTINCT period_key) AS periods,
       COUNT(DISTINCT kpi_name) AS kpis
FROM mart.kpi_snapshot
UNION ALL
SELECT 'mart.period_comparison', COUNT(*), COUNT(DISTINCT curr_period_key), 0
FROM mart.period_comparison
UNION ALL
SELECT 'mart.daily_sales_agg', COUNT(*), 0, 0
FROM mart.daily_sales_agg
UNION ALL
SELECT 'mart.rfm_snapshot', COUNT(*), COUNT(DISTINCT period_key), 0
FROM mart.rfm_snapshot
UNION ALL
SELECT 'mart.customer_migration', COUNT(*), COUNT(DISTINCT curr_period_key), 0
FROM mart.customer_migration;
```

### 5.3. Kết quả đã kiểm tra

| Bảng | Kết quả |
|---|---:|
| `mart.kpi_snapshot` | 2,045 rows |
| Periods trong `mart.kpi_snapshot` | 16 periods |
| KPI trong `mart.kpi_snapshot` | 16 KPIs |
| `mart.period_comparison` | 30 rows |
| `mart.daily_sales_agg` | 1,124 rows |
| `mart.rfm_snapshot` | 12 rows |
| `mart.customer_migration` | 12,804 rows |

### 5.4. Query kiểm tra KPI thật cho 2014Q1 và 2014Q2

```sql
SELECT kpi_name, period_key, dimension, value::numeric(18,2)
FROM mart.kpi_snapshot
WHERE period_key IN ('2014Q1', '2014Q2')
  AND dimension = 'overall'
ORDER BY kpi_name, period_key;
```

### 5.5. Một số KPI đã xác nhận

| KPI | 2014Q1 | 2014Q2 |
|---|---:|---:|
| `avg_order_value` | 2,040.20 | 1,319.83 |
| `gross_margin_pct` | 14.61 | 21.72 |
| `gross_profit` | 1,876,138.27 | 1,566,311.22 |
| `hhi_revenue_concentration` | 0.77 | 0.76 |

### 5.6. Lưu ý về kỳ có giá trị 0

Một số dòng trong `mart.kpi_snapshot` có giá trị 0 ở các kỳ ngoài phạm vi dữ liệu bán hàng như:

- 2011Q1: trước khi có dữ liệu bán hàng.
- 2014Q3, 2014Q4: sau khi dữ liệu bán hàng kết thúc.
- `inventory_turnover`: bằng 0 vì dữ liệu inventory hiện là snapshot hiện tại, chưa có lịch sử tồn kho theo từng kỳ.

Khi vẽ dashboard time-series nên filter khoảng kỳ hợp lệ:

```sql
WHERE period_key BETWEEN '2011Q2' AND '2014Q2'
```

### 5.7. Kết luận

Mart layer đạt yêu cầu để vẽ dashboard theo period/time-series. Dashboard 1 nên ưu tiên dùng `mart.kpi_snapshot`, `mart.period_comparison`, `mart.daily_sales_agg` thay vì tính KPI trực tiếp toàn bộ từ `dw.fact_sales`.

---

## 6. Period Comparison Pre-check

### 6.1. Mục tiêu

Kiểm tra bảng `mart.period_comparison` có đủ dữ liệu để giải thích nguyên nhân biến động KPI giữa kỳ hiện tại và kỳ trước.

### 6.2. Query kiểm tra

```sql
SELECT kpi_name,
       dimension,
       dimension_value,
       curr_value::numeric(18,2) AS curr_value,
       prev_value::numeric(18,2) AS prev_value,
       pct_change::numeric(10,2) AS pct_change,
       contribution_pct::numeric(10,2) AS contribution_pct
FROM mart.period_comparison
WHERE curr_period_key = '2014Q2'
  AND kpi_name = 'revenue'
ORDER BY ABS(contribution_pct) DESC
LIMIT 10;
```

### 6.3. Kết quả nổi bật

| Dimension | Dimension Value | Curr Value | Prev Value | % Change | Contribution |
|---|---|---:|---:|---:|---:|
| customer_type | Individual | 7,212,854.02 | 12,845,072.64 | -43.85% | -100.00% |
| category | Bikes | 701,965.86 | 1,406,698.25 | -50.10% | -97.01% |
| territory | Southwest | 1,419,559.87 | 2,552,337.78 | -44.38% | -20.11% |
| territory | Northwest | 1,060,159.46 | 1,937,591.05 | -45.28% | -15.58% |
| territory | France | 470,332.60 | 1,203,746.09 | -60.93% | -13.02% |

### 6.4. Kết luận

`mart.period_comparison` có thể dùng để vẽ các biểu đồ:

- Revenue Contribution by Category
- Revenue Contribution by Territory
- KPI Current vs Previous Period
- Top Drivers of Revenue Change

Đây là phần quan trọng để chứng minh dashboard có phân tích nguyên nhân, không chỉ mô tả số liệu.

---

## 7. ML Output Pre-check

### 7.1. Mục tiêu

Kiểm tra các bảng ML output đã được tạo bằng pipeline chuẩn, không chạy script tay.

Các lệnh đã dùng:

```bash
make ml-clustering
make ml-anomaly
make ml-migration
make ml-decision
```

---

## 8. Customer Segmentation Pre-check

### 8.1. Mục tiêu

Kiểm tra mô hình K-Means RFM đã chạy đúng và có thể dùng cho Dashboard 2.

### 8.2. Kết quả đã kiểm tra

| Nội dung | Kết quả |
|---|---:|
| Method | K-Means trên RFM |
| Cách chọn K | `choose_best_k` bằng silhouette score |
| Best K | 3 |
| Best silhouette score | ~0.4836 |
| Số khách hàng được gán segment | 18,669 |

Phân bố cluster:

| Cluster Label | Số khách hàng |
|---|---:|
| Loyal Customers | 14,078 |
| Champions | 4,149 |
| Potential Loyalists | 442 |

### 8.3. Query kiểm tra

```sql
SELECT cluster_label,
       COUNT(*) AS customer_count,
       ROUND(AVG(monetary), 2) AS avg_monetary,
       ROUND(AVG(recency_days), 2) AS avg_recency,
       ROUND(AVG(frequency), 2) AS avg_frequency
FROM dw.ml_customer_segments
GROUP BY cluster_label
ORDER BY customer_count DESC;
```

Kiểm tra metrics:

```sql
SELECT *
FROM dw.ml_customer_clustering_metrics
ORDER BY k;
```

### 8.4. Kết luận

Dashboard 2 có thể vẽ:

- Customer Segments — RFM Clustering
- Segment Details Table
- RFM Cluster Share by Period
- Customer Migration Summary

---

## 9. Inventory Risk / Anomaly Pre-check

### 9.1. Mục tiêu

Kiểm tra output từ Isolation Forest và xác định cách đặt tên biểu đồ cho đúng dữ liệu.

### 9.2. Query kiểm tra

```sql
SELECT CASE WHEN anomaly_flag THEN 'anomaly' ELSE 'warning' END AS flag_type,
       CASE WHEN zero_sales_flag THEN 'zero_sales' ELSE 'has_sales' END AS sales_type,
       COUNT(*) AS count,
       ROUND(AVG(days_inventory_outstanding)::numeric, 1) AS avg_dio
FROM dw.ml_inventory_anomaly
GROUP BY anomaly_flag, zero_sales_flag
ORDER BY anomaly_flag DESC, zero_sales_flag DESC;
```

### 9.3. Kết quả đã kiểm tra

| Flag Type | Sales Type | Count | Avg DIO |
|---|---|---:|---:|
| warning | zero_sales | 209 | 999.0 |
| warning | has_sales | 6 | 20.6 |

### 9.4. Diễn giải quan trọng

Trong lần chạy hiện tại, `anomaly_flag = true` không xuất hiện. Lý do là dữ liệu inventory hiện chỉ là snapshot tại một thời điểm, thiếu biến động lịch sử nên Isolation Forest không phát hiện anomaly thật sự. Tuy nhiên hệ thống vẫn phát hiện 209 sản phẩm có `zero_sales_flag = true`, đây là tín hiệu vận hành quan trọng.

Vì vậy khi vẽ Dashboard 3, không nên đặt tên biểu đồ là:

```text
Top Inventory Anomaly Products
```

Nên đặt là:

```text
Inventory Risk Flags — Zero-Sales & Slow-Moving Products
```

hoặc:

```text
Inventory Risk / Zero-Sales Warning Products
```

### 9.5. Kết luận

Dashboard 3 nên thể hiện output ML theo hướng inventory risk, zero-sales warning và decision support thay vì khẳng định có anomaly nghiêm trọng.

---

## 10. Decision Support Pre-check

### 10.1. Mục tiêu

Kiểm tra bảng `dw.decision_support` có dữ liệu khuyến nghị hành động để đưa vào Dashboard 3.

### 10.2. Query kiểm tra

```sql
SELECT entity_type,
       signal_type,
       priority,
       COUNT(*) AS count
FROM dw.decision_support
GROUP BY entity_type, signal_type, priority
ORDER BY entity_type, signal_type, priority;
```

### 10.3. Kết quả đã kiểm tra

| Metric | Kết quả |
|---|---:|
| Total decision support rows | 18,852 |
| HIGH priority | 8,339 |
| MEDIUM priority | 10,513 |
| Entity types | customer, product, inventory, operations |

### 10.4. Kết luận

Dashboard 3 nên có bảng:

- Operational Decision Support
- High/Medium Priority Actions
- Decision Support by Priority

---

## 11. DDL / Init Script Pre-check

### 11.1. Mục tiêu

Đảm bảo các bảng mới không chỉ được tạo thủ công trong database local, mà đã nằm trong file khởi tạo để người khác chạy lại được.

### 11.2. Query/lệnh kiểm tra

```bash
grep -c "CREATE TABLE" sql/ddl_script.sql
grep -c "CREATE TABLE" scripts/init_dw_tables.py

grep -R "ml_customer_segments\|ml_inventory_anomaly\|decision_support\|kpi_snapshot\|period_comparison\|rfm_snapshot\|customer_migration\|inventory_snapshot" -n sql scripts
```

### 11.3. Kết quả đã kiểm tra

| File | Kết quả |
|---|---:|
| `sql/ddl_script.sql` | 17 bảng |
| `scripts/init_dw_tables.py` | 17 bảng |

Các bảng đã bao gồm:

- `dw.ml_customer_segments`
- `dw.ml_customer_clustering_metrics`
- `dw.ml_inventory_anomaly`
- `dw.decision_support`
- `mart.kpi_snapshot`
- `mart.rfm_snapshot`
- `mart.customer_migration`
- `mart.period_comparison`
- `mart.inventory_snapshot`
- `mart.daily_sales_agg`

### 11.4. Kết luận

DDL/init script đạt yêu cầu. Môi trường mới có thể tạo lại đủ bảng phục vụ mart layer, ML output và dashboard.

---

## 12. Metabase Dashboard Pre-check

### 12.1. Mục tiêu

Kiểm tra dashboard đã được tạo từ dữ liệu đúng và không còn dùng dashboard cũ chỉ tính tổng toàn dataset.

### 12.2. Kết quả đã kiểm tra

Đã tạo 3 dashboard:

| Dashboard | ID | Số card | Nguồn dữ liệu chính |
|---|---:|---:|---|
| Business Performance Overview | 11 | 10 | `mart.kpi_snapshot`, `mart.period_comparison` |
| Product & Customer Analytics | 12 | 13 | `dw.ml_customer_segments`, `dw.fact_sales`, `mart.rfm_snapshot`, `dw.decision_support` |
| Inventory & Operational Decision Support | 13 | 12 | `dw.ml_inventory_anomaly`, `dw.fact_inventory`, `dw.decision_support` |

Đã xác nhận:

- Chỉ còn 3 dashboard chính sau khi xóa duplicate dashboard cũ.
- Cards trả dữ liệu live từ Metabase API.
- Các native SQL cards đọc từ `dw.*` và `mart.*`.

### 12.3. Việc cần kiểm tra thủ công lần cuối trên UI

Trước khi nộp hoặc export PDF, cần mở Metabase UI và kiểm tra bằng mắt:

1. Card có lỗi đỏ không.
2. Biểu đồ có đúng loại không: number, line, bar, pie, table.
3. Title có ghi rõ period như `2014Q2 vs 2014Q1` không.
4. Time-series có filter khoảng kỳ hợp lệ `2011Q2 → 2014Q2` không.
5. Dashboard 3 có dùng wording `Inventory Risk / Zero-Sales Warning`, không gọi quá mạnh là anomaly nếu `anomaly_flag = 0`.
6. Nếu cần, thêm dashboard-level filter `period_key`.

---

## 13. Mapping kết quả check vào dashboard

### 13.1. Dashboard 1 — Business Performance Overview (ID=11, 10 cards)

Dashboard này dùng để chứng minh nhóm đã sửa theo yêu cầu KPI có period/time-series.

Layout: 5 rows

| Row | Cards | Loại |
|---|---|---|
| 1 | 4 KPI number (Revenue, Gross Profit, Margin %, Order Count) | Scalar |
| 2 | Revenue & Gross Profit Trend | Line full-width |
| 3 | Gross Margin % Trend + Revenue by Category | Line + Bar |
| 4 | Contribution by Category + Contribution by Territory | Bar + Bar |
| 5 | KPI Comparison Table 2014Q2 vs 2014Q1 | Table full-width |

### 13.2. Dashboard 2 — Product & Customer Analytics (ID=12, 13 cards)

Dashboard này dùng để chứng minh tích hợp ML customer segmentation.

Layout: 6 rows

| Row | Cards | Loại |
|---|---|---|
| 1 | 4 KPI number (Active Customers, Products, Units, Avg Revenue) | Scalar |
| 2 | Customer Segments RFM + Segment Details | Bar + Table |
| 3 | ABC Product Class + Top 10 Products | Bar + Bar |
| 4 | Top 10 Customers | Table full-width |
| 5 | Segment Share by Quarter + Revenue by Customer Type | Line + Pie |
| 6 | Gross Margin % by Category + Cost vs Price Scatter | Bar + Scatter |

### 13.3. Dashboard 3 — Inventory & Operational Decision Support (ID=13, 12 cards)

Dashboard này dùng để chứng minh tích hợp ML inventory risk và decision support.

Layout: 5 rows

| Row | Cards | Loại |
|---|---|---|
| 1 | 4 KPI number (Risk Products, Zero-Sales, High Priority, Inventory Value) | Scalar |
| 2 | Inventory Risk Flags — Zero-Sales & Slow-Moving Products | Table full-width |
| 3 | Risk Count by Category + Inventory Value by Category | Bar + Bar |
| 4 | DIO vs Value Scatter + Inventory Snapshot Summary | Scatter + Table |
| 5 | Actions by Priority + High Priority Actions + Operational DS | Bar + Table + Table |

---

## 14. Kết luận cuối

Kết quả pre-check cho thấy hệ thống đã đủ điều kiện để vẽ lại dashboard theo yêu cầu mới:

1. Core DWH đã có dữ liệu thật và toàn vẹn.
2. Mart layer đã có KPI snapshot theo period.
3. Period comparison đã có dữ liệu để phân tích nguyên nhân biến động.
4. ML output đã được tạo bằng pipeline chuẩn qua `make` command.
5. Decision support đã có recommended actions.
6. Metabase đã tạo 3 dashboard đọc từ `dw.*` và `mart.*`.

Dashboard mới nên được trình bày theo logic:

```text
Selected Period → KPI Snapshot → Trend → Contribution/Drill-down → ML Output → Decision Support
```

Điều này chứng minh dashboard không chỉ là trực quan hóa mô tả, mà là lớp BI đọc từ mart layer và ML output để hỗ trợ phân tích và ra quyết định.

---

## 15. Ghi chú còn lại trước khi commit/nộp

- Không commit token/password Metabase thật trong `scripts/setup_metabase.py` hoặc log.
- Nếu script còn default password thật, nên đổi sang bắt buộc đọc từ biến môi trường:

```python
MB_EMAIL = os.environ["MB_EMAIL"]
MB_PASS = os.environ["MB_PASS"]
```

- Đã chạy lại ML pipeline (anomaly, migration, decision_support) với code mới.
- `avg_order_value` đã được rename thành `revenue_per_order` trong code — đã cập nhật SQL card D1-C10.
- Dashboard mới nhất đã rebuild bằng `scripts/setup_metabase.py`.
- Nếu có thời gian, test lại trên môi trường sạch bằng:

```bash
make init-db
make etl-full
make ml
make analytics-runner period=2014Q2
python scripts/setup_metabase.py
```

- Export lại PDF hoặc screenshot dashboard mới từ Metabase sau khi kiểm tra UI.
