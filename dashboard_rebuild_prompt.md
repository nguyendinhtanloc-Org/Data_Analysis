# PROMPT — Vẽ lại 3 Metabase Dashboard (chuẩn dữ liệu · đúng yêu cầu · đẹp · đa dạng biểu đồ)

> Dán toàn bộ nội dung dưới đây cho agent. Agent phải đọc kỹ **PHẦN 0 (ràng buộc bất biến)** trước khi tạo bất kỳ card nào. Vi phạm PHẦN 0 = làm lại.

---

## VAI TRÒ & MỤC TIÊU

Bạn là **BI Engineer** dựng dashboard trên **Metabase (v0.50.1)** đọc từ **PostgreSQL** (`adventureworks_dw`). Nhiệm vụ: tạo lại **3 dashboard** bằng **native SQL cards**, đảm bảo đồng thời 4 tiêu chí:

1. **Đúng dữ liệu** — số liệu khớp mart layer & ML output đã pre-check, không bịa, không gọi sai bản chất (xem PHẦN 0).
2. **Đúng yêu cầu** — thể hiện rõ 3 yêu cầu của giảng viên (xem PHẦN 1).
3. **Đẹp & chuyên nghiệp** — theo design system ở PHẦN 2 (màu, format số, tiêu đề, layout grid).
4. **Đa dạng biểu đồ** — mỗi dashboard dùng ≥ 4 loại visualization khác nhau (scalar, line, bar/row, pie, table, scatter, combo).

Mọi card là **native SQL question**. Không dùng GUI query builder. Mỗi card phải có: `name`, `sql`, `display type`, `visualization_settings` (màu + format), vị trí grid (`row/col/size_x/size_y`, lưới 24 cột).

> ⚠️ **Toàn bộ SQL trong tài liệu này là VÍ DỤ THAM KHẢO, không phải lệnh cứng.** Tên bảng, tên cột và **giá trị `kpi_name`/`cluster_label`/`category`** phải được xác minh với database thực tế ở BƯỚC 0 trước khi dùng. Nếu DB khác (ví dụ `kpi_name` là `total_revenue` thay vì `revenue`), **dùng giá trị trong DB làm chuẩn** và sửa SQL cho khớp. Tuyệt đối **không tự tạo/chế thêm dữ liệu mới**; chỉ đọc từ những gì đã có.

---

## BƯỚC 0 — VALIDATE SCHEMA & DỮ LIỆU (bắt buộc, làm TRƯỚC khi tạo bất kỳ card nào)

Chạy các truy vấn thăm dò và ghi lại kết quả. Nếu kết quả khác các giá trị giả định trong prompt → **DB là chân lý**, cập nhật SQL/nhãn theo DB (đồng thời vẫn giữ các quy tắc bản chất ở PHẦN 0, ví dụ không gọi "anomaly" khi anomaly_flag=0).

```sql
-- Cấu trúc & số dòng các bảng cốt lõi
SELECT table_schema, table_name FROM information_schema.tables
WHERE table_schema IN ('mart','dw') ORDER BY 1,2;
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema='mart' AND table_name='kpi_snapshot' ORDER BY ordinal_position;

-- Các giá trị dùng để lọc/nhóm (KHÔNG hardcode nếu khác)
SELECT DISTINCT kpi_name         FROM mart.kpi_snapshot        ORDER BY 1;
SELECT DISTINCT period_key, period_type FROM mart.kpi_snapshot ORDER BY 1;
SELECT DISTINCT cluster_label, COUNT(*) FROM dw.ml_customer_segments GROUP BY 1;
SELECT DISTINCT category         FROM dw.ml_inventory_anomaly   ORDER BY 1;
SELECT DISTINCT entity_type, priority FROM dw.decision_support  ORDER BY 1,2;

-- Xác định kỳ mới nhất & kỳ liền trước để dùng động (thay cho hardcode)
SELECT MAX(period_key) AS latest_period FROM mart.kpi_snapshot
WHERE period_type='quarter' AND value IS NOT NULL AND value <> 0;
```

Lập một **bảng mapping** (giá trị prompt → giá trị thực trong DB) rồi mới sang các bước vẽ. Nếu một `kpi_name` giả định không tồn tại, tìm cột/tên tương đương thay vì bỏ card.

---

## PHẦN 0 — RÀNG BUỘC DỮ LIỆU BẤT BIẾN (đọc trước, tuyệt đối không vi phạm)

