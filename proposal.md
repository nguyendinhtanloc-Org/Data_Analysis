# HỆ THỐNG KHO DỮ LIỆU TÍCH HỢP HỌC MÁY CHO PHÂN TÍCH HIỆU QUẢ KINH DOANH

*Data Warehouse with Integrated Machine Learning for Business Performance Analytics*

| Hạng mục | Thông tin |
| --- | --- |
| Dữ liệu nguồn | AdventureWorks 2019 (Microsoft SQL Server sample — mô phỏng doanh nghiệp bán lẻ xe đạp tại Bắc Mỹ) |
| Tech Stack | PostgreSQL 15, Python 3.11, scikit-learn, Docker Compose, Metabase v0.50+ |
| Nhóm / Thời gian | 4 thành viên, 2 tuần |
| Chi phí hạ tầng | 0 VND — toàn bộ open-source |

## PHẦN I — BỐI CẢNH & BÀI TOÁN

### 1.1 Vấn đề xuất phát

Doanh nghiệp bán lẻ thường tích lũy lượng lớn dữ liệu giao dịch nhưng thiếu hạ tầng để chuyển dữ liệu đó thành thông tin hỗ trợ quyết định. Ba vấn đề phổ biến trong thực tế là: (1) dữ liệu phân tán ở nhiều nguồn dẫn đến con số không nhất quán giữa các phòng ban, (2) báo cáo doanh thu chỉ phản ánh kết quả bề mặt mà bỏ qua lợi nhuận thực và chi phí ẩn, (3) tồn kho bất thường và hành vi khách hàng xấu đi chỉ được phát hiện khi đã quá muộn để can thiệp hiệu quả.

Dự án này xây dựng một hệ thống end-to-end giải quyết cả ba vấn đề: từ kho dữ liệu tập trung, phân tích chỉ số theo chuỗi thời gian, ứng dụng học máy để phân cụm và phát hiện bất thường, đến lớp hỗ trợ quyết định hiển thị gợi ý hành động cụ thể dựa trên kết quả phân tích và ML.

### 1.2 Đối tượng sử dụng và bài toán quyết định

Hệ thống phục vụ ba nhóm người dùng cụ thể. Mỗi nhóm không chỉ cần nhìn thấy số liệu mà cần được hỗ trợ ra quyết định cụ thể tiếp theo.

**Sales Manager** cần biết mỗi tuần: doanh thu và lợi nhuận gộp đang đi theo hướng nào, sản phẩm nào đang tạo ra phần lớn doanh thu, khu vực nào tăng trưởng hay sụt giảm. Khi doanh thu giảm hơn 10% so với cùng kỳ, hệ thống tự động drill-down chỉ ra danh mục và khu vực đang kéo chỉ số xuống — giảm thời gian truy tìm nguyên nhân thủ công.

**Warehouse Manager** cần biết: sản phẩm nào đang tồn kho bất thường so với lịch sử, vốn đang bị chôn ở đâu. Khi mô hình Isolation Forest flagged một sản phẩm, hệ thống hiển thị kèm giá trị tồn kho và số ngày tồn để Warehouse Manager ra quyết định thanh lý hay điều chỉnh reorder policy mà không cần tính tay.

**Marketing Manager** cần biết: khách hàng nào thuộc nhóm có giá trị cao đang có dấu hiệu rời bỏ, nhóm nào chỉ mua một lần và có thể kích hoạt lại. Kết quả phân cụm K-Means được hiển thị kèm profile RFM và gợi ý hướng tiếp cận cho từng nhóm — không phải chỉ cluster label.

### 1.3 Câu hỏi phân tích

| Mã | Nội dung | Phương pháp |
| --- | --- | --- |
| Q1 | Doanh thu và lợi nhuận gộp thay đổi thế nào theo quý (QoQ + YoY)? | OLAP, Window Function |
| Q2 | 20% sản phẩm nào tạo ra 80% doanh thu? | Phân tích Pareto ABC |
| Q3 | Danh mục nào có biên lợi nhuận thực sự cao sau khi trừ chi phí? | Gross Margin% by category |
| Q4 | Khu vực địa lý nào đang tăng trưởng hay sụt giảm? | ROLLUP + YoY by territory |
| Q5 | Sản phẩm nào đang tồn kho bất thường? | Isolation Forest |
| Q6 | Khách hàng phân thành những nhóm hành vi nào? | K-Means trên RFM |
| Q7 | Chiết khấu đang ảnh hưởng thực sự như thế nào đến biên lợi nhuận? | Discount vs Margin analysis |
| Q8–Q10 | Hiệu quả vận hành tài chính: DSO, DPO, Cash Conversion Cycle | Financial KPI trend |

