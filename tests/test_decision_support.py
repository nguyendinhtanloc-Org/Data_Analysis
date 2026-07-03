"""Tests cho ML decision support module — không cần DB."""
import pandas as pd

from src.ml.decision_support import customer_priority, inventory_priority


def test_customer_priority_champions_high_value():
    row = pd.Series({
        "cluster_label": "Champions",
        "recency_days": 10,
        "monetary": 10000.0,
    })
    priority, action, reason = customer_priority(row)
    assert priority == "HIGH"


def test_customer_priority_champions_medium():
    row = pd.Series({
        "cluster_label": "Champions",
        "recency_days": 10,
        "monetary": 3000.0,
    })
    priority, action, reason = customer_priority(row)
    assert priority == "MEDIUM"


def test_customer_priority_loyal_active_high():
    row = pd.Series({
        "cluster_label": "Loyal Customers",
        "recency_days": 15,
        "monetary": 5000.0,
    })
    priority, action, reason = customer_priority(row)
    assert priority == "HIGH"


def test_customer_priority_loyal_dormant():
    row = pd.Series({
        "cluster_label": "Loyal Customers",
        "recency_days": 200,
        "monetary": 1000.0,
    })
    priority, action, reason = customer_priority(row)
    assert priority == "HIGH"


def test_customer_priority_loyal_medium():
    row = pd.Series({
        "cluster_label": "Loyal Customers",
        "recency_days": 60,
        "monetary": 500.0,
    })
    priority, action, reason = customer_priority(row)
    assert priority == "MEDIUM"


def test_customer_priority_potential_low():
    row = pd.Series({
        "cluster_label": "Potential Loyalists",
        "recency_days": 30,
        "monetary": 200.0,
    })
    priority, action, reason = customer_priority(row)
    assert priority == "LOW"


def test_inventory_priority_zero_sales():
    row = pd.Series({
        "days_inventory_outstanding": 999.0,
        "inventory_value": 10000.0,
        "anomaly_score": 0.0,
        "zero_sales_flag": True,
    })
    priority, action, reason = inventory_priority(row)
    assert priority == "MEDIUM"


def test_inventory_priority_high_dio_and_value():
    row = pd.Series({
        "days_inventory_outstanding": 400.0,
        "inventory_value": 10000.0,
        "anomaly_score": 50.0,
        "zero_sales_flag": False,
    })
    priority, action, reason = inventory_priority(row)
    assert priority == "HIGH"


def test_inventory_priority_medium_dio():
    row = pd.Series({
        "days_inventory_outstanding": 200.0,
        "inventory_value": 1000.0,
        "anomaly_score": 50.0,
        "zero_sales_flag": False,
    })
    priority, action, reason = inventory_priority(row)
    assert priority == "MEDIUM"


def test_inventory_priority_low():
    row = pd.Series({
        "days_inventory_outstanding": 30.0,
        "inventory_value": 500.0,
        "anomaly_score": 0.0,
        "zero_sales_flag": False,
    })
    priority, action, reason = inventory_priority(row)
    assert priority == "LOW"
