import pandas as pd
import numpy as np
from datetime import datetime
from src.etl.transform import (
    transform_dim_date,
    transform_dim_product,
    transform_dim_customer,
    transform_dim_territory,
    transform_dim_employee,
    transform_fact_sales,
    standardize_column_names,
    deduplicate_by_modified,
)


def test_standardize_column_names():
    df = pd.DataFrame({"Product ID": [1], "  Name  ": ["A"], "ModifiedDate": [datetime.now()]})
    result = standardize_column_names(df)
    assert list(result.columns) == ["product_id", "name", "modifieddate"]


def test_deduplicate_by_modified():
    df = pd.DataFrame({
        "id": [1, 1, 2],
        "name": ["old", "new", "only"],
        "modified_date": ["2020-01-01", "2020-06-01", "2020-03-01"],
    })
    result = deduplicate_by_modified(df, "id")
    assert len(result) == 2
    assert result.iloc[0]["name"] == "new"


def test_transform_dim_date():
    df = transform_dim_date(2020, 2021)
    assert len(df) == 731
    assert list(df.columns) == ["date_key", "date", "day", "month", "quarter", "year", "is_weekend"]
    assert df.iloc[0]["year"] == 2020
    assert df.iloc[-1]["year"] == 2021


def test_transform_dim_product_drops_negative_price():
    df_raw = pd.DataFrame({
        "ProductID": [1, 2],
        "Name": ["Good", "Bad"],
        "ListPrice": [100.0, -5.0],
        "StandardCost": [50.0, 20.0],
        "ModifiedDate": ["2020-01-01", "2020-01-01"],
        "SubcategoryName": [None, None],
        "CategoryName": [None, None],
    })
    df_raw["ModifiedDate"] = pd.to_datetime(df_raw["ModifiedDate"])
    result = transform_dim_product(df_raw)
    assert len(result) == 1
    assert result.iloc[0]["product_id"] == 1


def test_transform_dim_customer_fills_unknowns():
    df_raw = pd.DataFrame({
        "CustomerID": [1],
        "FullName": [None],
        "CustomerType": [None],
        "Country": ["US"],
        "StateProvince": ["WA"],
        "TerritoryID": [1],
        "ModifiedDate": ["2020-01-01"],
    })
    result = transform_dim_customer(df_raw)
    assert result.iloc[0]["full_name"] == "Unknown"
    assert result.iloc[0]["customer_type"] == "Unknown"


def test_transform_fact_sales_lookup():
    dim_product = pd.DataFrame({
        "product_key": [10, 20],
        "product_id": [1, 1],
        "name": ["Old Price", "New Price"],
        "standard_cost": [50.0, 80.0],
        "valid_from": [pd.Timestamp("2010-01-01"), pd.Timestamp("2012-01-01")],
        "valid_to": [pd.Timestamp("2012-01-01"), None],
        "is_current": [False, True],
    })
    dim_customer = pd.DataFrame({
        "customer_key": [100],
        "customer_id": [1],
        "customer_type": ["Individual"],
    })
    dim_territory = pd.DataFrame({
        "territory_key": [5],
        "territory_id": [1],
    })
    dim_employee = pd.DataFrame({
        "employee_key": [50],
        "employee_id": [1],
    })

    # Sale in 2011 — should match product_key=10 (Old Price, standard_cost=50)
    df_raw = pd.DataFrame({
        "SalesOrderID": [1000],
        "SalesOrderDetailID": [1001],
        "OrderDate": ["2011-06-01"],
        "ProductID": [1],
        "CustomerID": [1],
        "TerritoryID": [1],
        "SalesPersonID": [1],
        "OrderQty": [2],
        "UnitPrice": [200.0],
        "UnitPriceDiscount": [0],
        "LineTotal": [400.0],
        "StandardCost": [80.0],
        "ModifiedDate": ["2020-01-01"],
    })
    df_raw["ModifiedDate"] = pd.to_datetime(df_raw["ModifiedDate"])
    result = transform_fact_sales(df_raw, dim_product, dim_customer, dim_territory, dim_employee)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["product_key"] == 10, f"Expected product_key=10 (SCD2 lookup), got {row['product_key']}"
    assert row["standard_cost"] == 50.0, f"Expected historical cost 50.0, got {row['standard_cost']}"
    assert row["gross_profit"] == 400.0 - (50.0 * 2), f"Gross profit mismatch: {row['gross_profit']}"