### 1.4 Giả thuyết kỳ vọng trước khi phân tích

Phân tích tốt bắt đầu từ giả thuyết có cơ sở, không phải từ việc chạy tất cả query rồi mới tìm cách giải thích. Các giả thuyết dưới đây được gọi là "kỳ vọng" vì chúng dựa trên đặc thù ngành bán lẻ xe đạp nói chung — AdventureWorks là dataset mô phỏng và kết quả thực tế có thể khác. Kết quả bác bỏ giả thuyết không phải thất bại mà là phát hiện có giá trị về đặc thù của dataset này so với giả định ngành.

| Mã | Giả thuyết kỳ vọng | Cơ sở lý luận |
| --- | --- | --- |
| H1 | Doanh thu tập trung Q2–Q3, Q1 và Q4 thấp hơn đáng kể | Xe đạp là sản phẩm mùa xuân/hè tại Bắc Mỹ — nhu cầu giảm khi trời lạnh (NPD Group, 2019) |
| H2 | 20% SKU tạo ra hơn 80% tổng doanh thu | Quy luật Pareto phổ biến trong bán lẻ (Juran, 1954; Koch, 1998) |
| H3 | Danh mục Bikes có Gross Margin% cao nhất | Xe đạp hoàn chỉnh có list price cao hơn nhiều so với standard_cost; phụ kiện cạnh tranh giá gay gắt hơn |
| H4 | North America chiếm hơn 50% doanh thu; Pacific và Europe có YoY growth cao hơn | AdventureWorks có thị trường lịch sử tại Mỹ; thị trường mới thường tăng trưởng nhanh hơn từ nền thấp |
| H5 | Components có tỷ lệ tồn kho bất thường cao nhất | Phụ tùng thường mua theo lô lớn với lead time dài, nhu cầu thực khó dự báo chính xác |
| H6 | K-Means RFM tách được ít nhất 3 nhóm khách hàng có hành vi khác biệt rõ ràng | RFM là framework phân cụm khách hàng chuẩn trong bán lẻ (Hughes, 1994); Silhouette Score kỳ vọng > 0.35 |
| H7 | Danh mục có discount trung bình cao không bù đắp được margin bị mất | Price elasticity thấp trong bán lẻ chuyên dụng — volume tăng không đủ bù margin giảm |
| H8 | Cash Conversion Cycle nằm trong khoảng 45–75 ngày và cải thiện theo thời gian | Benchmark ngành bán lẻ thể thao (Sageworks Industry Report, 2015) |

## PHẦN II — GIẢI PHÁP KỸ THUẬT

### 2.1 Kiến trúc tổng thể

Hệ thống gồm 5 tầng liên kết theo luồng dữ liệu một chiều:

```
OLTP (AdventureWorks)
        |
        v
ETL Pipeline (Python)
        |
        v
Data Warehouse (PostgreSQL — Star Schema)
        |
        v
ML Layer (scikit-learn — K-Means + Isolation Forest)
        |
        v
Decision Support Layer (Business Rules trên kết quả ML + Dashboard Metabase)
```

Tầng ML đọc dữ liệu từ DWH, ghi kết quả (cluster label, anomaly flag) trở lại DWH dưới dạng bảng riêng. Decision Support Layer đọc các bảng này, áp dụng business rules để sinh gợi ý hành động, rồi hiển thị trên Dashboard. Thiết kế này giữ logic ML tách biệt hoàn toàn với logic hiển thị — có thể thay đổi mô hình mà không cần sửa Dashboard.

### 2.2 Quyết định kỹ thuật và lý do chọn

Phần này trình bày mỗi lựa chọn kỹ thuật quan trọng kèm lý do cụ thể, các phương án đã cân nhắc, và trade-off được thừa nhận. Cách tiếp cận theo tinh thần Architecture Decision Record (Nygard, 2011).

**Quyết định 1 — Mô hình kho dữ liệu: Star Schema**

Context: Cần chọn mô hình tổ chức dữ liệu cho kho — Star Schema, Snowflake Schema, hoặc Data Vault.

Quyết định: Star Schema với 2 bảng Fact và 5 bảng Dimension.

Lý do: Query OLAP trên Star Schema chỉ cần JOIN tối thiểu giữa Fact và các Dimension trực tiếp, phù hợp với Metabase — công cụ tạo query bằng giao diện đồ họa, không hỗ trợ tốt cho nhiều tầng JOIN lồng nhau. Snowflake Schema chuẩn hóa hơn nhưng thêm độ phức tạp JOIN không cần thiết với dataset quy mô này. Data Vault phù hợp cho hệ thống có nhiều nguồn dữ liệu thay đổi liên tục — không phù hợp với scope đồ án.

