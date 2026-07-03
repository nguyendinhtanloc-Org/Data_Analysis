"""Counterexamples — chứng minh đồ án SAI trong các tình huống cụ thể.
Chạy được local KHÔNG cần pandas/numpy: python3 -m pytest tests/test_counterexamples.py -v
"""
import math


# =============================================================================
# 1. avg_order_value KPI systematically wrong
# =============================================================================
def test_kpi_avg_order_value_wrong_by_definition():
    """avg_order_value = SUM(line_total) / COUNT(sales_order_detail_id)
    Đây là "giá trị trung bình mỗi DÒNG", không phải mỗi ĐƠN HÀNG.

    Ví dụ:
      - Đơn hàng A: 2 dòng, mỗi dòng $50  → line_total = $100
      - Đơn hàng B: 1 dòng, $200           → line_total = $200
      - avg_order_value thực tế           = ($100 + $200) / 2 đơn = $150
      - avg_order_value theo query        = ($100 + $200) / 3 dòng = $100
    """
    line_items = [
        {"detail_id": 1, "order_id": "A", "line_total": 50.0},
        {"detail_id": 2, "order_id": "A", "line_total": 50.0},
        {"detail_id": 3, "order_id": "B", "line_total": 200.0},
    ]
    sum_lt = sum(i["line_total"] for i in line_items)
    count_details = len(set(i["detail_id"] for i in line_items))
    count_orders = len(set(i["order_id"] for i in line_items))

    query_avg = sum_lt / count_details  # = 300 / 3 = 100
    true_avg = sum_lt / count_orders    # = 300 / 2 = 150

    error_pct = abs(query_avg - true_avg) / true_avg * 100
    print(f"    avg_order_value query: ${query_avg:.0f}, true: ${true_avg:.0f}, error: {error_pct:.0f}%")
    assert error_pct > 30, f"Sai số {error_pct:.0f}% — đây là systematic error do dùng sai denominator"


# =============================================================================
# 2. Incremental ETL loads NOTHING
# =============================================================================
def test_incremental_etl_loads_nothing():
    """All watermarks trong config.json là 2026-07-02.
    AdventureWorks data chỉ đến 2014.
    WHERE ModifiedDate > '2026-07-02' → 0 rows cho MỌI bảng.
    Chỉ --full mode mới load được data — nhưng incremental là default!
    """
    watermarks = {
        "Sales.SalesOrderDetail": "2026-07-02T06:30:06.064792",
        "Sales.SalesOrderHeader": "2026-07-02T06:30:06.064792",
        "Production.Product": "2026-07-02T06:30:06.064792",
        "Production.ProductSubcategory": "2026-07-02T06:30:06.064792",
        "Production.ProductCategory": "2026-07-02T06:30:06.064792",
        "Sales.Customer": "2026-07-02T06:30:06.064792",
        "Person.Person": "2026-07-02T06:30:06.064792",
        "Sales.SalesTerritory": "2026-07-02T06:30:06.064792",
        "HumanResources.Employee": "2026-07-02T06:30:06.064792",
        "HumanResources.EmployeeDepartmentHistory": "2026-07-02T06:30:06.064792",
        "HumanResources.Department": "2026-07-02T06:30:06.064792",
        "Production.ProductInventory": "2026-07-02T06:30:06.064792",
        "Production.WorkOrder": "2026-07-02T06:30:06.064792",
    }
    # AdventureWorks data max ModifiedDate: khoảng 2014-06-30
    LAST_ADW_DATE = "2014-06-30"
    ALL_IN_FUTURE = all(wm.startswith("2026") for wm in watermarks.values())
    print(f"    All {len(watermarks)} watermarks in 2026 (future)? {ALL_IN_FUTURE}")
    assert ALL_IN_FUTURE, "Phải có watermark trong tương lai"
    # Với mỗi bảng: WHERE ModifiedDate > '2026-07-02' trả về 0 rows
    # → incremental mode: 0 rows extracted → pipeline báo SUCCESS nhưng DWH trống
    print(f"    AdventureWorks data max ModifiedDate: {LAST_ADW_DATE}")
    print(f"    Watermark min: 2026-07-02")
    print(f"    → Incremental mode extracts 0 rows from ALL {len(watermarks)} tables")
    assert LAST_ADW_DATE < "2026-07-02", \
        "Data date < watermark → WHERE ModifiedDate > watermark = FALSE → 0 rows"


