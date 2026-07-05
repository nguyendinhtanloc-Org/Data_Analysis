# Tổng kết các cải tiến dự án

Tài liệu này mô tả những thay đổi đã được thực hiện để cải tiến đồ án Data Warehouse & Business Analytics, dựa trên các yêu cầu từ buổi bảo vệ.

---

## 1. Mart Layer — Tầng lưu trữ chỉ số theo thời gian

### Vấn đề ban đầu

KPI được tính trực tiếp từ Star Schema mỗi khi dashboard load. Điều này gây ra hai vấn đề:
- Không lưu lại lịch sử KPI theo từng kỳ (quý, tháng, năm)
- Khi dữ liệu nguồn thay đổi (do SCD Type 2, update), KPI quá khứ có thể bị sai lệch
- Không có biên thời gian cố định — mặc định lấy toàn bộ dataset

### Giải pháp

Tạo schema `mart` trong PostgreSQL gồm 5 bảng lưu trữ snapshot:

| Bảng | Chức năng |
|---|---|
| `mart.kpi_snapshot` | Lưu KPI (doanh thu, lợi nhuận, biên lãi, số đơn hàng...) theo từng quý/năm, có thể phân ra theo dimension (territory, category, customer_type) |
| `mart.rfm_snapshot` | Lưu phân phối cụm khách hàng (Champions, Loyal, At-Risk...) theo từng quý |
| `mart.customer_migration` | Theo dõi từng khách hàng di chuyển giữa các cụm qua các kỳ (ví dụ: từ Champions sang At-Risk) |
| `mart.inventory_snapshot` | Lưu chỉ số tồn kho theo từng quý cho từng sản phẩm |
| `mart.period_comparison` | Lưu kết quả so sánh period-over-period (có contribution %, p-value, effect size) |

### Cách hoạt động

Mỗi khi chạy ETL xong, pipeline tự động gọi `run_kpi_snapshot()` để:
1. Đọc watermark snapshot từ config.json (vd: "2014Q1")
2. Xác định các kỳ chưa được tính (vd: 2014Q2, 2014Q3...)
3. Tính toán KPI với time-bound (start_date, end_date) — không lấy toàn bộ dataset
4. UPSERT vào bảng snapshots (không tạo duplicate)
5. Cập nhật watermark

Nhờ có tầng này, Metabase dashboard có thể query trực tiếp từ bảng snapshot mà không cần tính lại KPI.

### Các file đã thay đổi

- `sql/ddl_script.sql`: Thêm CREATE SCHEMA mart + 5 bảng
- `scripts/init_dw_tables.py`: Thêm DDL cho mart schema
- `config.json`: Thêm `snapshot_watermark` để theo dõi tiến độ snapshot

---

## 2. Advanced Analytics — Tầng phân tích chuyên sâu

### Vấn đề ban đầu

Đồ án chỉ dừng ở mức "mô tả" (descriptive analytics). Cụ thể:
- Biết doanh thu giảm nhưng không biết tại sao
- Biết khách hàng thuộc cụm "At-Risk" nhưng không biết lý do họ rời bỏ
- Không có kiểm định thống kê để xác nhận các nhận xét

### Giải pháp

Tạo package `src/analytics/` gồm 8 module:

#### a) KPI Engine (`kpi_calculator.py`)

Định nghĩa sẵn **10 KPI cơ bản** và **6 KPI theo dimension**. Mỗi KPI đều có SQL query riêng với tham số `start_date` và `end_date`:

**KPI cơ bản (overall):**
| KPI | Ý nghĩa | Công thức |
|---|---|---|
| `revenue` | Tổng doanh thu | SUM(line_total) |
| `gross_profit` | Lợi nhuận gộp | SUM(gross_profit) |
| `gross_margin_pct` | Biên lãi gộp (%) | GP / Revenue × 100 |
| `order_count` | Số lượng đơn hàng | COUNT(DISTINCT sales_order_detail_id) |
| `total_customers` | Tổng khách hàng | COUNT(DISTINCT customer_key) |
| `avg_order_value` | Giá trị đơn hàng trung bình | Revenue / Order Count |
| `revenue_per_customer` | Doanh thu trên mỗi khách hàng | Revenue / Customer Count |
| `inventory_turnover` | Vòng quay hàng tồn kho | COGS / Avg Inventory Value |
| `repeat_customer_rate` | Tỷ lệ khách hàng quay lại | % KH hiện tại đã từng mua trước đây |
| `hhi_revenue_concentration` | Mức độ tập trung doanh thu (HHI) | Σ(shareᵢ²) theo category |