Đây là các sự thật đã được pre-check. Card nào mâu thuẫn với danh sách này là SAI.

**0.1. Phạm vi kỳ hợp lệ.** Dữ liệu bán hàng chỉ có **2011Q2 → 2014Q2**. Mọi biểu đồ time-series PHẢI filter:
```sql
WHERE period_key BETWEEN '2011Q2' AND '2014Q2'
```
Không vẽ 2011Q1 (chưa có data), 2014Q3/Q4 (rỗng → giá trị 0 gây hiểu nhầm).

**0.2. Kỳ hiện tại = kỳ mới nhất có dữ liệu (động), kỳ so sánh = kỳ liền trước.** Ưu tiên lấy `curr = MAX(period_key)` từ BƯỚC 0 (để dashboard vẫn đúng khi refresh data sau này) thay vì hardcode. Với dataset AdventureWorks hiện tại, latest = **`2014Q2`** và prev = **`2014Q1`** — dùng làm giá trị mặc định/fallback. Tiêu đề card vẫn ghi rõ kỳ đang hiển thị (ví dụ `Revenue — 2014Q2`, `KPI Comparison — 2014Q2 vs 2014Q1`); nếu dùng filter động thì để tiêu đề `... — Current Period` và hiện kỳ qua subtitle. Trong native SQL nên tham số hóa: `WHERE period_key = {{period}}` với default = latest.

**0.3. Clustering: K = 3 (KHÔNG phải 4).** Chọn K bằng **silhouette score** (`choose_best_k`, k=2..7), silhouette ≈ **0.48**. Ba nhãn và phân bố:
| cluster_label | customer_count |
|---|---|
| Loyal Customers | 14,078 |
| Champions | 4,149 |
| Potential Loyalists | 442 |
Không dùng chữ "heuristic", không ghi k=4.

**0.4. Inventory: KHÔNG có anomaly thật.** `anomaly_flag = 0 sản phẩm`. Chỉ có **209 zero-sales warning** + **6 has-sales warning**. Isolation Forest `contamination = 0.06`.
- CẤM đặt tên card kiểu "Top Anomaly Products", "Inventory Anomalies".
- Dùng wording: **"Inventory Risk / Zero-Sales Warning"**, **"Slow-Moving & Zero-Sales Products"**.
- Cột dùng: `zero_sales_flag`, `days_inventory_outstanding` (DIO), `inventory_value`.

**0.5. `inventory_turnover = 0` toàn kỳ** (inventory chỉ là snapshot, thiếu lịch sử). CẤM vẽ "Inventory Turnover Trend" (sẽ là đường phẳng = 0). Thay bằng **"Inventory Snapshot Summary"** (Top sản phẩm theo inventory_value) hoặc **"DIO vs Inventory Value — Risk Map"** (scatter).

**0.6. Root cause đã chốt:** Doanh thu 2014Q2 giảm **-43.9%** ($7.21M vs $12.85M). Driver chính: **Bikes -50.1% (đóng góp -97.0%)**; theo customer_type: **Individual -100.0%**. Biên lợi nhuận gộp **tăng +48.7%** (14.6% → 21.7%). HHI = **0.761** (Bikes chiếm 86.8%). Các con số này lấy từ `mart.period_comparison`, không tính lại thủ công khác đi.

**0.7. Decision support:** tổng **18,852 rows** (8,339 HIGH + 10,513 MEDIUM). entity_type ∈ {customer, product, inventory, operations, kpi}.

**0.8. Schema cột chuẩn** (dùng đúng tên, không đoán):
- `mart.kpi_snapshot(kpi_name, period_type, period_key, period_start, period_end, value, dimension, dimension_value)`
- `mart.period_comparison(kpi_name, curr_period_key, prev_period_key, dimension, dimension_value, curr_value, prev_value, abs_change, pct_change, contribution_pct, is_significant, p_value, effect_size)`
- `mart.rfm_snapshot(period_key, cluster_label, customer_count, avg_recency, avg_frequency, avg_monetary, total_monetary, pct_of_total)`
- `mart.customer_migration(customer_key, prev_period_key, curr_period_key, prev_cluster, curr_cluster, prev_monetary, curr_monetary, is_churned, is_new)`
- `dw.ml_customer_segments(customer_key, full_name, recency_days, frequency, monetary, cluster_id, cluster_label, silhouette_score)`
- `dw.ml_inventory_anomaly(product_key, product_name, category, subcategory, avg_quantity, inventory_value, units_sold, days_inventory_outstanding, anomaly_flag, anomaly_score, zero_sales_flag)`
- `dw.decision_support(entity_type, entity_key, signal_type, priority, recommended_action, reason)`
- `dw.fact_sales(date_key, product_key, customer_key, territory_key, order_qty, unit_price, line_total, standard_cost, gross_profit, sales_order_id)` + dims `dw.dim_product(category, subcategory, name, standard_cost, is_current)`, `dw.dim_customer(customer_type, country)`, `dw.dim_date(date, year, quarter, month)`.