Trade-off chấp nhận: Star Schema dẫn đến dư thừa dữ liệu ở bảng Dimension so với Snowflake. Với quy mô AdventureWorks, chi phí lưu trữ này không đáng kể.

**Quyết định 2 — ETL Framework: Python thuần với SQLAlchemy**

Context: Cần chọn framework để extract, transform và load dữ liệu từ OLTP sang DWH.

Các phương án cân nhắc: dbt, Apache Airflow, Apache Spark, Python thuần.

Quyết định: Python + Pandas + SQLAlchemy.

Lý do: dbt chuyên về transform trong SQL và phù hợp hơn khi team quen SQL thuần — nhưng tích hợp kém với bước ML Python phía sau vì dbt không quản lý Python script. Airflow phù hợp cho orchestration pipeline phức tạp có dependency graph và retry tự động, nhưng overhead cấu hình không tương xứng với pipeline 2 tuần chạy thủ công. Spark overkill hoàn toàn với dataset dưới 1 triệu bản ghi. Python thuần cho phép kiểm soát toàn bộ logic, tích hợp tự nhiên với scikit-learn ở bước ML, và dễ debug hơn.

Trade-off chấp nhận: Pipeline Python thuần thiếu dependency graph, retry logic tự động, và data lineage tracking — nhược điểm nghiêm trọng trong môi trường production thực tế. Dự án ghi nhận điều này và xác định Apache Airflow là hướng nâng cấp tự nhiên nếu mở rộng scope.

**Quyết định 3 — Dashboard: Metabase**

Context: Cần chọn công cụ BI để hiển thị kết quả phân tích và ML.

Các phương án cân nhắc: Power BI, Tableau, Apache Superset, Looker Studio, Metabase.

Quyết định: Metabase v0.50+.

Lý do: Power BI và Tableau yêu cầu license thương mại. Looker Studio không hỗ trợ kết nối trực tiếp PostgreSQL on-premise không có public IP. Apache Superset mạnh hơn về visualization nhưng cấu hình phức tạp hơn đáng kể và không phù hợp với 2 tuần. Metabase kết nối trực tiếp PostgreSQL, hỗ trợ SQL tùy chỉnh, drill-down, và alert rule mà không cần cấu hình thêm.

Trade-off chấp nhận: Metabase giới hạn về calculated field phức tạp và custom visualization so với Power BI. Với 10 câu hỏi phân tích đã định nghĩa trước, giới hạn này không ảnh hưởng đến output trong scope đồ án.

**Quyết định 4 — Anomaly detection: Isolation Forest thay vì Z-score hoặc IQR**

Context: Cần phát hiện sản phẩm có tồn kho bất thường. Các phương án từ đơn giản đến phức tạp: IQR, Z-score, EWMA, Seasonal Decomposition, Isolation Forest.

Lý do không dùng Z-score hay IQR: Cả hai giả định dữ liệu phân phối đối xứng. Trong thực tế, số lượng tồn kho thường có phân phối lệch phải mạnh do seasonal spike và bulk purchasing — vi phạm giả định này làm Z-score báo nhiều false positive với hàng mua theo lô lớn định kỳ.

Lý do không dùng EWMA hay Seasonal Decomposition: Cả hai yêu cầu chuỗi thời gian liên tục theo từng sản phẩm. Fact_Inventory trong AdventureWorks là snapshot không đều — không đủ điều kiện cho time-series decomposition đáng tin cậy.

Lý do chọn Isolation Forest: Không giả định phân phối, hoạt động tốt với dữ liệu nhiều chiều (quantity, inventory value, days outstanding), và Liu et al. (2008) đã chứng minh hiệu quả trên dữ liệu tabular có outlier không đối xứng.

Trade-off chấp nhận: Isolation Forest kém interpretable hơn Z-score — khó giải thích tại sao một sản phẩm cụ thể bị flagged. Xử lý bằng cách hiển thị thêm các feature value thực tế bên cạnh anomaly flag để người dùng tự đánh giá.

**Quyết định 5 — Phân cụm khách hàng: K-Means trên RFM thay vì DBSCAN hay GMM**

Context: Cần phân cụm khách hàng dựa trên hành vi mua hàng. Các phương án: K-Means, DBSCAN, GMM, Agglomerative Clustering.