**KPI đa chiều (dimension):**
| KPI | Dimension | Mục đích |
|---|---|---|
| `revenue_by_territory` | territory | Doanh thu theo khu vực |
| `revenue_by_category` | category | Doanh thu theo danh mục |
| `margin_by_category` | category | Biên lãi theo danh mục |
| `revenue_by_customer_type` | customer_type | Doanh thu theo loại KH |
| `inventory_turnover_by_category` | category | Vòng quay tồn kho theo danh mục |
| `repeat_rate_by_customer_type` | customer_type | Tỷ lệ quay lại theo loại KH |

Ba KPI mới (`inventory_turnover`, `repeat_customer_rate`, `hhi_revenue_concentration`) được thêm vào nhằm lấp 3 khoảng trống tường thuật:
1. **Rủi ro chiến lược**: HHI đo mức độ phụ thuộc vào một vài danh mục — nếu Bikes chiếm >70% doanh thu, một biến động ở category này có thể gây sụp đổ.
2. **Hiệu quả vận hành**: Inventory Turnover cho biết vốn có đang bị chôn trong kho hay không — kết nối trực tiếp với phát hiện bất thường từ anomaly detection.
3. **Lòng trung thành khách hàng**: Repeat Rate cho biết bao nhiêu % khách hàng quay lại mua — bổ sung cho phân tích cụm và migration.

#### b) Contribution Analysis (`contribution.py`)

Khi một KPI thay đổi giữa 2 kỳ, module này phân rã sự thay đổi đó theo từng dimension để xác định "ai là thủ phạm chính".

Công thức: ΔKPI = Σ(weightᵢ × Δrateᵢ) + mix effect

Ví dụ: Margin giảm 5%. Sau khi phân rã:
- Clothing đóng góp -1.2% (tỷ trọng 15%)
- Bikes đóng góp -0.3% (tỷ trọng 70%)
- Accessories đóng góp +0.1% (tỷ trọng 15%)

=> Clothing là thủ phạm chính mặc dù tỷ trọng nhỏ, vì biên lãi giảm sâu.

#### c) Drill-down Diagnosis (`drill_down.py`)

Cho phép đi sâu từ cấp tổng thể xuống cấp chi tiết để truy tìm nguyên nhân gốc rễ:

```
Overall (Doanh thu giảm 5%)
  → Category (Clothing giảm 8%, đóng góp -1.2%)
    → Subcategory (Jerseys giảm 15%, đóng góp -0.8%)
      → Product (Sport Vest margin 35% → 18%, do discount 5% → 25%)
```

Mỗi cấp đều đánh dấu "is_driver" (đóng góp > ngưỡng 5%) để tập trung vào yếu tố chính.

#### d) Insight Generator (`insight_generator.py`)

Tự động sinh text insight có cấu trúc từ các phân tích trên. Gồm các hàm:

| Hàm | Dùng cho | Severity logic |
|---|---|---|
| `generate_revenue_insight()` | revenue, gross_profit, ... | pct_change > 20% → critical |
| `generate_cluster_migration_insight()` | Customer migration | churn > 10% → critical |
| `generate_anomaly_insight()` | Inventory anomaly | DIO > 180 → critical |
| `generate_hhi_insight()` | HHI concentration | HHI > 0.25 → critical |
| `generate_inventory_turnover_insight()` | Inventory turnover | turnover < 2 → critical |
| `generate_retention_insight()` | Repeat rate | retention < 30% → critical |

Ví dụ insight cho HHI:

```
[CRITICAL] Mức độ tập trung doanh thu (HHI): 0.543
  • Đánh giá: cao (HHI > 0.25) — doanh thu phụ thuộc quá nhiều vào một danh mục
  • Kỳ trước: 0.521 | Biến động: +0.022
  • Gợi ý: Cần đa dạng hóa danh mục sản phẩm để giảm rủi ro tập trung.
    Nếu danh mục chính gặp biến động, tổng doanh thu sẽ giảm mạnh.
```

Ví dụ insight cho Inventory Turnover:

```
[WARNING] Vòng quay hàng tồn kho suy giảm: 2.85 lần/kỳ
  • Kỳ trước: 3.42 | Thay đổi: -16.7%
  • Danh mục luân chuyển chậm nhất:
    - Clothing: 1.23 lần
    - Accessories: 2.01 lần
  • Gợi ý: Vòng quay tồn kho ở mức trung bình. Rà soát từng category để tối ưu.
```

#### e) Causal Inference (`causal.py`)

Áp dụng 2 phương pháp phân tích nhân quả:

**Difference-in-Differences (DiD)**: So sánh nhóm được intervention vs nhóm control. Ví dụ: Discount trên Clothing có thực sự làm tăng doanh thu không? So sánh với nhóm Accessories (không discount). Nếu p < 0.05 thì có bằng chứng thống kê.