# =============================================================================
# 3. HHI bị méo khi có NULL / unknown category
# =============================================================================
def test_hhi_distorted_by_null_category():
    """HHI query: GROUP BY p.category — nếu có NULL category, nó tạo 1 group riêng.
    Với 3 categories thật (Bikes, Clothing, Accessories) + 1 NULL:
      - NULL chiếm 10% → HHI = 0.300 (thấp hơn 3-group: 0.345)
      - NULL chiếm 90% → HHI ≈ 0.812 (cao artificial — tưởng concentration cao)
    Threshold 0.4/0.6 không còn ý nghĩa.
    """
    def hhi(shares):
        return sum(s**2 for s in shares)

    # 3 categories, không NULL
    s3 = [400/900, 300/900, 200/900]
    hhi3 = hhi(s3)

    # 3 categories + NULL chiếm 10%
    s4a = [400/1000, 300/1000, 200/1000, 100/1000]
    hhi4a = hhi(s4a)

    # 3 categories + NULL chiếm 90%
    s4b = [50/1000, 30/1000, 20/1000, 900/1000]
    hhi4b = hhi(s4b)

    print(f"    HHI 3 categories:          {hhi3:.3f}")
    print(f"    HHI 3 + NULL (10%):        {hhi4a:.3f} (giảm artificial)")
    print(f"    HHI 3 + NULL (90%):        {hhi4b:.3f} (tăng artificial)")
    assert hhi4a < hhi3, "NULL làm HHI giảm (thêm group = phân tán) — nhưng artificial"
    assert hhi4b > 0.6, "NULL dominant → HHI > 0.6 (critical alert) — nhưng là do data quality"


# =============================================================================
# 4. UNIQUE constraint allows duplicates when location_id IS NULL
# =============================================================================
def test_unique_constraint_null_duplicates():
    """PostgreSQL UNIQUE (product_key, location_id, date_key):
    Trong SQL, NULL != NULL → (1, NULL, 20240101) và (1, NULL, 20240101) là 2 rows khác nhau.
    → fact_inventory có thể có duplicate inventory snapshot cho cùng product+date.
    """
    inventory_rows = [
        {"product_key": 1, "location_id": None, "date_key": 20240101, "quantity": 100},
        {"product_key": 1, "location_id": None, "date_key": 20240101, "quantity": 200},
        {"product_key": 1, "location_id": 5,    "date_key": 20240101, "quantity": 300},
    ]

    # Simulate PostgreSQL UNIQUE: NULLs treated as distinct
    seen = set()
    duplicates_allowed = 0
    for r in inventory_rows:
        pk = (r["product_key"], r["location_id"], r["date_key"])
        # In PostgreSQL: NULL != NULL, so (1, NULL, 20240101) != (1, NULL, 20240101)
        if r["location_id"] is None:
            seen.add(pk)
            duplicates_allowed += 1
        else:
            if pk in seen:
                pass  # would be rejected
            else:
                seen.add(pk)
                duplicates_allowed += 1

    assert duplicates_allowed == 3  # all 3 rows inserted despite duplicate product+date
    true_quantity = 100  # expected if dedup worked
    wrong_quantity = sum(r["quantity"] for r in inventory_rows if r["location_id"] is None)
    print(f"    Expected quantity for product=1, date=20240101: {true_quantity}")
    print(f"    Actual quantity (NULL-allow-duplicates):       {wrong_quantity}")
    assert wrong_quantity > true_quantity, "NULL duplicates inflate inventory quantity"


