# Luồng Code của Machine Learning Engineer

## Giới thiệu

Người ML Engineer chịu trách nhiệm xây dựng các mô hình ML: phân khúc khách hàng RFM (K-Means), phát hiện bất thường tồn kho (Isolation Forest), theo dõi di cư khách hàng qua các kỳ, và tổng hợp các khuyến nghị tự động.

## Các file liên quan

| File | Mục đích |
|------|----------|
| `src/ml/clustering.py` | Phân khúc khách hàng bằng K-Means trên RFM |
| `src/ml/anomaly.py` | Phát hiện bất thường tồn kho bằng Isolation Forest |
| `src/ml/migration.py` | Theo dõi di chuyển khách hàng giữa các phân khúc qua các kỳ |
| `src/ml/decision_support.py` | Engine tổng hợp: gộp ML + analytics thành khuyến nghị |
| `src/ml/early_warning.py` | Phát hiện sớm nguy cơ: churn khách hàng + tồn kho |
| `models/rfm_scaler.json` | Tham số StandardScaler được save bởi clustering.py |
| `models/rfm_centroids.npy` | Toạ độ tâm cụm được save bởi clustering.py |

## Cách chạy

```bash
# Từng module
python src/ml/clustering.py
python src/ml/anomaly.py
python src/ml/migration.py
python src/ml/decision_support.py
python src/ml/early_warning.py

# Toàn bộ ML pipeline (đúng thứ tự)
make ml-clustering   # Bước 1
make ml-anomaly      # Bước 2
make ml-migration    # Bước 3
make ml-decision     # Bước 4
# hoặc
make ml              # Chạy cả 4 bước trên
```

## Luồng thực thi chi tiết

### 1. Clustering (src/ml/clustering.py)

`run_customer_clustering()`:

1. Đọc dữ liệu RFM từ DWH:
   - Query `dw.fact_sales` tính: recency_days (số ngày từ lần mua cuối), frequency (số lần mua), monetary (tổng chi tiêu)
   - Dữ liệu theo từng customer_key từ trước đến nay (all-time)

2. Tiền xử lý:
   - Loại bỏ IQR outliers ở cột monetary (Q1 - 1.5*IQR, Q3 + 1.5*IQR)
   - Feature vector: [recency_days * -1, frequency, monetary]
   - Chuẩn hóa bằng StandardScaler

3. Chọn số cụm K tối ưu:
   - `choose_best_k(x, min_k=2, max_k=7)`
   - Tính silhouette score cho từng K
   - Chọn K có silhouette cao nhất. Mặc định K=3 (Champions, Loyal, Potential Loyalists)

4. Gán nhãn cho cụm:
   - Sắp xếp cụm theo RFM score (điểm tổng hợp từ recency, frequency, monetary)
   - Gán nhãn từ cao nhất đến thấp nhất: "Champions", "Loyal Customers", "Potential Loyalists", "New Customers", "At-Risk", "Low Value"
   - Nếu K=3, chỉ lấy 3 nhãn đầu tiên

5. Lưu artifacts:
   - `models/rfm_scaler.json`: mean, scale, var của StandardScaler
   - `models/rfm_centroids.npy`: toạ độ tâm cụm

6. Ghi vào DWH:
   - `TRUNCATE + INSERT INTO dw.ml_customer_segments`: từng customer_key + cluster
   - `TRUNCATE + INSERT INTO dw.ml_customer_clustering_metrics`: K, silhouette_score, inertia

### 2. Anomaly Detection (src/ml/anomaly.py)

`run_inventory_anomaly_detection()`:

1. Đọc dữ liệu từ DWH:
   - Inventory agg: AVG(quantity), STDDEV(quantity), SUM(quantity * standard_cost) cho từng product
   - Sales agg: SUM(COGS), SUM(order_qty), COUNT(DISTINCT date_key) cho từng product
   - Chỉ lấy product có is_current = true

2. Tính DIO (Days Inventory Outstanding):
   - `DIO = (inventory_value * active_sales_days) / total_cogs`
   - Nếu total_cogs <= 0 hoặc active_sales_days <= 0: DIO = 999 (unsold)
   - Giá trị DIO được clip trong [0, 999]

3. Xử lý unsold products:
   - Sản phẩm không có giao dịch bán: luôn được đánh dấu là bất thường (anomaly)
   - Severity score: 85/100 (nguy cơ tồn kho chết)

4. Isolation Forest cho sold products (cần tối thiểu 10 mẫu):
   - Features: [avg_quantity, std_quantity, max_quantity, inventory_value, units_sold, days_inventory_outstanding]
   - RobustScaler: chuẩn hóa bằng median + IQR (bền với outliers)
   - IsolationForest: n_estimators=100, max_features=0.7, contamination=0.06
   - `contamination=0.06` được chọn dựa trên domain knowledge: 5-8% sản phẩm có bất thường thực sự

