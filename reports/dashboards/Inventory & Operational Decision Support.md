# BI Dashboard Documentation — Inventory & Operational Decision Support

## 1. Mục tiêu Dashboard

Dashboard **Inventory & Operational Decision Support** giám sát hàng tồn kho bất thường (ML anomaly detection), vòng quay tồn kho, và khuyến nghị vận hành từ decision support engine.

Câu hỏi chính:
- Sản phẩm nào có dấu hiệu tồn kho bất thường (quá nhiều, quá ít, hoặc không có doanh số)?
- Vòng quay hàng tồn kho thay đổi thế nào qua các quý?
- Ngành hàng nào có nhiều vấn đề tồn kho nhất?
- Hệ thống khuyến nghị hành động gì cho từng vấn đề?
- Khách hàng di chuyển (churn / mới) giữa các kỳ ra sao?

## 2. Nguồn dữ liệu

- **dw.ml_inventory_anomaly**: Isolation Forest output — phát hiện tồn kho bất thường
- **mart.kpi_snapshot**: Inventory turnover KPI theo quý
- **dw.decision_support**: Khuyến nghị từ insight engine (entity_type = 'inventory')
- **mart.customer_migration**: Thống kê churn/acquire cho operational view

## 3. Cards trong Dashboard

### 3.1 Inventory Anomaly Flags
- **Loại**: Table
- **Mô tả**: Danh sách sản phẩm có anomaly_flag=true hoặc zero_sales_flag=true, sắp xếp theo DIO giảm dần
- **Source**: `dw.ml_inventory_anomaly WHERE anomaly_flag OR zero_sales_flag`
- **ML Model**: Isolation Forest (contamination=0.05) trên inventory metrics

### 3.2 Inventory Turnover Trend
- **Loại**: Line chart
- **Mô tả**: Xu hướng vòng quay hàng tồn kho qua các quý
- **Source**: `mart.kpi_snapshot WHERE kpi_name = 'inventory_turnover'`

### 3.3 Anomaly Count by Category
- **Loại**: Bar chart
- **Mô tả**: Số lượng sản phẩm bất thường theo từng danh mục, kèm DIO trung bình
- **Source**: `dw.ml_inventory_anomaly GROUP BY category`

### 3.4 Operational Decision Support
- **Loại**: Table
- **Mô tả**: Khuyến nghị từ ML insight engine cho entity_type = 'inventory'
- **Source**: `dw.decision_support WHERE entity_type = 'inventory'`
- **Tín hiệu**: Inventory Anomaly (zero-sales, DIO cao)

### 3.5 Inventory Value by Category
- **Loại**: Bar chart
- **Mô tả**: Tổng giá trị tồn kho và DIO trung bình theo danh mục
- **Source**: `dw.ml_inventory_anomaly GROUP BY category`

### 3.6 Customer Migration Summary
- **Loại**: Table
- **Mô tả**: Thống kê churn và acquire khách hàng theo từng cặp kỳ
- **Source**: `mart.customer_migration GROUP BY prev_period_key, curr_period_key`

## 4. ML Model Details

**Inventory Anomaly (Isolation Forest)**:
- Features: avg_quantity, inventory_value, units_sold
- Contamination: 0.05
- Output: anomaly_flag (boolean), anomaly_score
- Zero-sales flag: sản phẩm có units_sold = 0 nhưng tồn kho > 0

**Kết quả mẫu**:
- 209 sản phẩm zero-sales warning (cảnh báo, không đánh dấu anomaly)
- 6 sản phẩm anomaly thực sự
- Decision support ghi nhận 209 inventory insights (MEDIUM priority)

## 5. Operational Metrics

| Metric | Giá trị |
|--------|---------|
| Sản phẩm có tồn kho | 504 |
| Sản phẩm zero-sales | 209 (41.5%) |
| Sản phẩm anomaly | 6 |
| Inventory Turnover Q2 2014 | 0.00 (dữ liệu tồn kho không đủ biến động) |