---

## PHẦN 1 — 3 YÊU CẦU CỦA GIẢNG VIÊN (dashboard phải chứng minh được)

Agent phải bố trí card sao cho người xem nhìn ra ngay:

1. **Có tầng snapshot lưu KPI theo kỳ.** → Mọi KPI time-series đọc từ `mart.kpi_snapshot` (không SUM toàn `fact_sales`). Trong mô tả dashboard ghi rõ "Source: mart.kpi_snapshot (snapshot theo quý)".
2. **KPI có biên thời gian, không lấy cả dataset.** → Card scalar luôn kèm kỳ (`... — 2014Q2`); card trend chạy theo `period_key` từng quý. Nếu có thể, thêm 1 card cấp năm (`period_type = 'year'`) để nhấn "từ đầu năm → cuối năm".
3. **Phân tích sâu — phát hiện vấn đề + nguyên nhân bằng dữ liệu.** → Bắt buộc có cụm card **Contribution / Root-cause** đọc từ `mart.period_comparison` (by category, by territory, by customer_type) + drill-down, thể hiện chuỗi "Δ tổng → dimension đóng góp lớn nhất".

Luồng đọc mỗi dashboard nên tuân theo: **KPI hiện tại → Trend → Contribution/Drill-down → ML output → Decision Support**.

---

## PHẦN 2 — DESIGN SYSTEM (đẹp · format đỉnh · nhất quán)

### 2.1. Bảng màu (hex — set trong series settings mỗi card)

| Vai trò | Màu | Dùng cho |
|---|---|---|
| Revenue / primary | `#2563EB` | doanh thu, line chính |
| Gross profit / positive | `#16A34A` | lợi nhuận, biến động dương |
| Margin | `#7C3AED` | biên lợi nhuận % |
| Negative / alert | `#DC2626` | biến động âm, contribution âm |
| Warning / risk | `#F59E0B` | zero-sales, HIGH priority |
| Neutral | `#64748B` / lưới `#E2E8F0` | trục, gridline, text phụ |

**Category (Bikes/Components/Clothing/Accessories):** `#2563EB`, `#7C3AED`, `#EC4899`, `#14B8A6`
**Segment (Champions/Loyal/Potential Loyalists):** `#F59E0B` (gold), `#2563EB`, `#10B981`
**ABC class (A/B/C):** `#16A34A`, `#F59E0B`, `#94A3B8`
**Priority (HIGH/MEDIUM/LOW):** `#DC2626`, `#F59E0B`, `#94A3B8`

Quy tắc màu: **xanh = tốt, đỏ = xấu, hổ phách = cảnh báo**. Áp dụng nhất quán toàn bộ 3 dashboard.

### 2.2. Format số (đặt trong column formatting)
- Tiền: prefix `$`, ngăn cách nghìn, rút gọn (`$7.21M`, `$1,320`). Với card scalar tiền lớn bật **compact/abbreviate**.
- %: 1 chữ số thập phân, có dấu (`+48.7%`, `-43.9%`).
- pp (điểm phần trăm) cho thay đổi margin: ghi `+7.1pp` trong tiêu đề/subtitle.
- Số nguyên (KH, đơn, sản phẩm): ngăn cách nghìn, không thập phân.

### 2.3. Scalar (Number) cards
- Bật **comparison to previous value** khi Metabase hỗ trợ, hoặc nhúng Δ% vào subtitle.
- Màu điều kiện: giá trị tăng tốt → xanh; giảm xấu → đỏ. Doanh thu giảm 43.9% để đỏ; margin tăng để xanh.