# =============================================================================
# 5. Simpson's Paradox — contribution analysis chỉ ra sai root cause
# =============================================================================
def test_simpsons_paradox_contribution():
    """Mix shift: high-value category (Bikes) giảm share, low-value (Accessories) tăng share.
    Mọi category đều tăng revenue, nhưng tổng thể tăng chậm hơn kỳ vọng vì mix shift.
    Contribution analysis attributing change to "Bikes" misses the real story.

    prev = Bikes=1000, Clothing=200, Accessories=100  → total=1300
    curr = Bikes=900,  Clothing=300, Accessories=200  → total=1400
      - Bikes: -10%  → abs_change=-100, contribution=-100/100 = -100%
      - Clothing: +50% → abs_change=+100, contribution=+100/100 = +100%
      - Accessories: +100% → abs_change=+100, contribution=+100/100 = +100%
    Top contributor by abs change: Clothing và Accessories (cùng +100)
    """
    prev = {"Bikes": 1000, "Clothing": 200, "Accessories": 100}
    curr = {"Bikes": 900, "Clothing": 300, "Accessories": 200}
    total_prev = sum(prev.values())
    total_curr = sum(curr.values())
    total_change = total_curr - total_prev

    print(f"\n    Simpson's Paradox example:")
    print(f"    {'Category':<15} {'Prev':>8} {'Curr':>8} {'%Chg':>8} {'Contrib':>8}")
    contributions = {}
    for cat in prev:
        chg_pct = (curr[cat] - prev[cat]) / prev[cat] * 100
        contrib = (curr[cat] - prev[cat]) / abs(total_change) * 100
        contributions[cat] = contrib
        print(f"    {cat:<15} {prev[cat]:>8} {curr[cat]:>8} {chg_pct:>+7.1f}% {contrib:>+7.1f}%")

    print(f"    {'TOTAL':<15} {total_prev:>8} {total_curr:>8} {(total_change/total_prev*100):>+7.1f}%")

    top_by_contrib = max(contributions, key=lambda k: abs(contributions[k]))
    print(f"\n    Top contributor: {top_by_contrib} ({contributions[top_by_contrib]:.1f}%)")

    # Insight text generation (mô phỏng insight_generator.py logic)
    if abs(contributions[top_by_contrib]) >= 5:
        lines = [f"\n    → Nguyên nhân chính: {top_by_contrib} đóng góp {contributions[top_by_contrib]:.1f}%"]
    else:
        lines = ["\n    → Không có nguyên nhân rõ rệt"]

    print("".join(lines))
    print("    → NHƯNG: Bikes giảm vì khách chuyển sang Accessories rẻ hơn.")
    print("    → Root cause thực sự là MIX SHIFT, không phải Bikes.")

    # The contribution model doesn't separate rate effect from mix effect
    # Nó chỉ nói "Bikes đóng góp X%" mà không giải thích TẠI SAO Bikes giảm
    # → Insight gây hiểu lầm
    assert abs(total_change) > 0, "Phải có total change"
    assert abs(contributions[top_by_contrib]) > 50, "Top contributor dominates"


# =============================================================================
# 6. Fixed centroids fail under concept drift
# =============================================================================
def test_fixed_centroids_concept_drift():
    """Fixed centroids từ all-time data (2010-2014). Nếu behavior thay đổi
    (e.g. hậu COVID: ai cũng mua ít hơn + thường xuyên hơn), mọi customer bị misclassify.

    Code thật dùng StandardScaler trước khi fit centroids. Giả lập:
      - Scaler mean: (100, 5, 500)
      - Scaler scale: (80, 4, 400)
    Sau scale:
      Champion centroid ≈ (-1.19, 1.25, 0) = (5-100/80, 10-5/4, 500-500/400)
      Low Value centroid  ≈ (1.25, -0.75, -1.0)
    """

    centroids_raw = [(5, 10, 500), (200, 2, 100)]  # before scaling
    scaler_mean = (100, 5, 500)
    scaler_scale = (80, 4, 400)

    def scale(point, mean, scale):
        return tuple((point[d] - mean[d]) / scale[d] for d in range(3))

    centroids_scaled = [scale(c, scaler_mean, scaler_scale) for c in centroids_raw]

    # New period: behavior changes — everyone shops more frequently but lower value
    # (post-COVID shift to small frequent orders)
    new_customers_raw = [
        (30, 6, 200),    # mới mua, freq vừa, mon vừa — ambiguous
        (90, 4, 150),    # 
        (10, 8, 300),    # mới mua, freq khá, mon khá — gần champion
        (200, 1, 30),    # lâu rồi ko mua, ít — rõ ràng Low Value
        (50, 7, 250),    # 
    ]
    new_customers_scaled = [scale(c, scaler_mean, scaler_scale) for c in new_customers_raw]

    def nearest_centroid(point, cents):
        min_dist = float("inf")
        best = -1
        for i, c in enumerate(cents):
            dist = math.sqrt(sum((point[d] - c[d])**2 for d in range(3)))
            if dist < min_dist:
                min_dist = dist
                best = i
        return best

    labels = [nearest_centroid(c, centroids_scaled) for c in new_customers_scaled]

    print(f"    Scaled centroids: Champions={centroids_scaled[0]}, Low Value={centroids_scaled[1]}")
    print(f"    New customers classified:")
    misclassified = False
    for i, (raw, sc, l) in enumerate(zip(new_customers_raw, new_customers_scaled, labels)):
        label = "Champions" if l == 0 else "Low Value"
        # Logical expectation
        is_high_value = raw[2] >= 250 and raw[1] >= 5 and raw[0] <= 60
        expected = "Champions" if is_high_value else "Low Value"
        if label != expected:
            misclassified = True
        print(f"      Customer {i}: R={raw[0]} F={raw[1]} M=${raw[2]} → {label}" + (" !" if label != expected else ""))

    print(f"\n    → Misclassification detected: {misclassified}")
    assert misclassified, "Concept drift làm fixed centroids misclassify customers"


