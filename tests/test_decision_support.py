"""Tests cho ML decision support module — không cần DB."""
import pandas as pd

from src.ml.decision_support import customer_priority, inventory_priority


def test_customer_priority_high():
    row = pd.Series({
        "signal_type": "Churn Risk",
        "curr_monetary": 15000.0,
        "prev_monetary": 5000.0,
    })
    priority, action = customer_priority(row)
    assert priority == "HIGH"


def test_customer_priority_medium():
    row = pd.Series({
        "signal_type": "Churn Risk",
        "curr_monetary": 7000.0,
        "prev_monetary": 3000.0,
    })
    priority, action = customer_priority(row)
    assert priority == "MEDIUM"


def test_customer_priority_low():
    row = pd.Series({
        "signal_type": "Churn Risk",
        "curr_monetary": 1000.0,
        "prev_monetary": 500.0,
    })
    priority, action = customer_priority(row)
    assert priority == "LOW"


def test_inventory_priority_high():
    row = pd.Series({
        "product_name": "Widget",
        "category": "Bikes",
        "days_inventory_outstanding": 500.0,
    })
    priority, action = inventory_priority(row)
    assert priority == "HIGH"


def test_inventory_priority_low():
    row = pd.Series({
        "product_name": "Widget",
        "category": "Bikes",
        "days_inventory_outstanding": 30.0,
    })
    priority, action = inventory_priority(row)
    assert priority == "LOW"