5. Tính severity index:
   - anomaly_score = decision_function() -> chuẩn hóa về [0, 1]
   - severity = anomaly_score * 100 (0-100)
   - anomaly_flag = (pred == -1)

6. Ghi vào DWH:
   - `TRUNCATE + INSERT INTO dw.ml_inventory_anomaly`

### 3. Customer Migration (src/ml/migration.py)

`run_full_migration_pipeline(start_year=2013, end_year=auto)`:

1. Xác định danh sách các quý cần tính:
   - Đọc `mart.kpi_snapshot` để lấy min/max year
   - Tạo danh sách quarter từ start_year đến end_year

2. Với mỗi quarter:
   - `get_rfm_by_period()`: Tính RFM cho từng customer trong khoảng thời gian

3. `compute_clusters_for_period()`:
   - Load `models/rfm_scaler.json` và `models/rfm_centroids.npy` (được tạo bởi clustering.py)
   - Chuẩn hóa RFM features bằng StandardScaler đã lưu
   - Gán customer vào cụm gần nhất (nearest centroid assignment, không fit lại model)
   - Gán nhãn cluster bằng `assign_cluster_labels()` từ clustering.py
   - Giám sát concept drift: tính khoảng cách trung bình từ dữ liệu mới đến tâm cụm cũ

4. Lưu vào `mart.rfm_snapshot`:
   - Cluster distribution cho từng kỳ: customer_count, avg_recency, avg_frequency, avg_monetary, pct_of_total

5. `build_migration_matrix()`:
   - Outer join customer_key giữa kỳ trước và kỳ hiện tại
   - Phát hiện: churned (có ở kỳ trước, không ở kỳ này), new (chỉ ở kỳ này), migrated (cluster thay đổi)

6. Lưu vào `mart.customer_migration`:
   - prev_cluster, curr_cluster, is_churned, is_new, monetary change

### 4. Decision Support (src/ml/decision_support.py)

`run_decision_support(engine)`:

Đây là insight engine tổng hợp từ tất cả các module:

1. Customer priority:
   - Đọc `dw.ml_customer_segments`
   - Rule-based:
     - "At-Risk" + monetary > $10,000: HIGH priority
     - "Champions": MEDIUM (giữ chân)
     - "Low Value": MEDIUM (upsell)
     - Còn lại: LOW

2. Inventory priority:
   - Đọc `dw.ml_inventory_anomaly` (anomaly_flag = true)
   - Rule-based:
     - DIO >= 180 + inventory_value > $10,000: HIGH (nguy cơ hàng chết)
     - DIO >= 90: MEDIUM
     - Còn lại: LOW

3. KPI insights:
   - Đọc `mart.kpi_snapshot`
   - Phát hiện QoQ change > 10% -> tạo signal

4. Migration insights:
   - Đọc `mart.customer_migration`
   - Phát hiện khách churn và downgrade -> tạo signal

5. Ghi vào `dw.decision_support`:
   - entity_type: "customer", "product", "kpi"
   - signal_type: "churn_risk", "inventory_risk", "margin_drop", ...
   - priority: HIGH / MEDIUM / LOW
   - recommended_action: văn bản đề xuất
   - reason: cơ sở đưa ra khuyến nghị

### 5. Early Warning (src/ml/early_warning.py)

`run_early_warning(engine)` (độc lập, không phụ thuộc các module khác):

1. Detect churn risk:
   - So sánh 3 tháng hiện tại vs 3 tháng trước đó cho từng customer
   - Chỉ tính customer có monetary >= $500 trong kỳ trước
   - Chỉ số churn_risk_score = 0.3 * (recency > 90) + 0.35 * (freq_drop > 50%) + 0.35 * (monetary_drop > 50%)
   - Phân loại: LOW (< 0.3), MEDIUM (0.3 - 0.6), HIGH (> 0.6)

2. Detect inventory risk:
   - `months_of_stock = avg_stock / avg_monthly_sold` (tính từ 90 ngày gần nhất)
   - risk_score = 1 - 1 / (1 + months_of_stock)
   - Phân loại: LOW, MEDIUM, HIGH

## Thứ tự phụ thuộc giữa các module

```
clustering.py
  |
  +--> models/rfm_scaler.json, models/rfm_centroids.npy
  |      |
  |      +--> migration.py (đọc scaler và centroid đã fix)
  |             |
  |             +--> mart.rfm_snapshot, mart.customer_migration
  |
anomaly.py (độc lập)
  |
  +--> dw.ml_inventory_anomaly

early_warning.py (độc lập)

decision_support.py
  |
  +--> đọc clustering output (dw.ml_customer_segments)
  +--> đọc anomaly output (dw.ml_inventory_anomaly)
  +--> đọc migration output (mart.customer_migration)
  +--> đọc snapshot output (mart.kpi_snapshot)
  |
  +--> dw.decision_support
```

Lưu ý: `migration.py` require `clustering.py` đã chạy trước đó vì cần file centroid và scaler. `decision_support.py` cần tất cả các module còn lại đã chạy.