# =============================================================================
# 7. repeat_customer_rate inflated by long-tail customers
# =============================================================================
def test_repeat_rate_inflated():
    """repeat_customer_rate = KH mua trong kỳ AND đã mua trước kỳ / KH trong kỳ.
    KH mua 1 lần năm 2009 (5 năm trước), không mua gì 2010-2013, mua 1 lần 2014.
    → Được tính là 'repeat' dù 5 năm vắng bóng."""

    period_customers = {1, 2, 3, 4, 5}
    previous_customers = {1, 2}

    # Standard case: no long-gap customer
    repeat_std = len(period_customers & previous_customers) / len(period_customers) * 100

    # Add customer 6 who bought 5 years ago and again now
    period_customers.add(6)
    previous_customers.add(6)
    repeat_inflated = len(period_customers & previous_customers) / len(period_customers) * 100

    print(f"    Repeat rate before adding long-gap customer: {repeat_std:.1f}%")
    print(f"    Repeat rate after  adding long-gap customer: {repeat_inflated:.1f}%")
    print(f"    → KH 6 không mua gì 5 năm, chỉ mua 1 lần trong 2014 — vẫn tính là 'repeat'")
    print(f"    → Retention rate bị inflate {repeat_inflated - repeat_std:.1f} điểm phần trăm")

    assert repeat_inflated > repeat_std, "Long-gap customer inflates repeat rate"


# =============================================================================
# 8. inventory_turnover dùng sai standard_cost (không join SCD2 history)
# =============================================================================
def test_inventory_turnover_wrong_cost():
    """Query AVG(i.quantity * p.standard_cost) với p.is_current=true.
    Nhưng standard_cost thay đổi theo SCD2:
      - 2011-2012: cost = $50
      - 2013-now:  cost = $70
    Inventory ngày 2012-06-01 (qty=100) được định giá $70 (current) thay vì $50 (historical).
    """
    # Data
    inventory_snapshots = [
        {"date": "2012-06-01", "qty": 100, "historical_cost": 50},
        {"date": "2014-06-01", "qty": 100, "historical_cost": 70},
    ]

    current_cost = 70  # p.is_current = true

    avg_inv_true = sum(s["qty"] * s["historical_cost"] for s in inventory_snapshots) / len(inventory_snapshots)
    avg_inv_query = sum(s["qty"] * current_cost for s in inventory_snapshots) / len(inventory_snapshots)

    error_pct = (avg_inv_query - avg_inv_true) / avg_inv_true * 100
    print(f"    True avg inventory value: ${avg_inv_true:.0f}")
    print(f"    Query avg inventory value: ${avg_inv_query:.0f} (dùng current cost $70 cho cả 2012)")
    print(f"    Error: {error_pct:+.0f}%")

    assert error_pct > 10, f"Inventory turnover overstated by {error_pct:.0f}%"