Lý do không dùng DBSCAN: Không cho phép chỉ định số cluster, và với dữ liệu RFM sau chuẩn hóa thường có mật độ khá đồng đều — DBSCAN hay gộp nhiều nhóm thành một hoặc tạo quá nhiều noise point.

Lý do không dùng GMM: Kém ổn định hơn khi số chiều nhỏ (3 chiều RFM) và cần giả định về số component tương tự K-Means nhưng khó giải thích kết quả hơn cho người dùng kinh doanh.

Lý do chọn K-Means: Phù hợp với dữ liệu số liên tục sau chuẩn hóa, centroid có ý nghĩa trực tiếp dễ giải thích cho Marketing Manager, và cho phép chạy nhiều lần với K khác nhau để chọn K tối ưu bằng Elbow Method + Silhouette Score. Hughes (1994) và nhiều nghiên cứu thực nghiệm sau đó xác nhận K-Means trên RFM là phương pháp hiệu quả trong bán lẻ.

Trade-off chấp nhận: K-Means nhạy cảm với outlier và giả định cluster có hình cầu xấp xỉ bằng nhau. Xử lý bằng cách loại outlier cực đoan (monetary > Q3 + 3×IQR) trước khi fit.

### 2.3 Star Schema

**Hai bảng Fact:**

| Bảng | Granularity | Measures chính |
| --- | --- | --- |
| Fact_Sales | 1 dòng sản phẩm trong 1 đơn hàng | order_qty, unit_price, unit_price_discount, line_total, standard_cost, gross_profit |
| Fact_Inventory | 1 sản phẩm tại 1 địa điểm vào 1 ngày (snapshot) | quantity, ordered_qty, scrapped_qty |

**Năm bảng Dimension:**

| Bảng | SCD | Cột chính |
| --- | --- | --- |
| Dim_Date | N/A | date_key, date, day, month, quarter, year, is_weekend |
| Dim_Product | Type 2 | product_key, name, subcategory, category, list_price, standard_cost, valid_from, valid_to, is_current |
| Dim_Customer | Type 1 | customer_key, full_name, customer_type, country, state_province, territory_id |
| Dim_Territory | Type 1 | territory_key, territory_name, country_region, group_name |
| Dim_Employee | Type 1 | employee_key, full_name, job_title, department, hire_date |

Dim_Product dùng SCD Type 2 vì list_price và standard_cost thay đổi theo thời gian — phân tích margin cần biết giá tại thời điểm bán, không phải giá hiện tại. Các Dimension còn lại dùng Type 1 vì lịch sử thay đổi của chúng không có giá trị phân tích trong scope này.

### 2.4 ETL Pipeline

**Extract:** Full load lần đầu từ 5 schema OLTP. Incremental load sau đó chỉ kéo bản ghi có ModifiedDate > watermark lần chạy trước, lưu vào config.json. Giới hạn đã biết: ModifiedDate không bắt được hard delete.

**Data Quality Rules:**

| Cột | Rule | Hành động | Ghi chú |
| --- | --- | --- | --- |
| FK columns | IS NULL | DROP + ghi error_log | FK null là orphan record — không load vào Fact |
| unit_price, standard_cost | < 0 hoặc NULL | DROP + ghi error_log | Giá âm không hợp lệ về nghiệp vụ |
| order_qty | <= 0 hoặc NULL | DROP + ghi error_log | Số lượng phải dương |
| full_name | IS NULL | Fill 'Unknown' | Tên null không block record |
| Duplicate natural key | Trùng primary key nguồn | Giữ bản ModifiedDate mới nhất | Áp dụng cho Dimension |

**Transform & Load:** Surrogate key integer tự tăng thay thế natural key. gross_profit tính tại bước Transform (gross_profit = line_total − standard_cost × order_qty) để đảm bảo nhất quán — không tính lại trong SQL phân tích. Mỗi lần ETL bọc trong một DB transaction; lỗi giữa chừng dẫn đến ROLLBACK toàn bộ.

**Validation 3 lớp:**

| Lớp | Nội dung kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Pre-load | Row count sau Extract, schema không thay đổi, bảng không rỗng | Không có bảng trả về 0 bản ghi bất ngờ |
| Post-load | Orphan record, row count staging vs DWH, null ở cột FK | 0 orphan, 0 null FK, row count khớp 100% |
| Cross-check | SUM(line_total) DWH vs OLTP, COUNT(order_id) theo năm | Khớp 100% với nguồn OLTP |

## PHẦN III — PHÂN TÍCH SQL & KIỂM CHỨNG GIẢ THUYẾT

