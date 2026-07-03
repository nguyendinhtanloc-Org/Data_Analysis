# Luồng Code của Data Analyst (Analytics & KPI)

## Giới thiệu

Người Data Analyst chịu trách nhiệm tính toán KPI, phân tích đóng góp (contribution), drill-down nguyên nhân gốc, tạo insight tự động, kiểm định thống kê, và tổng hợp báo cáo phân tích.

## Các file liên quan

| File | Mục đích |
|------|----------|
| `src/analytics/runner.py` | Điều phối chạy toàn bộ phân tích, tạo file báo cáo Markdown |
| `src/analytics/kpi_calculator.py` | Định nghĩa 10 KPI tổng thể + 8 KPI theo dimension, engine tính toán |
| `src/analytics/snapshot_manager.py` | Quản lý snapshot KPI định kỳ (insert/upsert vào mart.kpi_snapshot) |
| `src/analytics/contribution.py` | Phân tích đóng góp của từng dimension vào biến động KPI |
| `src/analytics/drill_down.py` | Đào sâu đa cấp: tìm nguyên nhân gốc rễ theo hệ thống phân cấp |
| `src/analytics/insight_generator.py` | Sinh văn bản insight tự động từ dữ liệu phân tích |
| `src/analytics/hypothesis_tester.py` | Kiểm định thống kê (t-test, chi-square, Mann-Kendall) |
| `src/analytics/causal.py` | Suy luận nhân quả (price elasticity) |

## Cách chạy

```bash
# Qua ETL entry point
python src/etl/etl.py --analytics kpi --period 2014Q2
python src/etl/etl.py --analytics contribution --period 2014Q2
python src/etl/etl.py --analytics drilldown --period 2014Q2
python src/etl/etl.py --analytics causal
python src/etl/etl.py --analytics all --period 2014Q2

# Chỉ chạy snapshot
python src/etl/etl.py --snapshot

# Báo cáo đầy đủ
python src/analytics/runner.py --period 2014Q2
```

## Luồng thực thi của runner.py

### 1. Khởi tạo AnalyticsRunner

`AnalyticsRunner.__init__()` tạo engine kết nối PostgreSQL, thiết lập logging.

### 2. _resolve_period()

Đọc period_key (ví dụ: 2014Q2), tính:
- curr_start, curr_end: ngày bắt đầu và kết thúc của kỳ hiện tại
- prev_start, prev_end: ngày bắt đầu và kết thúc của kỳ trước (previous quarter)

### 3. _load_kpi_data()

Đọc từ `mart.kpi_snapshot` cho cả kỳ hiện tại và kỳ trước.
Nếu bảng trống, fallback về tính toán trực tiếp từ `dw.fact_sales`.

### 4. _run_contribution()

Phân tích đóng góp cho từng KPI (revenue, gross_margin_pct) theo từng dimension (category, territory, customer_type).

`contribution_breakdown()` trong `contribution.py` thực hiện:

- Lấy doanh thu/gross_margin cho từng giá trị dimension ở cả 2 kỳ
- Tính weight (tỷ trọng của dimension value trong kỳ hiện tại)
- Tính abs_change và pct_change cho từng dimension value
- Tính contribution_pct: mức đóng góp của từng dimension value vào biến động tổng thể
- Phát hiện mix_shift_warning: nếu weight thay đổi > 20%, có thể do thay đổi cơ cấu (mix shift) chứ không phải thay đổi thực sự

Kết quả được lưu vào `mart.period_comparison`.

### 5. _run_drill_down()

`drill_down()` trong `drill_down.py` thực hiện đệ quy theo hệ thống phân cấp:

```
overall
  --> category
    --> subcategory
      --> product
```

Ở mỗi cấp, tính đóng góp của từng phần tử. Nếu phần tử nào là driver (|contribution_pct| >= threshold), tiếp tục đi sâu vào cấp dưới.

### 6. _generate_insights()

`insight_generator.py` nhận kết quả từ contribution và drill-down, sinh văn bản có cấu trúc:

