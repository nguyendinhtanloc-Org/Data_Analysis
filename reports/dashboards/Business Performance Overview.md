# BI Dashboard Documentation — Business Performance Overview

## 1. Mục tiêu Dashboard

Dashboard **Business Performance Overview** cung cấp cái nhìn tổng quan về hiệu quả kinh doanh sử dụng KPI snapshot theo quý, phân tích đóng góp và root-cause.

Luồng đọc: **KPI → Trend → Contribution → Table**

## 2. Nguồn dữ liệu

- **mart.kpi_snapshot** (snapshot theo quý) — KPI tổng thể & dimension
- **mart.period_comparison** — Contribution percentage, period-over-period

## 3. Cards trong Dashboard (11 cards)

### Row 0 — Text heading
- Mô tả mục tiêu + nguồn data + kỳ

### Row 1 — 4 Scalar (size_x=6)
| Card | Source | Period |
|---|---|---|
| C1 · Revenue ($M) | mart.kpi_snapshot | 2014Q2 |
| C2 · Gross Profit ($M) | mart.kpi_snapshot | 2014Q2 |
| C3 · Gross Margin (%) | mart.kpi_snapshot | 2014Q2 |
| C4 · Orders | mart.kpi_snapshot | 2014Q2 |

### Row 2 — Combo chart (full-width)
- **C5 · Revenue & Gross Profit Trend** — revenue = bar, gross_profit = line
- Source: mart.kpi_snapshot, filter `2011Q2 → 2014Q2`

### Row 3 — 2 halves
- **C6 · Gross Margin % Trend** (line, #7C3AED)
- **C7 · Revenue by Category — 2014Q2** (bar, color per category)

### Row 4 — Root-cause (horizontal bar — yêu cầu #3)
- **C8 · Revenue Change Contribution by Category** (#DC2626 âm, #16A34A dương)
- **C9 · Revenue Change Contribution by Territory** (top 10)

### Row 5 — Table full-width
- **C10 · KPI Comparison — 2014Q2 vs 2014Q1** (7 KPIs)

## 4. Kết quả mẫu

| Driver | Contribution | Change |
|---|---|---|
| Bikes | -97.0% | -50.1% |
| Individual | -100.0% | -43.9% |
| Southwest | -20.1% | -44.4% |

## 5. Metabase Dashboard ID

- **ID**: 20
- **Số cards**: 11
- **Layout**: 6 rows (heading + 4 scalar → combo full → line+bar → 2 horizontal bar → table full)
- **Loại biểu đồ**: scalar, combo (bar+line), line, bar, horizontal bar (row), table