### 2.4. Table cards
- Bật **conditional formatting**: pct_change/contribution âm → nền đỏ nhạt, dương → xanh nhạt; priority HIGH → chữ/nền đỏ.
- Sắp xếp giảm dần theo cột quan trọng (|contribution|, DIO, monetary).
- Giới hạn cột hiển thị, đặt lại header tiếng người đọc được (không để `pct_change` trần → "Δ %").

### 2.5. Line / trend
- Có **goal line** hoặc trend line khi hợp lý. Line mượt, marker ở điểm dữ liệu.
- Trục X = period_key theo thứ tự thời gian; **ép filter 2011Q2–2014Q2**.

### 2.6. Layout (lưới 24 cột Metabase)
- **Row 1 = 4 scalar KPI** (mỗi cái `size_x=6`) — "at a glance".
- Các row sau: trộn full-width (`size_x=24`) và nửa (`size_x=12`).
- Chiều cao: scalar `size_y=3`, chart `size_y=6`, table lớn `size_y=6–8`.
- Không để 2 pie cạnh nhau; xen kẽ loại biểu đồ giữa các row để "đa dạng".
- Mỗi dashboard có **1 text card tiêu đề** ở trên cùng mô tả mục tiêu + nguồn (mart snapshot) + kỳ.

### 2.7. Bộ lọc dashboard-level
- Thêm filter `period_key` (default `2014Q2`) map vào các card dùng biến `{{period}}`.
- Card scalar/comparison dùng field-filter hoặc biến để đổi kỳ linh hoạt (chứng minh KPI có biên thời gian).

---

## PHẦN 3 — SPEC CHI TIẾT DASHBOARD 1: Business Performance Overview

**Mục tiêu:** tổng quan hiệu quả kinh doanh theo kỳ + phân tích nguyên nhân biến động. Nguồn chính: `mart.kpi_snapshot`, `mart.period_comparison`. Chứng minh yêu cầu #1 và #3.

**Row 1 — 4 scalar (size_y=3):**

- **C1 · Revenue — 2014Q2** (đỏ, giảm)
```sql
SELECT value AS revenue
FROM mart.kpi_snapshot
WHERE kpi_name='revenue' AND period_key='2014Q2' AND dimension='overall';
```
- **C2 · Gross Profit — 2014Q2**
```sql
SELECT value FROM mart.kpi_snapshot
WHERE kpi_name='gross_profit' AND period_key='2014Q2' AND dimension='overall';
```
- **C3 · Gross Margin % — 2014Q2** (xanh, tăng)
```sql
SELECT value FROM mart.kpi_snapshot
WHERE kpi_name='gross_margin_pct' AND period_key='2014Q2' AND dimension='overall';
```
- **C4 · Orders — 2014Q2**
```sql
SELECT value FROM mart.kpi_snapshot
WHERE kpi_name='order_count' AND period_key='2014Q2' AND dimension='overall';
```

**Row 2 — Combo/Line full-width (size_x=24, size_y=6): Revenue & Gross Profit Trend by Quarter**
```sql
SELECT period_key,
       MAX(CASE WHEN kpi_name='revenue'      THEN value END) AS revenue,
       MAX(CASE WHEN kpi_name='gross_profit' THEN value END) AS gross_profit
FROM mart.kpi_snapshot
WHERE dimension='overall'
  AND kpi_name IN ('revenue','gross_profit')
  AND period_key BETWEEN '2011Q2' AND '2014Q2'
GROUP BY period_key ORDER BY period_key;
```
Display: **combo** (revenue = bar `#2563EB`, gross_profit = line `#16A34A`).

**Row 3 — 2 nửa (size_x=12, size_y=6):**
- **C6 · Gross Margin % Trend** (line `#7C3AED`, goal line = giá trị 2014Q2)
```sql
SELECT period_key, value AS gross_margin_pct
FROM mart.kpi_snapshot
WHERE kpi_name='gross_margin_pct' AND dimension='overall'
  AND period_key BETWEEN '2011Q2' AND '2014Q2'
ORDER BY period_key;
```
- **C7 · Revenue by Category — 2014Q2** (bar/row, màu category)
```sql
SELECT dimension_value AS category, value AS revenue
FROM mart.kpi_snapshot
WHERE kpi_name='revenue_by_category' AND period_key='2014Q2'
ORDER BY value DESC;
```