Mỗi câu hỏi phân tích được trình bày theo cấu trúc nhất quán: bài toán kinh doanh — phương pháp — SQL — kết quả kỳ vọng — insight hành động.

### Q1 — Doanh thu & Lợi nhuận gộp theo quý

Kiểm chứng H1. YoY growth quan trọng hơn QoQ trong quyết định chiến lược vì loại bỏ nhiễu mùa vụ. QoQ âm vào Q4 có thể là tự nhiên với ngành xe đạp — không nên đọc nhầm thành tín hiệu tiêu cực nếu YoY vẫn dương.

```sql
WITH quarterly AS (
    SELECT
        d.year, d.quarter,
        SUM(f.line_total)   AS revenue,
        SUM(f.gross_profit) AS gross_profit
    FROM dw.Fact_Sales f
    JOIN dw.Dim_Date d USING (date_key)
    GROUP BY d.year, d.quarter
)
SELECT
    year, quarter, revenue, gross_profit,
    ROUND(gross_profit / NULLIF(revenue, 0) * 100, 2) AS margin_pct,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY year, quarter))
        / NULLIF(LAG(revenue) OVER (ORDER BY year, quarter), 0) * 100, 2
    ) AS qoq_growth_pct,
    ROUND(
        (revenue - LAG(revenue, 4) OVER (ORDER BY year, quarter))
        / NULLIF(LAG(revenue, 4) OVER (ORDER BY year, quarter), 0) * 100, 2
    ) AS yoy_growth_pct
FROM quarterly
ORDER BY year, quarter;
```

Kết quả kỳ vọng: Q2+Q3 chiếm hơn 55% doanh thu năm. YoY âm liên tiếp 2 quý là tín hiệu cần điều tra bất kể QoQ có dương hay không.

### Q2 — Phân tích ABC Pareto

Kiểm chứng H2. Phân loại sản phẩm thành 3 nhóm để định hướng tồn kho và marketing.

```sql
WITH ranked AS (
    SELECT
        p.product_name, p.category,
        SUM(f.line_total) AS revenue,
        SUM(SUM(f.line_total)) OVER () AS total_revenue,
        SUM(SUM(f.line_total)) OVER (
            ORDER BY SUM(f.line_total) DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative
    FROM dw.Fact_Sales f
    JOIN dw.Dim_Product p USING (product_key)
    WHERE p.is_current = true
    GROUP BY p.product_name, p.category
)
SELECT
    product_name, category, revenue,
    ROUND(revenue / total_revenue * 100, 2)   AS revenue_share_pct,
    ROUND(cumulative / total_revenue * 100, 2) AS cumulative_pct,
    CASE
        WHEN cumulative / total_revenue <= 0.80 THEN 'A'
        WHEN cumulative / total_revenue <= 0.95 THEN 'B'
        ELSE 'C'
    END AS abc_class
FROM ranked
ORDER BY revenue DESC;
```

### Q7 — Tác động chiết khấu lên biên lợi nhuận

Kiểm chứng H7. revenue_lost_to_discount là con số bị ẩn hoàn toàn trong báo cáo doanh thu thông thường — hiển thị con số này trên Dashboard tạo nhận thức rõ hơn về chi phí thực của chính sách giá.

```sql
SELECT
    p.category,
    COUNT(DISTINCT f.order_id)                          AS order_count,
    ROUND(AVG(f.unit_price_discount) * 100, 2)          AS avg_discount_pct,
    SUM(f.line_total)                                    AS net_revenue,
    SUM(f.unit_price * f.order_qty)                      AS gross_revenue_no_discount,
    SUM(f.unit_price * f.order_qty) - SUM(f.line_total)  AS revenue_lost_to_discount,
    ROUND(SUM(f.gross_profit) / NULLIF(SUM(f.line_total), 0) * 100, 2) AS actual_margin_pct
FROM dw.Fact_Sales f
JOIN dw.Dim_Product p USING (product_key)
WHERE p.is_current = true
GROUP BY p.category
ORDER BY avg_discount_pct DESC;
```

### Q8–Q10 — Cash Conversion Cycle

CCC = DIO + DSO − DPO. CCC âm nghĩa doanh nghiệp thu tiền trước khi phải trả — mô hình vận hành lý tưởng. DSO và DPO trong dự án này tính xấp xỉ từ SalesOrderHeader và PurchaseOrderDetail vì AdventureWorks không có bảng AR/AP chính thức — điều này được ghi rõ trong báo cáo như một giới hạn đã biết.

## PHẦN IV — MACHINE LEARNING

### 4.1 Vị trí của ML trong hệ thống