**Price Elasticity of Demand (PED)**: Dùng log-log regression để tính độ co giãn của cầu theo giá. PED = -2.93 nghĩa là giá tăng 1% thì demand giảm 2.93%.

#### f) Statistical Tests (`hypothesis_tester.py`)

Cung cấp các kiểm định thống kê:

| Test | Mục đích |
|---|---|
| t-test (2 mẫu) | So sánh KPI giữa 2 nhóm/2 kỳ |
| Chi-square test | Kiểm tra phân phối cụm khách hàng có thay đổi không |
| Mann-Kendall test | Kiểm tra xem KPI có xu hướng tăng/giảm theo thời gian không |
| Cohen's d | Độ lớn ảnh hưởng (effect size) |

#### g) Snapshot Manager (`snapshot_manager.py`)

Phối hợp toàn bộ quá trình snapshot:
- Đọc watermark để biết kỳ cuối cùng đã tính
- Xác định các kỳ còn thiếu
- Gọi KPI Engine để tính toán (bao gồm cả 10 KPI cơ bản và 6 KPI đa chiều)
- UPSERT vào mart.kpi_snapshot
- Cập nhật watermark

#### h) Analytics Runner (`runner.py`) — Kết nối mọi thứ

Đây là module quan trọng nhất: **một lệnh duy nhất chạy TOÀN BỘ pipeline phân tích và sinh báo cáo.**

Pipeline của runner:
```
KPI Snapshot → Contribution Analysis → Drill-down
→ Causal Inference (PED) → Insight Generator
→ Decision Support → Báo cáo Markdown tổng hợp
```

Cách chạy:
```bash
make analytics-runner period=2014Q2
# => reports/analytics_report_2014Q2.md
```

Báo cáo đầu ra gồm 10 phần:
1. **Tổng quan KPI** — Bảng so sánh tất cả 10 KPI giữa 2 kỳ
2. **Phát hiện chính** — Các insight critical/warning
3. **Rủi ro chiến lược (HHI)** — Mức độ tập trung doanh thu + phân bố theo danh mục
4. **Hiệu quả vận hành (Inventory Turnover)** — Vòng quay tồn kho tổng thể + theo từng category
5. **Khách hàng (Retention)** — Tỷ lệ quay lại + phân rã theo loại KH
6. **Phân tích đóng góp** — Ai là thủ phạm chính? (theo category, territory, customer_type)
7. **Chuỗi nguyên nhân (Drill-down)** — Truy vết từ tổng thể xuống sản phẩm
8. **Suy luận nhân quả (PED)** — Độ co giãn theo giá cho từng danh mục
9. **Cảnh báo tồn kho** — Sản phẩm có DIO bất thường
10. **Đề xuất hành động** — Tổng hợp từ insight engine + decision support

### Các file đã tạo

Tất cả trong `src/analytics/`:
- `__init__.py`
- `kpi_calculator.py` (10 KPI tổng thể + 6 KPI đa chiều)
- `snapshot_manager.py`
- `contribution.py`
- `drill_down.py`
- `insight_generator.py` (6 hàm insight: revenue, cluster, anomaly, HHI, turnover, retention)
- `causal.py`
- `hypothesis_tester.py`
- `runner.py` (Orchestrator — kết nối tất cả, xuất báo cáo Markdown)

---

## 3. Nâng cấp Machine Learning

### Vấn đề ban đầu

- RFM clustering chỉ tính 1 lần, không có tracking qua các kỳ
- Không biết khách hàng di chuyển giữa các cụm như thế nào
- Không có hệ thống cảnh báo sớm
- Decision support chỉ là rule-based đơn giản

### Giải pháp

#### a) Customer Migration Tracking (`src/ml/migration.py`)

Cho mỗi quý từ 2013 đến 2014:
1. Tính RFM cho quý đó
2. Chạy K-Means clustering
3. Lưu phân phối cụm vào `mart.rfm_snapshot`
4. So sánh với quý trước → xây dựng migration matrix
5. Lưu vào `mart.customer_migration`

Migration matrix ví dụ:
```
                Quý này
          Champions  Loyal  At-Risk
Quý trước Champions   80%    12%     8%
          Loyal       15%    70%    15%
          At-Risk      5%     8%    87%
```

Nghĩa là 15% khách hàng Loyal đã chuyển xuống At-Risk — cần cảnh báo.

#### b) Early Warning System (`src/ml/early_warning.py`)

Phát hiện sớm các nguy cơ trước khi KPI chính bị ảnh hưởng:

**Churn risk detection**: Dựa trên leading indicators:
- Tần suất mua giảm >50% so với kỳ trước
- Giá trị mua giảm >50%
- Thời gian không mua >90 ngày

**Inventory risk detection**: Sản phẩm có số ngày tồn kho cao bất thường.