**Row 4 — Root cause, 2 nửa (size_x=12, size_y=6): (yêu cầu #3)** — cả 2 dùng **Horizontal Bar (row chart)** để đọc nhãn dimension dễ hơn; tô màu theo dấu: contribution âm = `#DC2626`, dương = `#16A34A`.
- **C8 · Revenue Change Contribution by Category — 2014Q2 vs 2014Q1** (horizontal bar)
```sql
SELECT dimension_value AS category, contribution_pct, pct_change
FROM mart.period_comparison
WHERE kpi_name='revenue' AND curr_period_key='2014Q2' AND dimension='category'
ORDER BY contribution_pct ASC;
```
- **C9 · Revenue Change Contribution by Territory (Top 10)** (horizontal bar)
```sql
SELECT dimension_value AS territory, contribution_pct, pct_change
FROM mart.period_comparison
WHERE kpi_name='revenue' AND curr_period_key='2014Q2' AND dimension='territory'
ORDER BY ABS(contribution_pct) DESC LIMIT 10;
```

**Row 5 — KPI Comparison Table full-width (size_x=24, size_y=6): 2014Q2 vs 2014Q1**
```sql
SELECT c.kpi_name AS "KPI",
       c.curr_value AS "2014Q2",
       c.prev_value AS "2014Q1",
       c.abs_change AS "Δ",
       c.pct_change AS "Δ %"
FROM mart.period_comparison c
WHERE c.curr_period_key='2014Q2' AND c.dimension='overall'
  AND c.kpi_name IN ('revenue','gross_profit','gross_margin_pct',
                     'order_count','total_customers','avg_order_value','revenue_per_customer')
ORDER BY c.kpi_name;
```
Conditional formatting cột "Δ %": âm đỏ, dương xanh.

*(Tùy chọn chứng minh biên thời gian theo NĂM):* thêm 1 card line dùng `period_type='year'` nếu snapshot năm tồn tại.

---

## PHẦN 4 — SPEC CHI TIẾT DASHBOARD 2: Product & Customer Analytics

**Mục tiêu:** RFM segmentation (K=3), hiệu suất sản phẩm (ABC), hành vi KH. Nguồn: `dw.ml_customer_segments`, `mart.rfm_snapshot`, `dw.fact_sales`+dims, `dw.decision_support`.

**Row 1 — 4 scalar (2014Q2, filter fact_sales theo dim_date):**
- **C1 · Active Customers** — `COUNT(DISTINCT customer_key)`
- **C2 · Active Products** — `COUNT(DISTINCT product_key)`
- **C3 · Units Sold** — `SUM(order_qty)`
- **C4 · Revenue / Customer** — `SUM(line_total)/COUNT(DISTINCT customer_key)`
```sql
-- mẫu C1 (đổi biểu thức cho C2–C4)
SELECT COUNT(DISTINCT f.customer_key) AS active_customers
FROM dw.fact_sales f JOIN dw.dim_date d ON f.date_key=d.date_key
WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30';
```

**Row 2 — 2 nửa: (RFM K-Means, đa dạng bar + table)**
- **C5 · Customer Segments — RFM K-Means (K=3)** (bar, màu segment)
```sql
SELECT cluster_label,
       COUNT(*) AS customers,
       ROUND(SUM(monetary),0) AS total_monetary
FROM dw.ml_customer_segments
GROUP BY cluster_label ORDER BY customers DESC;
```
- **C6 · RFM Segment Details** (table)
```sql
SELECT cluster_label AS "Segment",
       COUNT(*) AS "Customers",
       ROUND(AVG(recency_days),1) AS "Avg Recency (d)",
       ROUND(AVG(frequency),1)    AS "Avg Frequency",
       ROUND(AVG(monetary),2)     AS "Avg Monetary"
FROM dw.ml_customer_segments
GROUP BY cluster_label ORDER BY "Customers" DESC;
```
Subtitle card: "K=3 chọn bằng silhouette ≈ 0.48".

**Row 3 — 2 nửa:**
- **C7 · Revenue Share by ABC Product Class — 2014Q2** (bar xếp chồng hoặc pie, màu ABC)
```sql
WITH prod AS (
  SELECT p.product_id, SUM(f.line_total) AS rev
  FROM dw.fact_sales f
  JOIN dw.dim_date d ON f.date_key=d.date_key
  JOIN dw.dim_product p ON f.product_key=p.product_key
  WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'
  GROUP BY p.product_id
), ranked AS (
  SELECT rev, SUM(rev) OVER (ORDER BY rev DESC) / SUM(rev) OVER () AS cum_share
  FROM prod
)
SELECT CASE WHEN cum_share<=0.8 THEN 'A' WHEN cum_share<=0.95 THEN 'B' ELSE 'C' END AS abc_class,
       COUNT(*) AS products, ROUND(SUM(rev),0) AS revenue
FROM ranked GROUP BY 1 ORDER BY 1;
```
- **C8 · Top 10 Products by Revenue — 2014Q2** (row/bar ngang `#2563EB`)
```sql
SELECT p.name AS product, SUM(f.line_total) AS revenue
FROM dw.fact_sales f
JOIN dw.dim_date d ON f.date_key=d.date_key
JOIN dw.dim_product p ON f.product_key=p.product_key
WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'
GROUP BY p.name ORDER BY revenue DESC LIMIT 10;
```

**Row 4 — Top 10 Customers full-width (table, size_x=24):**
```sql
SELECT c.full_name AS "Customer", c.customer_type AS "Type", c.country AS "Country",
       COUNT(DISTINCT f.sales_order_id) AS "Orders",
       ROUND(SUM(f.line_total),0) AS "Revenue"
FROM dw.fact_sales f
JOIN dw.dim_date d ON f.date_key=d.date_key
JOIN dw.dim_customer c ON f.customer_key=c.customer_key
WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'
GROUP BY c.full_name,c.customer_type,c.country
ORDER BY "Revenue" DESC LIMIT 10;
```

**Row 5 — 2 nửa: (segment theo thời gian + cơ cấu KH)**
- **C10 · Customer Segment Share by Quarter** (line, 1 đường/segment)
```sql
SELECT period_key, cluster_label, pct_of_total
FROM mart.rfm_snapshot
WHERE period_key BETWEEN '2013Q1' AND '2014Q2'
ORDER BY period_key, cluster_label;
```
- **C11 · Revenue by Territory — 2014Q2** (**Donut**, không dùng Pie 2 lát). *Lý do:* doanh thu theo customer_type ở kỳ này gần như 100% Individual → pie vô nghĩa. Đổi sang phân bố nhiều lát theo territory/country.
```sql
SELECT t.territory_name AS territory, SUM(f.line_total) AS revenue
FROM dw.fact_sales f
JOIN dw.dim_date d ON f.date_key=d.date_key
JOIN dw.dim_territory t ON f.territory_key=t.territory_key
WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'
GROUP BY t.territory_name ORDER BY revenue DESC;
```

**Row 6b — Heatmap full-width (size_x=24, size_y=6): Revenue Heatmap — Customer Type × Category** (giống BI chuyên nghiệp, "đa dạng biểu đồ"). Metabase: dùng **pivot table với conditional color** hoặc heatmap; trục hàng = customer_type, cột = category, giá trị = revenue, thang màu tuần tự (nhạt→đậm `#2563EB`).
```sql
SELECT c.customer_type, p.category, SUM(f.line_total) AS revenue
FROM dw.fact_sales f
JOIN dw.dim_date d ON f.date_key=d.date_key
JOIN dw.dim_customer c ON f.customer_key=c.customer_key
JOIN dw.dim_product p  ON f.product_key=p.product_key
WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'
GROUP BY c.customer_type, p.category
ORDER BY c.customer_type, revenue DESC;
```
*(Biến thể nếu muốn: đổi `c.customer_type` → `c.country` để có Country × Category.)*

**Row 6 — 2 nửa: (margin + scatter)**
- **C12 · Gross Margin % by Category — 2014Q2** (bar, màu category)
```sql
SELECT p.category,
       ROUND(SUM(f.gross_profit)/NULLIF(SUM(f.line_total),0)*100,1) AS gross_margin_pct
FROM dw.fact_sales f
JOIN dw.dim_date d ON f.date_key=d.date_key
JOIN dw.dim_product p ON f.product_key=p.product_key
WHERE d.date BETWEEN '2014-04-01' AND '2014-06-30'
GROUP BY p.category ORDER BY gross_margin_pct DESC;
```
- **C13 · Cost vs Selling Price (Scatter)** — mỗi điểm 1 sản phẩm, màu theo category
```sql
SELECT p.name, p.category, p.standard_cost AS cost, p.list_price AS price
FROM dw.dim_product p
WHERE p.is_current AND p.list_price>0;
```

---

## PHẦN 5 — SPEC CHI TIẾT DASHBOARD 3: Inventory & Operational Decision Support

**Mục tiêu:** rủi ro tồn kho (zero-sales/slow-moving), giá trị tồn kho, khuyến nghị vận hành. Nguồn: `dw.ml_inventory_anomaly`, `dw.decision_support`, `dw.fact_inventory`+`dim_product`.
**Wording bắt buộc:** "Risk / Zero-Sales Warning" — KHÔNG dùng "anomaly" (0.4, 0.5).

**Row 1 — 4 scalar:**
- **C1 · Inventory Risk Products** (`#F59E0B`)
```sql
SELECT COUNT(*) FROM dw.ml_inventory_anomaly WHERE anomaly_flag OR zero_sales_flag;
```
- **C2 · Zero-Sales Warnings**
```sql
SELECT COUNT(*) FROM dw.ml_inventory_anomaly WHERE zero_sales_flag;
```
- **C3 · High-Priority Actions** (`#DC2626`)
```sql
SELECT COUNT(*) FROM dw.decision_support WHERE priority='HIGH';
```
- **C4 · Total Inventory Value**
```sql
SELECT ROUND(SUM(inventory_value),0) FROM dw.ml_inventory_anomaly;
```

**Row 2 — Risk Flags Table full-width (size_x=24, size_y=6): Zero-Sales & Slow-Moving Products**
```sql
SELECT product_name AS "Product", category AS "Category",
       ROUND(inventory_value,0) AS "Inv Value",
       units_sold AS "Units Sold",
       ROUND(days_inventory_outstanding,0) AS "DIO",
       CASE WHEN zero_sales_flag THEN 'Zero-Sales' ELSE 'Slow-Moving' END AS "Risk"
FROM dw.ml_inventory_anomaly
WHERE zero_sales_flag OR days_inventory_outstanding>=180
ORDER BY days_inventory_outstanding DESC, inventory_value DESC
LIMIT 50;
```
Conditional format: "Risk"=Zero-Sales → nền hổ phách; DIO cao → đỏ dần.

**Row 3 — 2 nửa:**
- **C6 · Inventory Risk Count by Category** (bar, màu category)
```sql
SELECT category,
       COUNT(*) FILTER (WHERE zero_sales_flag) AS zero_sales,
       ROUND(AVG(days_inventory_outstanding),1) AS avg_dio
FROM dw.ml_inventory_anomaly
GROUP BY category ORDER BY zero_sales DESC;
```
- **C7 · Inventory Value by Category** (**Treemap** nếu bản Metabase hỗ trợ — đẹp và trực quan tỷ trọng; nếu không hỗ trợ, fallback **Horizontal Bar** `#2563EB`, không dùng vertical bar)
```sql
SELECT category, ROUND(SUM(inventory_value),0) AS inv_value
FROM dw.ml_inventory_anomaly
GROUP BY category ORDER BY inv_value DESC;
```

**Row 4 — 2 nửa: (thay cho turnover trend — xem 0.5)**
- **C8 · DIO vs Inventory Value — Risk Map (Bubble Chart)** — nâng scatter thành **bubble** để mã hóa 4 chiều: **X = Inventory Value, Y = DIO, bubble size = Avg Quantity, màu = Zero-Sales / Has-Sales**. Điểm to + góc trên-phải = rủi ro cao nhất (nhiều vốn, DIO lớn, tồn nhiều). Trong Metabase: scatter với **Bubble size** = cột thứ 3.
```sql
SELECT product_name, category,
       inventory_value,
       days_inventory_outstanding AS dio,
       avg_quantity,
       CASE WHEN zero_sales_flag THEN 'Zero-Sales' ELSE 'Has-Sales' END AS status
FROM dw.ml_inventory_anomaly
WHERE inventory_value>0;
```
- **C9 · Inventory Snapshot Summary — Top 20 by Value** (table)
```sql
SELECT product_name AS "Product", category AS "Category",
       ROUND(avg_quantity,0) AS "Avg Qty",
       ROUND(inventory_value,0) AS "Inv Value",
       ROUND(days_inventory_outstanding,0) AS "DIO"
FROM dw.ml_inventory_anomaly
ORDER BY inventory_value DESC LIMIT 20;
```

**Row 5 — 3 card (size_x=8 mỗi cái): Decision Support**
- **C10 · Actions by Priority** (bar, màu priority)
```sql
SELECT priority, COUNT(*) AS actions
FROM dw.decision_support
GROUP BY priority ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END;
```
- **C11 · High-Priority Actions** (table)
```sql
SELECT entity_type AS "Entity", signal_type AS "Signal", recommended_action AS "Action"
FROM dw.decision_support WHERE priority='HIGH'
ORDER BY entity_type LIMIT 30;
```
- **C12 · Operational Decision Support (Inventory/Product)** (table)
```sql
SELECT signal_type AS "Signal", priority AS "Priority", recommended_action AS "Action"
FROM dw.decision_support
WHERE entity_type IN ('product','inventory','operations')
ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END LIMIT 30;
```

---

## PHẦN 6 — QUY TRÌNH THỰC HIỆN (agent làm theo)

1. **Tạo/kiểm tra Metabase database connection** tới `adventureworks_dw`. 
2. Với mỗi card: tạo native question (POST `/api/card`) → set `display` + `visualization_settings` (màu, format, conditional formatting) theo PHẦN 2.
3. Tạo 3 dashboard (POST `/api/dashboard`), thêm **text card tiêu đề** đầu mỗi dashboard.
4. Thêm dashcards với đúng `row/col/size_x/size_y` (lưới 24 cột) theo layout từng PHẦN.
5. Thêm **dashboard filter `period_key`** (default `2014Q2`) map vào card có biến.
6. Xóa dashboard/card cũ trùng lặp để chỉ còn đúng 3 dashboard.
7. Chạy **checklist PHẦN 7**. Chỗ nào fail thì sửa rồi export lại.

---

## PHẦN 7 — CHECKLIST NGHIỆM THU (agent tự kiểm trước khi báo xong)

**Đúng dữ liệu**
- [ ] Không card nào chứa chữ "anomaly" khi mô tả inventory (anomaly_flag=0).
- [ ] Không có card "Inventory Turnover Trend" (turnover=0).
- [ ] Clustering ghi K=3, silhouette≈0.48; không có k=4.
- [ ] Contribution card khớp: Bikes -97.0%, Individual -100.0%.
- [ ] Mọi time-series filter `period_key BETWEEN '2011Q2' AND '2014Q2'`.

**Đúng yêu cầu**
- [ ] KPI time-series đọc từ `mart.kpi_snapshot` (không SUM toàn fact_sales).
- [ ] Card scalar/comparison đều gắn kỳ (2014Q2) — chứng minh biên thời gian.
- [ ] Có cụm Contribution/Root-cause từ `mart.period_comparison` (category + territory + customer_type).

**Đẹp & đa dạng**
- [ ] Mỗi dashboard ≥ 5 loại visualization khác nhau (scalar, combo, horizontal bar, line, table, pie/donut, scatter/bubble, heatmap, treemap).
- [ ] Dashboard 1 dùng **combo** cho Revenue/Gross Profit và **horizontal bar** cho contribution.
- [ ] Dashboard 2 có **heatmap** (Customer Type × Category) và **donut** (không còn pie 2 lát vô nghĩa).
- [ ] Dashboard 3 dùng **bubble chart** (X=Inv Value, Y=DIO, size=Avg Qty, màu=Zero/Has-Sales) và **treemap** (hoặc horizontal bar) cho Inventory Value by Category.
- [ ] Màu áp đúng quy ước (xanh=tốt, đỏ=xấu, hổ phách=cảnh báo), nhất quán 3 dashboard.
- [ ] Tiền/%/số nguyên format đúng; table có conditional formatting.
- [ ] Row 1 mỗi dashboard = 4 scalar; có **text card mô tả** (nội dung PHẦN 8.1) ở đầu mỗi dashboard.

**Kỹ thuật**
- [ ] Đã chạy **BƯỚC 0 validate schema**; SQL dùng đúng tên bảng/cột/`kpi_name` thực tế trong DB (không hardcode nếu DB khác).
- [ ] Filter kỳ ưu tiên **latest period động** (`MAX(period_key)`), 2014Q2 chỉ là default/fallback.
- [ ] Không hardcode token/password trong bất kỳ script nào.
- [ ] Chỉ còn đúng 3 dashboard, card không lỗi đỏ khi mở UI.
- [ ] Tiêu đề card ghi rõ kỳ, ví dụ `... — 2014Q2` hoặc `2014Q2 vs 2014Q1`.