ML không thay thế SQL analytics mà bổ sung cho phần SQL không làm được: tìm cấu trúc ẩn trong dữ liệu mà ngưỡng cứng không nắm bắt được. Cụ thể, SQL với ngưỡng cố định không phân biệt được khách hàng có hành vi tương tự nhau trong cùng một nhóm doanh thu, và không phát hiện được tồn kho bất thường khi phân phối dữ liệu lệch mạnh.

Hai module ML trong dự án:

- Module 1 — Phân cụm khách hàng: K-Means trên RFM (Q6)
- Module 2 — Phát hiện tồn kho bất thường: Isolation Forest (Q5)

Kết quả của hai module được ghi vào DWH và đọc bởi Decision Support Layer ở Phần V.

### 4.2 Module 1 — Phân cụm khách hàng K-Means trên RFM

**Bước 1 — Tính đặc trưng RFM từ DWH:**

```sql
WITH rfm_raw AS (
    SELECT
        c.customer_key,
        c.full_name,
        MAX(d.date)                AS last_purchase_date,
        COUNT(DISTINCT f.order_id) AS frequency,
        SUM(f.line_total)          AS monetary
    FROM dw.Fact_Sales f
    JOIN dw.Dim_Customer c USING (customer_key)
    JOIN dw.Dim_Date d USING (date_key)
    GROUP BY c.customer_key, c.full_name
)
SELECT
    customer_key, full_name,
    CURRENT_DATE - last_purchase_date AS recency_days,
    frequency, monetary
FROM rfm_raw;
```

**Bước 2 — Tiền xử lý và chuẩn hóa:**

```python
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import pandas as pd

df = pd.read_sql(rfm_query, engine)

# Loại outlier cực đoan trước khi fit
Q1 = df['monetary'].quantile(0.25)
Q3 = df['monetary'].quantile(0.75)
df = df[df['monetary'] <= Q3 + 3 * (Q3 - Q1)]

# Recency đảo chiều: recency_days thấp = mua gần đây = tốt hơn
features = df[['recency_days', 'frequency', 'monetary']].copy()
features['recency_days'] = features['recency_days'] * -1

scaler = StandardScaler()
X = scaler.fit_transform(features)
```

**Bước 3 — Chọn K tối ưu:**

```python
inertia, sil_scores = [], []
for k in range(2, 8):
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X)
    inertia.append(km.inertia_)
    sil_scores.append(silhouette_score(X, labels))
# Chọn K tại điểm gãy Elbow kết hợp Silhouette Score cao nhất
```

**Bước 4 — Fit và ghi kết quả về DWH:**

```python
km_final = KMeans(n_clusters=K_optimal, random_state=42, n_init=10)
df['cluster'] = km_final.fit_predict(X)

# Profile centroid để gán nhãn kinh doanh sau khi có kết quả thực
cluster_profile = df.groupby('cluster')[
    ['recency_days', 'frequency', 'monetary']
].mean()
print(cluster_profile)

df[['customer_key', 'cluster', 'recency_days',
    'frequency', 'monetary']].to_sql(
    'ml_customer_segments', engine,
    schema='dw', if_exists='replace', index=False
)
```

Lưu ý: nhãn kinh doanh cho từng cluster (ví dụ Champions, At-Risk) sẽ được gán sau khi xem profile centroid thực tế — không gán cứng trước khi có kết quả chạy.

Kết quả kỳ vọng: K tối ưu trong khoảng 3–5, Silhouette Score > 0.35, các cluster có profile RFM phân biệt rõ ràng.

### 4.3 Module 2 — Phát hiện tồn kho bất thường với Isolation Forest

**Bước 1 — Tính đặc trưng từ DWH:**

```sql
SELECT
    p.product_key, p.product_name, p.category,
    AVG(i.quantity)                   AS avg_quantity,
    STDDEV(i.quantity)                AS std_quantity,
    MAX(i.quantity)                   AS max_quantity,
    SUM(i.quantity * p.standard_cost) AS inventory_value,
    365.0 / NULLIF(
        SUM(f.line_total - f.gross_profit)
        / NULLIF(AVG(i.quantity * p.standard_cost), 0)
    , 0)                               AS days_inventory_outstanding
FROM dw.Fact_Inventory i
JOIN dw.Dim_Product p USING (product_key)
LEFT JOIN dw.Fact_Sales f USING (product_key)
WHERE p.is_current = true
GROUP BY p.product_key, p.product_name, p.category
HAVING COUNT(*) >= 10;
```

**Bước 2 — Fit Isolation Forest và ghi kết quả:**

