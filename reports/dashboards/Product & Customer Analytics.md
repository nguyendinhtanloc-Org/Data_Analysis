# BI Dashboard Documentation — Product & Customer Analytics

## 1. Mục tiêu Dashboard

Dashboard **Product & Customer Analytics** phân tích khách hàng qua RFM segments (K-Means K=3, silhouette≈0.48), hiệu suất sản phẩm (ABC classification), hành vi KH.

Luồng đọc: **KPI → RFM Segments → ABC/Top Products → Top Customers → Segment Trend → Heatmap → Margin/Price**

## 2. Nguồn dữ liệu

- **dw.ml_customer_segments** — K-Means clustering output (RFM)
- **mart.rfm_snapshot** — RFM cluster distribution theo quý
- **dw.fact_sales + dw.dim_product/dim_customer/dim_date/dim_territory** — Dữ liệu gốc product & customer analytics

## 3. Cards trong Dashboard (15 cards)

### Row 0 — Text heading
### Row 1 — 4 Scalar (2014Q2)
| Card | Source |
|---|---|
| C1 · Active Customers | dw.fact_sales |
| C2 · Active Products | dw.fact_sales |
| C3 · Units Sold | dw.fact_sales |
| C4 · Revenue per Customer | dw.fact_sales |

### Row 2 — RFM Segments
- **C5 · Customer Segments — RFM K-Means (K=3)** (bar, segment colors)
- **C6 · RFM Segment Details** (table)

### Row 3 — Product Performance
- **C7 · Revenue Share by ABC Product Class — 2014Q2** (bar, ABC colors)
- **C8 · Top 10 Products by Revenue — 2014Q2** (horizontal bar)

### Row 4 — Full-width table
- **C9 · Top 10 Customers — 2014Q2** (with Type, Country, Orders, Revenue)

### Row 5 — Segment Trend + Territory Donut
- **C10 · Customer Segment Share by Quarter** (line, 2013Q1→2014Q2)
- **C11 · Revenue by Territory — 2014Q2** (donut — thay pie customer_type vì 100% Individual)

### Row 6 — Heatmap full-width
- **C12 · Revenue Heatmap — Customer Type × Category** (pivot table)

### Row 7 — Margin + Price
- **C13 · Gross Margin % by Category — 2014Q2** (bar)
- **C14 · Cost vs Selling Price by Product** (scatter)

## 4. ML Model Details

**RFM Clustering (K-Means)**:
- Features: recency_days (đảo dấu), frequency, monetary
- Scale: StandardScaler
- Chọn K: `choose_best_k` bằng silhouette score (k=2..7)
- Số cluster tối ưu: **3** (silhouette ≈ 0.48)
- Phân bố: Loyal Customers (14,078), Champions (4,149), Potential Loyalists (442)

## 5. Metabase Dashboard ID

- **ID**: 21
- **Số cards**: 15
- **Layout**: 8 rows (heading → 4 scalar → 2 charts → 2 charts → table full → line+donut → pivot full → bar+scatter)
- **Loại biểu đồ**: scalar, bar, horizontal bar (row), table, line, donut (pie), pivot table, scatter
