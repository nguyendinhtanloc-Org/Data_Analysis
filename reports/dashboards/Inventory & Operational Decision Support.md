# BI Dashboard Documentation — Inventory & Operational Decision Support

## 1. Mục tiêu Dashboard

Dashboard **Inventory & Operational Decision Support** giám sát tồn kho rủi ro (zero-sales / slow-moving), giá trị tồn kho, khuyến nghị vận hành.

**Wording bắt buộc:** "Inventory Risk / Zero-Sales Warning" — KHÔNG dùng "anomaly" (anomaly_flag = 0).

## 2. Nguồn dữ liệu

- **dw.ml_inventory_anomaly** — Isolation Forest output (risk flags, DIO, inventory_value)
- **dw.decision_support** — Khuyến nghị hành động (HIGH/MEDIUM priority)
- **dw.fact_inventory + dw.dim_product** — Inventory snapshot

## 3. Cards trong Dashboard (13 cards)

### Row 0 — Text heading
### Row 1 — 4 Scalar
| Card | Source | Color |
|---|---|---|
| C1 · Inventory Risk Products | dw.ml_inventory_anomaly | #F59E0B |
| C2 · Zero-Sales Warnings | dw.ml_inventory_anomaly | #F59E0B |
| C3 · High-Priority Actions | dw.decision_support | #DC2626 |
| C4 · Total Inventory Value | dw.ml_inventory_anomaly | Neutral |

### Row 2 — Table full-width
- **C5 · Zero-Sales & Slow-Moving Products** (50 products, sorted by DIO desc)
- Columns: Product, Category, Inv Value, Units Sold, DIO, Risk label

### Row 3 — Risk by Category + Inventory Value
- **C6 · Inventory Risk Count by Category** (bar, #F59E0B/#DC2626)
- **C7 · Inventory Value by Category** (horizontal bar, category colors)

### Row 4 — Risk Map + Snapshot
- **C8 · DIO vs Inventory Value — Risk Map** (scatter/bubble: X=Inv Value, Y=DIO, size=Avg Qty, màu=Zero/Has-Sales)
- **C9 · Top 20 by Inventory Value** (table)

### Row 5 — Decision Support (3 cards, size_x=8)
- **C10 · Actions by Priority** (bar, priority colors: HIGH=#DC2626, MEDIUM=#F59E0B, LOW=#94A3B8)
- **C11 · High-Priority Actions** (table)
- **C12 · Operational Decision Support — Inventory/Product** (table)

## 4. ML Model Details

**Inventory Risk Detection (Isolation Forest)**:
- Features: avg_quantity, inventory_value, units_sold
- Contamination: 0.06
- anomaly_flag: 0 (không có anomaly thực sự)
- zero_sales_flag: 209 products

| Flag Type | Count | Avg DIO |
|---|---|---|
| Zero-Sales Warning | 209 | 999.0 |
| Has-Sales Warning | 6 | 20.6 |

**Decision Support**: 18,852 insights (8,339 HIGH + 10,513 MEDIUM)

## 5. Metabase Dashboard ID

- **ID**: 22
- **Số cards**: 13
- **Layout**: 6 rows (heading → 4 scalar → table full → bar+row → bubble+table → 3 cards)
- **Loại biểu đồ**: scalar, table, bar, horizontal bar (row), scatter/bubble
- **Lưu ý**: Treemap không được Metabase v0.50.1 hỗ trợ — fallback horizontal bar
