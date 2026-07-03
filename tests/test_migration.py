"""Tests cho ML migration module — không cần DB."""
import pandas as pd
import numpy as np

from src.ml.migration import build_migration_matrix


def _make_rfm_df(customer_keys, cluster_labels, monetary_values):
    return pd.DataFrame({
        "customer_key": customer_keys,
        "cluster_label": cluster_labels,
        "monetary": monetary_values,
    })


def test_build_migration_empty_prev():
    prev = pd.DataFrame()
    curr = _make_rfm_df([1, 2], ["Champions", "At-Risk"], [1000, 200])
    result = build_migration_matrix(prev, curr, "2013Q1", "2013Q2")
    assert result.empty


def test_build_migration_empty_curr():
    prev = _make_rfm_df([1, 2], ["Champions", "At-Risk"], [1000, 200])
    curr = pd.DataFrame()
    result = build_migration_matrix(prev, curr, "2013Q1", "2013Q2")
    assert result.empty


def test_build_migration_normal():
    prev = _make_rfm_df([1, 2, 3], ["Champions", "Loyal", "At-Risk"], [1000, 500, 200])
    curr = _make_rfm_df([1, 2, 4], ["Champions", "At-Risk", "New"], [1200, 300, 100])
    result = build_migration_matrix(prev, curr, "2013Q1", "2013Q2")
    assert len(result) == 4  # 3 from prev + 1 new (customer 4)
    assert result.loc[result["customer_key"] == 3, "is_churned"].iloc[0] == True
    assert result.loc[result["customer_key"] == 4, "is_new"].iloc[0] == True
    assert "prev_period_key" in result.columns
    assert "curr_period_key" in result.columns
    assert "prev_cluster" in result.columns
    assert "curr_cluster" in result.columns


def test_build_migration_churn_flag():
    prev = _make_rfm_df([1, 2], ["Champions", "Loyal"], [1000, 500])
    curr = _make_rfm_df([1], ["Champions"], [1200])
    result = build_migration_matrix(prev, curr, "2013Q1", "2013Q2")
    churned = result[result["is_churned"]]
    assert len(churned) == 1
    assert churned.iloc[0]["customer_key"] == 2
    assert churned.iloc[0]["curr_cluster"] == "Churned"


def test_build_migration_new_flag():
    prev = _make_rfm_df([1], ["Champions"], [1000])
    curr = _make_rfm_df([1, 2], ["Champions", "New"], [1200, 100])
    result = build_migration_matrix(prev, curr, "2013Q1", "2013Q2")
    new = result[result["is_new"]]
    assert len(new) == 1
    assert new.iloc[0]["customer_key"] == 2
    assert new.iloc[0]["prev_cluster"] == "New"