- Phân loại mức độ nghiêm trọng (critical / warning / info) bằng `relative_magnitude = |curr-prev| / mean`
- Xác định trend (up / down / stable)
- Trích dẫn evidence từ dữ liệu
- Đề xuất hành động
- Đánh giá độ tin cậy (confidence 0-1)

Mỗi insight có cấu trúc:
```
[SEVERITY] KPI trend X% (curr_value vs prev_value)
Nguyên nhân chính:
  - Dimension A: contribution_pct%
  - Dimension B: contribution_pct%
Đề xuất: ...
```

### 7. _run_causal()

`price_elasticity()` trong `causal.py` thực hiện hồi quy log-log:
```
ln(Quantity) = alpha + beta * ln(UnitPrice)
```
Cho từng category (Bikes, Clothing, Accessories) và overall.

### 8. _run_hypothesis_tests()

`hypothesis_tester.py` thực hiện 3 loại kiểm định:
- `two_sample_ttest()`: So sánh line_total (hoặc unit_price, order_qty, gross_profit) giữa 2 nhóm (VD: Bikes vs Accessories)
- `trend_significance_test()`: Kiểm định Mann-Kendall cho trend doanh thu theo quý
- `chi_square_cluster_test()`: Kiểm định phân phối cluster giữa 2 kỳ

### 9. _build_report()

Tổng hợp toàn bộ kết quả vào file Markdown với 11 phần:
1. Executive Summary
2. KPI Overview
3. Period Comparison
4. Contribution Analysis
5. Drill-down Diagnosis
6. Statistical Tests
7. Causal Analysis
8. Inventory Anomalies
9. ML Decision Support
10. Segment Migration
11. Recommendations

Xuất ra `reports/analytics_report_{period_key}.md`.

## KPI Definitions chi tiết

### Overall KPIs (10 cái)

| KPI | Công thức SQL |
|-----|--------------|
| revenue | `SUM(f.line_total)` |
| gross_profit | `SUM(f.gross_profit)` |
| gross_margin_pct | `SUM(gross_profit) / SUM(line_total) * 100` (trả 0 nếu không có doanh thu) |
| order_count | `COUNT(DISTINCT sales_order_id)` |
| total_customers | `COUNT(DISTINCT customer_key)` |
| avg_order_value | `SUM(line_total) / COUNT(DISTINCT order_id)` |
| revenue_per_customer | `SUM(line_total) / COUNT(DISTINCT customer_key)` |
| inventory_turnover | COGS / avg inventory value (bằng 0 nếu inventory = 0) |
| repeat_customer_rate | % khách hàng đã mua trong 12 tháng trước / tổng khách hàng kỳ này |
| hhi_revenue_concentration | Herfindahl-Hirschman Index theo category |

### Dimension KPIs (8 cái)

| KPI | Dimension |
|-----|-----------|
| revenue_by_territory | territory |
| revenue_by_category | category |
| margin_by_category | category |
| revenue_by_customer_type | customer_type |
| inventory_turnover_by_category | category |
| revenue_by_product | product |
| repeat_rate_by_customer_type | customer_type |

## Snapshot Manager

`snapshot_manager.run_kpi_snapshot()` được gọi từ pipeline.py sau khi ETL hoàn tất.

Luồng thực hiện:
1. `get_snapshot_watermark()`: Đọc watermark từ `config.json` (có file locking tránh race condition)
2. `get_data_date_range()`: Xác định min/max year từ dữ liệu thực tế trong DWH
3. `get_pending_periods()`: Tạo danh sách các kỳ (quarter) chưa được snapshot
4. Với mỗi kỳ: `calculate_all_kpis()` tính toán 10 + 8 KPI, `_upsert_kpi_snapshot()` lưu vào `mart.kpi_snapshot`
5. `save_snapshot_watermark()`: Cập nhật watermark cho kỳ đã xử lý

## Insight Severity Classification

`_classify_severity()` trong `insight_generator.py` dùng `relative_magnitude` thay vì threshold tuyệt đối:
```
relative_magnitude = |curr - prev| / mean(curr, prev)
```

- relative_magnitude >= 0.3: critical
- relative_magnitude >= 0.15: warning
- còn lại: info

Cách này tránh false alarm trên dữ liệu seasonal (bike retail có biến động theo mùa rất lớn).
