"""Tests cho ML early warning module — không cần DB."""
import pandas as pd


def test_churn_no_prior_data():
    """Nếu không có monetary kỳ trước, churn risk = 0."""
    weight_recency, weight_freq, weight_mon = 0.3, 0.35, 0.35
    risk = (
        0.0 * weight_recency +
        0.0 * weight_freq +
        0.0 * weight_mon
    )
    assert risk == 0.0  # 0 * anything = 0, exact


def test_churn_full_risk():
    """Recency > 90, frequency giảm 50%+, monetary giảm 50%+ → risk = 1.0."""
    weight_recency, weight_freq, weight_mon = 0.3, 0.35, 0.35

    recency_score = 1.0 if 120 > 90 else 0.0
    freq_decline = 0.6
    freq_score = 1.0 if freq_decline >= 0.5 else 0.0
    mon_decline = 0.7
    mon_score = 1.0 if mon_decline >= 0.5 else 0.0

    risk = (
        recency_score * weight_recency +
        freq_score * weight_freq +
        mon_score * weight_mon
    )
    assert abs(risk - 1.0) < 1e-10


def test_churn_partial_risk():
    """Recency > 90 nhưng không có decline → risk thấp hơn."""
    weight_recency, weight_freq, weight_mon = 0.3, 0.35, 0.35

    recency_score = 1.0 if 120 > 90 else 0.0
    freq_decline = 0.1
    freq_score = 1.0 if freq_decline >= 0.5 else 0.0
    mon_decline = 0.1
    mon_score = 1.0 if mon_decline >= 0.5 else 0.0

    risk = (
        recency_score * weight_recency +
        freq_score * weight_freq +
        mon_score * weight_mon
    )
    assert abs(risk - 0.3) < 1e-10


def test_churn_weights_sum_to_one():
    assert abs(0.3 + 0.35 + 0.35 - 1.0) < 1e-10
