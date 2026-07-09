# BI Dashboard Documentation — Product & Customer Analytics

## 1. Mục tiêu Dashboard

Dashboard **Product & Customer Analytics** phân tích khách hàng qua RFM segments (ML clustering), hiệu suất sản phẩm, và các khuyến nghị từ decision support engine.

Câu hỏi chính:
- Khách hàng được phân nhóm thế nào theo RFM? Mỗi nhóm đóng góp bao nhiêu?
- Sản phẩm/danh mục nào bán chạy nhất?
- Doanh thu phân bố thế nào theo loại khách hàng?
- Hệ thống gợi ý hành động gì cho từng nhóm khách hàng?
- Phân phối RFM cluster thay đổi thế nào qua các kỳ?

## 2. Nguồn dữ liệu

- **dw.ml_customer_segments**: K-Means clustering output (RFM) với nhãn cluster
- **dw.fact_sales + dw.dim_product/dim_customer/dim_date**: Dữ liệu gốc cho product analytics
- **dw.decision_support**: Khuyến nghị từ insight engine (entity_type = 'customer')
- **mart.rfm_snapshot**: RFM cluster distribution theo từng kỳ

## 3. Cards trong Dashboard

### 3.1 Customer Segments Distribution
- **Loại**: Bar chart
- **Mô tả**: Số lượng khách hàng trong mỗi segment, kèm revenue
- **Source**: `dw.ml_customer_segments GROUP BY cluster_label`
- **ML Model**: K-Means với k=4 trên RFM features (recency, frequency, monetary)

### 3.2 Customer Segment Details
- **Loại**: Table
- **Mô tả**: Chi tiết từng segment: số lượng, recency trung bình, frequency, monetary
- **Source**: `dw.ml_customer_segments`

### 3.3 Product Revenue by Category
- **Loại**: Bar chart
- **Mô tả**: Doanh thu theo danh mục sản phẩm kỳ hiện tại
- **Source**: `dw.fact_sales + dw.dim_product`

### 3.4 Top 10 Products
- **Loại**: Bar chart
- **Mô tả**: Top 10 sản phẩm theo doanh thu kỳ hiện tại
- **Source**: `dw.fact_sales + dw.dim_product`

### 3.5 Revenue by Customer Type
- **Loại**: Pie chart
- **Mô tả**: Tỷ trọng doanh thu Store vs Individual
- **Source**: `dw.fact_sales + dw.dim_customer`

### 3.6 Customer Decision Support
- **Loại**: Table
- **Mô tả**: Khuyến nghị từ ML insight engine cho entity_type = 'customer'
- **Source**: `dw.decision_support WHERE entity_type = 'customer'`
- **Tín hiệu**: Migration insights (Champions churn, Loyal churn, v.v.)

### 3.7 RFM Cluster Share by Period
- **Loại**: Table
- **Mô tả**: Tỷ lệ % từng cluster theo từng kỳ (2013Q1 → 2014Q2)
- **Source**: `mart.rfm_snapshot`

## 4. ML Model Details

**RFM Clustering (K-Means)**:
- Features: recency_days (đảo dấu), frequency, monetary
- Scale: StandardScaler
- Số cluster: 4 (k=4, chọn heuristic)
- Silhouette score: ~0.46 (tương quan vừa phải)
- Output: dw.ml_customer_segments

**Customer Migration**:
- YoY comparison (cùng quý năm trước)
- Output: mart.customer_migration + mart.rfm_snapshot
- Tín hiệu: Churned (ngừng mua), New (mới), Downgraded (giảm cluster)