```python
from sklearn.ensemble import IsolationForest

features_inv = df_inv[[
    'avg_quantity', 'std_quantity',
    'inventory_value', 'days_inventory_outstanding'
]].fillna(0)

iso = IsolationForest(
    contamination=0.1,
    random_state=42,
    n_estimators=100
)
df_inv['anomaly_flag'] = iso.fit_predict(features_inv) == -1

df_inv[['product_key', 'anomaly_flag',
        'days_inventory_outstanding',
        'inventory_value']].to_sql(
    'ml_inventory_anomaly', engine,
    schema='dw', if_exists='replace', index=False
)
```

Tham số contamination=0.1 là giả định ban đầu và sẽ được điều chỉnh sau khi review thủ công 20–30 sản phẩm để kiểm tra độ chính xác thực tế.

### 4.4 Đánh giá mô hình

| Mô hình | Metric | Ngưỡng chấp nhận |
| --- | --- | --- |
| K-Means | Silhouette Score, Elbow inertia, cluster profile interpretability | Silhouette > 0.35; các cluster có profile kinh doanh phân biệt rõ |
| Isolation Forest | Precision@K trên ground truth thủ công (review 20–30 sản phẩm) | Ít nhất 70% sản phẩm flagged thực sự có tồn kho bất thường khi kiểm tra thủ công |

## PHẦN V — DECISION SUPPORT LAYER & DASHBOARD

### 5.1 Decision Support Layer

Decision Support Layer là lớp kết nối giữa kết quả ML và quyết định kinh doanh. Bản chất của lớp này là một business rule engine — nó đọc kết quả từ hai bảng ML (ml_customer_segments và ml_inventory_anomaly), áp dụng các rule kinh doanh được định nghĩa rõ ràng, và sinh ra gợi ý hành động cụ thể ghi vào bảng dw.decision_support.

Lớp này không phải ML — không có training, không có loss function, không có feedback loop. Mục đích của nó là dịch cluster label và anomaly flag thành ngôn ngữ hành động mà người dùng kinh doanh hiểu được mà không cần tự phân tích từ số liệu thô.

```python
decisions = []

# Rule cho customer segment — áp dụng sau khi có profile cluster thực tế
for _, row in df_customers.iterrows():
    cluster_label = row['cluster_label']  # Gán sau khi có kết quả chạy thật

    if cluster_label == 'At-Risk':
        # Khách hàng từng chi nhiều nhưng đã lâu không mua
        action = 'Ưu tiên chăm sóc lại — recency cao, monetary lịch sử lớn'
        priority = 'HIGH'
    elif cluster_label == 'Champions':
        action = 'Duy trì engagement — nhóm tạo giá trị cao nhất'
        priority = 'MEDIUM'
    elif cluster_label == 'New Customers':
        action = 'Tăng tần suất tương tác — kích hoạt lần mua thứ 2'
        priority = 'MEDIUM'
    else:
        action = 'Theo dõi định kỳ'
        priority = 'LOW'

    decisions.append({
        'entity_type': 'customer',
        'entity_key': row['customer_key'],
        'cluster_label': cluster_label,
        'action': action,
        'priority': priority
    })

# Rule cho inventory anomaly
for _, row in df_inv[df_inv['anomaly_flag']].iterrows():
    dio = row['days_inventory_outstanding']
    inv_value = row['inventory_value']

    if dio > 180:
        action = f'Xem xét thanh lý — DIO {dio:.0f} ngày, vốn chôn {inv_value:,.0f}'
        priority = 'HIGH'
    else:
        action = 'Theo dõi chặt — kiểm tra lại reorder policy'
        priority = 'MEDIUM'

    decisions.append({
        'entity_type': 'product',
        'entity_key': row['product_key'],
        'cluster_label': None,
        'action': action,
        'priority': priority
    })

pd.DataFrame(decisions).to_sql(
    'decision_support', engine,
    schema='dw', if_exists='replace', index=False
)
```

### 5.2 Dashboard — 3 trang trên Metabase