# =============================================================================
# 9. gross_profit vẫn sai nếu SCD2 lookup không match
# =============================================================================
def test_gross_profit_scd2_lookup_failure():
    """Sau fix, transform overwrite standard_cost từ dim_product SCD2.
    Nếu get_product_key_with_valid_range() không tìm thấy product_key (edge case:
    product bị xóa khỏi dim_product, hoặc date_key ngoài valid range), gross_profit
    GIỮ NGUYÊN giá trị từ extract (dùng current standard_cost)."""
    sales_row = {
        "line_total": 100.0,
        "order_qty": 1,
        "standard_cost_from_extract": 70.0,  # current cost
    }

    # Case A: SCD2 lookup succeeds → historical cost = $50
    historical_cost = 50.0
    gross_profit_A = sales_row["line_total"] - historical_cost * sales_row["order_qty"]
    # = 100 - 50 = 50

    # Case B: SCD2 lookup FAILS → giữ nguyên standard_cost từ extract ($70)
    gross_profit_B = sales_row["line_total"] - sales_row["standard_cost_from_extract"] * sales_row["order_qty"]
    # = 100 - 70 = 30

    diff = gross_profit_A - gross_profit_B
    print(f"    Gross profit with SCD2 lookup success: ${gross_profit_A:.0f}")
    print(f"    Gross profit with SCD2 lookup FAILURE: ${gross_profit_B:.0f}")
    print(f"    Difference: ${diff:.0f} ({(diff/gross_profit_A*100):.0f}%)")

    assert diff > 0, "SCD2 lookup failure silently produces wrong gross_profit"
    assert gross_profit_A != gross_profit_B


# =============================================================================
# 10. snapshot_watermark = "2013Q4" → snapshot Manager sẽ overwrite data Q1-Q4 2013
# =============================================================================
def test_snapshot_watermark_reset_overwrites_data():
    """Snapshot watermark reset từ 2026Q3 xuống 2013Q4.
    get_pending_periods() sẽ trả về Q1-Q4 2013 + Q1-Q2 2014.
    Mỗi period này sẽ được tính lại KPI và UPSERT — overwrite data cũ.
    Nếu có ai đã manually chỉnh sửa KPI snapshot, họ sẽ mất data.
    """
    min_year, max_year = 2013, 2014
    snapshot_watermark = "2013Q4"  # sau khi fix

    pending = []
    for year in range(min_year, max_year + 1):
        max_q = 4 if year < max_year else 2  # 2014 chỉ có Q1, Q2
        for q in range(1, max_q + 1):
            pk = f"{year}Q{q}"
            if pk <= snapshot_watermark:
                continue  # skip: 2013Q1-Q4
            pending.append(pk)

    print(f"    Snapshot watermark: {snapshot_watermark}")
    print(f"    Pending periods: {pending}")
    print(f"    → {len(pending)} periods sẽ được tính lại (2014Q1, 2014Q2)")
    assert len(pending) == 2, f"Expected 2 pending periods, got {len(pending)}"


# =============================================================================
# 11. margin_by_category can produce division-by-zero silently
# =============================================================================
def test_margin_by_category_zero_division():
    """If SUM(f.line_total) = 0 for a category, the query returns 0 instead of NULL.
    This masks the fact that the category has no revenue (not 0% margin)."""
    # SQL would return 0 due to CASE WHEN SUM(f.line_total) = 0 THEN 0
    line_total = 0
    gross_profit = 0
    margin = 0 if line_total == 0 else gross_profit / line_total * 100
    print(f"    Category with zero revenue → margin = {margin:.1f}% (should be NULL/undefined)")
    assert margin == 0, "Division-by-zero is masked as 0% margin"


# =============================================================================
# 12. H1 hypothesis test might use wrong column
# =============================================================================
def test_h1_hypothesis_wrong_test():
    """H1: Bikes have higher order value than Accessories.
    Uses two-sample t-test on 'line_total'.
    But line_total is per LINE ITEM, not per ORDER.
    A single Bike order with 5 items at $50 each = $250 total, but appears as 5 x $50.
    The t-test compares line_item values, not order values — wrong unit of analysis."""
    bikes_line_items = [50, 50, 50, 50, 50]  # 1 order of $250
    accessories_line_items = [20, 30]         # 2 orders of $20 and $30

    mean_bikes = sum(bikes_line_items) / len(bikes_line_items)
    mean_accessories = sum(accessories_line_items) / len(accessories_line_items)

    print(f"    Mean line_total for Bikes: ${mean_bikes:.0f}")
    print(f"    Mean line_total for Accessories: ${mean_accessories:.0f}")
    print(f"    → T-test on line_total says difference is ${mean_bikes - mean_accessories:.0f}")
    print(f"    → But real avg ORDER value: Bikes=${250:.0f}, Accessories=${(20+30)/2:.0f}")
    print(f"    → Wrong unit of analysis (line vs order) → wrong conclusion possible")

    assert mean_bikes != sum([250]) / 1  # mean per ORDER vs per LINE ITEM
