# BI Dashboard Documentation — Business Performance Overview

## 1. Mục tiêu Dashboard

Dashboard **Business Performance Overview** cung cấp cái nhìn tổng quan về hiệu quả kinh doanh sử dụng KPI snapshot theo kỳ (quarter), hỗ trợ so sánh period-over-period và phân tích đóng góp.

Câu hỏi chính:
- Doanh thu, lợi nhuận, biên lợi nhuận kỳ này so với kỳ trước thế nào?
- Động lực tăng/giảm đến từ danh mục, khu vực, loại khách hàng nào?
- Xu hướng doanh thu, biên lợi nhuận, vòng quay tồn kho theo quý?
- Mức độ tập trung doanh thu (HHI) có đáng lo ngại không?
- Tỷ lệ khách hàng quay lại và di chuyển cluster giữa các kỳ?

## 2. Nguồn dữ liệu

- **mart.kpi_snapshot**: KPI tổng thể và theo dimension, lưu theo từng quý
- **mart.period_comparison**: So sánh period-over-period kèm contribution percentage
- **mart.customer_migration**: Tracking khách hàng chuyển cluster giữa các kỳ
- **mart.rfm_snapshot**: Phân phối RFM cluster theo từng kỳ

**Period filter**: Tất cả cards được lọc theo period_key (2014Q1, 2014Q2, ...) — có thể thêm filter dashboard-level.

## 3. Cards trong Dashboard

### 3.1 KPI Summary
- **Loại**: Table
- **Mô tả**: So sánh 7 KPIs chính giữa kỳ hiện tại và kỳ trước, kèm biến động tuyệt đối và %
- **Source**: `mart.kpi_snapshot WHERE dimension = 'overall'`

### 3.2 Revenue Trend by Quarter
- **Loại**: Line chart
- **Mô tả**: Xu hướng doanh thu qua tất cả các quý có dữ liệu
- **Source**: `mart.kpi_snapshot WHERE kpi_name = 'revenue'`

### 3.3 Revenue by Category
- **Loại**: Pie chart
- **Mô tả**: Phân bố doanh thu theo danh mục sản phẩm kỳ hiện tại
- **Source**: `mart.kpi_snapshot WHERE kpi_name = 'revenue_by_category'`

### 3.4 Revenue Contribution by Territory
- **Loại**: Bar chart
- **Mô tả**: Đóng góp của từng khu vực vào biến động doanh thu, top 10
- **Source**: `mart.period_comparison WHERE dimension = 'territory'`

### 3.5 Gross Margin % Trend
- **Loại**: Line chart
- **Mô tả**: Xu hướng biên lợi nhuận gộp qua các quý
- **Source**: `mart.kpi_snapshot WHERE kpi_name = 'gross_margin_pct'`

### 3.6 Customer & Order Summary
- **Loại**: Table / Number
- **Mô tả**: Số khách hàng, đơn hàng, tỷ lệ quay lại, HHI kỳ hiện tại
- **Source**: `mart.kpi_snapshot WHERE kpi_name IN ('total_customers', 'order_count', 'repeat_customer_rate', 'hhi_revenue_concentration')`

### 3.7 Customer Migration Stats
- **Loại**: Table
- **Mô tả**: Số khách hàng churn, mới, tracked giữa các kỳ
- **Source**: `mart.customer_migration`

## 4. Kết quả mẫu (2014Q2 vs 2014Q1)

| KPI | Q2 2014 | Q1 2014 | Thay đổi | % |
|-----|---------|---------|----------|---|
| Doanh thu | $7.21M | $12.85M | -$5.63M | -43.9% |
| Lợi nhuận gộp | $1.57M | $1.88M | -$309K | -16.5% |
| Biên LN gộp | 21.7% | 14.6% | +7.1pp | +48.7% |
| Đơn hàng | 5,465 | 6,296 | -831 | -13.2% |
| Khách hàng | 5,111 | 5,901 | -790 | -13.4% |
| Giá trị ĐH TB | $1,320 | $2,040 | -$720 | -35.3% |

**Phân tích đóng góp**: Bikes đóng góp -87.5% vào giảm doanh thu, Components -9.1%.

## 5. Period Filter

Dashboard hỗ trợ lọc theo period_key (cột period trong mart.kpi_snapshot). Có thể thêm filter level dashboard để chuyển đổi giữa các quý.