| Trang | Đối tượng | Nội dung hiển thị | Hỗ trợ quyết định |
| --- | --- | --- | --- |
| Trang 1: Tổng quan KPI | Sales Manager | 4 KPI thẻ: Tổng doanh thu, Lợi nhuận gộp, Số đơn hàng, AOV. Biểu đồ doanh thu theo tháng + đường cùng kỳ năm trước. Gross Margin% theo quý. Alert highlight khi YoY < -10% | Khi alert kích hoạt, drill-down tự động lọc theo danh mục và khu vực để chỉ ra nguyên nhân |
| Trang 2: Khách hàng & Sản phẩm | Marketing Manager | Biểu đồ Pareto ABC. Bảng K-Means Customer Segments với profile RFM. Bảng decision_support lọc entity_type = customer, sắp xếp theo priority | Marketing Manager thấy trực tiếp danh sách khách hàng cần hành động và gợi ý cụ thể |
| Trang 3: Tồn kho & Vận hành | Warehouse Manager, CFO | Danh sách sản phẩm flagged bởi Isolation Forest kèm DIO và inventory value. Bảng decision_support lọc entity_type = product. KPI thẻ CCC: DIO, DSO, DPO | Warehouse Manager thấy danh sách ưu tiên xử lý kèm lý do cụ thể |

## PHẦN VI — HẠN CHẾ & HƯỚNG PHÁT TRIỂN

| Hạn chế | Mô tả | Hướng khắc phục |
| --- | --- | --- |
| Dữ liệu mẫu tĩnh | AdventureWorks không phản ánh biến động thị trường thực tế | Thay bằng dữ liệu live từ OLTP thực tế của doanh nghiệp |
| ETL chạy thủ công | Pipeline chưa được lên lịch tự động | Tích hợp Apache Airflow để schedule và quản lý dependency |
| Không bắt hard delete | Incremental load dựa trên ModifiedDate không phát hiện bản ghi bị xóa | Triển khai CDC bằng PostgreSQL logical replication hoặc Debezium |
| ML không có retraining pipeline | Mô hình train một lần — drift theo thời gian chưa được xử lý | Tích hợp MLflow để track experiment và schedule retraining định kỳ |
| Decision Support dùng rule cứng | Logic gợi ý hiện tại dựa trên business rule do nhóm định nghĩa, chưa học từ dữ liệu phản hồi | Thay bằng model học có giám sát nếu có dữ liệu phản hồi người dùng trong tương lai |
| Isolation Forest cần calibrate | Tham số contamination=0.1 là giả định ban đầu | Calibrate sau khi review thủ công ground truth |
| DSO/DPO dùng proxy | AdventureWorks không có bảng AR/AP chính thức | Ghi rõ trong báo cáo; dùng bảng AR/AP chính thức trong hệ thống thực |
| Scope DWH giới hạn | Chỉ có Fact_Sales và Fact_Inventory — thiếu Fact_Purchase, Fact_Return | Mở rộng schema nếu phát triển thành đồ án tốt nghiệp |

## PHẦN VII — KẾ HOẠCH THỰC HIỆN

| Thành viên | Vai trò | Nhiệm vụ | Output | Deadline |
| --- | --- | --- | --- | --- |
| A | Data Architect | Conceptual Model, Star Schema, DDL, Docker Compose | schema_diagram.png, ddl_script.sql, docker-compose.yml | Ngày 1–5 |
| B | ETL Engineer | Extract, Transform (SCD, null-handling, surrogate key), Load, Validation | etl_pipeline.py, validation_report.md | Ngày 4–8 |
| C | ML Engineer | RFM + K-Means, Isolation Forest, evaluation, Decision Support Layer | ml_clustering.py, ml_anomaly.py, decision_support.py, ml_evaluation.md | Ngày 7–12 |
| D | Analytics & BI | OLAP queries Q1–Q10, Materialized View, 3 trang Dashboard Metabase | analytics_queries.sql, dashboard hoàn chỉnh, bao_cao.docx | Ngày 9–13 |

Rủi ro timeline cần lưu ý: Decision Support Layer phụ thuộc hoàn toàn vào kết quả của Module 1 và Module 2. Nếu K-Means hoặc Isolation Forest cho kết quả không đủ chất lượng, nhóm cần thời gian điều chỉnh tham số trước khi viết rule. Ngày 14 là buffer dành cho integration test toàn bộ pipeline từ ETL đến Dashboard.

## Tài liệu tham khảo

Hughes, A. M. (1994). *Strategic Database Marketing*. Probus Publishing.

Juran, J. M. (1954). Universals in management planning and controlling. *The Management Review*, 43(11), 748–761.

Koch, R. (1998). *The 80/20 Principle*. Currency/Doubleday.

Liu, F. T., Ting, K. M., & Zhou, Z. H. (2008). Isolation forest. *Proceedings of the 8th IEEE International Conference on Data Mining*, 413–422.

NPD Group. (2019). *U.S. Cycling Industry Report*. The NPD Group, Inc.

Nygard, M. (2011). Documenting Architecture Decisions. https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions

Sageworks. (2015). *Industry Financial Report: Sporting Goods Stores*. Sageworks, Inc.