Xếp hạng risk: LOW / MEDIUM / HIGH.

### Các file đã tạo/sửa

- `src/ml/migration.py` (mới)
- `src/ml/early_warning.py` (mới)
- `src/ml/decision_support.py` (sửa lại để tích hợp thêm insight từ migration + KPI trend)

---

## 4. Nâng cấp ETL Pipeline

### Thay đổi trong pipeline

Pipeline từ 6 bước lên 7 bước. Bước 7 là Analytics Snapshot:

```
[1] EXTRACT → [2] TRANSFORM → [3] PRE-LOAD VALIDATION
→ [4] LOAD DIMS → [5] LOAD FACTS → [6] POST-LOAD VALIDATION
→ [7] ANALYTICS SNAPSHOT (mới)
```

### CLI flags mới

Thêm vào `src/etl/etl.py`:

| Flag | Chức năng |
|---|---|
| `--snapshot` | Chỉ chạy KPI snapshot, không chạy ETL |
| `--analytics kpi` | Tính KPI |
| `--analytics contribution` | Phân tích đóng góp |
| `--analytics drilldown` | Drill-down diagnosis |
| `--analytics causal` | Causal inference |
| `--analytics all` | Chạy toàn bộ |
| `--period 2014Q2` | Chọn kỳ phân tích |

### Các file đã sửa

- `src/etl/pipeline.py`: Thêm bước 7 (snapshot)
- `src/etl/etl.py`: Thêm CLI flags

---

## 5. Makefile và README (Docker-first)

### Thay đổi

Chuyển toàn bộ sang Docker-first, không còn phụ thuộc vào virtualenv local:

| Trước đây (venv) | Bây giờ (Docker) |
|---|---|
| `make validate` chạy python local | `docker compose run --rm etl python ...` |
| `make etl` cần `.venv/bin/python` | `docker compose exec etl python ...` |
| `make test-conn` cần venv | Docker |
| `make notebook` cần venv | Docker |

Thêm `period ?= 2014Q2` để Makefile tự động dùng period có data khi người dùng không cung cấp.

### Các file đã sửa

- `Makefile`: Toàn bộ target chuyển sang Docker
- `README.md`: Cập nhật hướng dẫn Docker-first, ví dụ dùng period có data
- `requirements.txt`: Thêm `statsmodels`, `scipy`

---

## 6. Số lượng thay đổi tổng cộng

### File mới (12 file)
1. `src/analytics/__init__.py`
2. `src/analytics/kpi_calculator.py` (10 KPI tổng thể + 6 KPI đa chiều)
3. `src/analytics/snapshot_manager.py`
4. `src/analytics/contribution.py`
5. `src/analytics/drill_down.py`
6. `src/analytics/insight_generator.py` (6 hàm insight)
7. `src/analytics/causal.py`
8. `src/analytics/hypothesis_tester.py`
9. `src/analytics/runner.py` (Orchestrator + báo cáo Markdown)
10. `src/ml/migration.py`
11. `src/ml/early_warning.py`
12. `reports/improvements_summary.md` (file này)

### File đã sửa (12 file)
1. `sql/ddl_script.sql` — Thêm mart schema + 5 bảng
2. `scripts/init_dw_tables.py` — Thêm DDL cho mart
3. `src/etl/pipeline.py` — Thêm bước snapshot
4. `src/etl/etl.py` — Thêm CLI flags
5. `src/ml/decision_support.py` — Tích hợp insight engine
6. `config.json` — Thêm snapshot watermark
7. `Makefile` — Docker-first, thêm targets, period default, thêm `analytics-runner`
8. `README.md` — Cập nhật hướng dẫn
9. `requirements.txt` — Thêm statsmodels, scipy
10. `src/analytics/kpi_calculator.py` — Mở rộng từ 7→10 KPI tổng thể, 4→6 KPI đa chiều
11. `src/analytics/insight_generator.py` — Thêm 3 hàm insight cho HHI, Inventory Turnover, Repeat Rate
12. `reports/improvements_summary.md` — Cập nhật toàn bộ nội dung + dấu tiếng Việt

---

## 7. Hướng dẫn chạy lại từ đầu

```bash
# 1. Build và khởi động
cp .env.example .env
make build
make up

# 2. Khởi tạo database
make init-db
make restore-db
make test-conn

# 3. ETL
make etl-full

# 4. Machine Learning
make ml

# 5. Snapshots (bao gồm 10 KPI tổng thể + 6 KPI đa chiều)
make snapshot

# 6. Analytics (dùng period có data: 2014, 2013)
make analytics-causal
make analytics-contribution period=2014Q2
make analytics-drilldown period=2014Q2

# 7. Migration & Insights
make ml-migration
make ml-decision

# 8. Metabase tại http://localhost:3000
```
