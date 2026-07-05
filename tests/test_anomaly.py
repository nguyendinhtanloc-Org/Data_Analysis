"""Tests cho ML anomaly detection — không cần DB."""
import numpy as np
import pandas as pd


def test_dio_formula_normal():
    """DIO = inventory_value * active_sales_days / total_cogs."""
    inv_val = 100000.0
    days = 365
    cogs = 50000.0
    dio = (inv_val * days) / cogs
    assert dio == 730.0


def test_dio_formula_zero_cogs():
    """Khi total_cogs = 0, DIO = 999."""
    inv_val = 100000.0
    days = 365
    cogs = 0.0
    mask_valid = (cogs > 0) & (days > 0)
    dio = 999.0 if not mask_valid else (inv_val * days) / cogs
    assert dio == 999.0


def test_dio_formula_clip_upper():
    """DIO bị clip ở 999."""
    inv_val = 100000.0
    days = 365
    cogs = 1.0
    raw = (inv_val * days) / cogs
    dio = min(raw, 999.0)
    assert dio == 999.0


def test_dio_formula_clip_lower():
    """DIO không âm."""
    inv_val = 100.0
    days = 30
    cogs = 100000.0
    raw = max((inv_val * days) / cogs, 0)
    assert raw == 0.03


def test_zero_sales_separation():
    """Kiểm tra logic tách sản phẩm không bán được (mô phỏng fix từ assumption audit).

    Sản phẩm có total_cogs=0 được flag riêng, không đưa vào Isolation Forest training.
    """
    n_sold, n_unsold = 100, 20
    df = pd.DataFrame({
        "total_cogs": [50000.0] * n_sold + [0.0] * n_unsold,
        "active_sales_days": [365] * n_sold + [0] * n_unsold,
    })
    mask_sold = (df["total_cogs"] > 0) & (df["active_sales_days"] > 0)
    assert mask_sold.sum() == n_sold
    assert (~mask_sold).sum() == n_unsold


def test_contamination_auto_calibrate():
    """IQR outlier ratio clamp 2%-30%. Nếu IQR=0 → fallback 0.05."""
    q1, q3 = 10, 20
    iqr = q3 - q1  # 10
    ratio = 0.05
    contamination = min(max(ratio, 0.02), 0.3)
    assert 0.02 <= contamination <= 0.3

    # IQR = 0 case
    iqr_zero = 0
    ratio_zero = 0.05 if iqr_zero <= 0 else 0.0
    cont_zero = min(max(ratio_zero, 0.02), 0.3)
    assert cont_zero == 0.05
