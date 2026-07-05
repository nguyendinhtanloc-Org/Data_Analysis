"""Integration tests — requires running Docker environment.
Run: docker compose exec etl python -m pytest tests/test_integration.py -v
"""
import pytest
from sqlalchemy import create_engine, text
from src.config import load_postgres_settings, load_mssql_settings


# ==============================================================================
# Connection tests
# ==============================================================================

def test_postgres_connection():
    settings = load_postgres_settings()
    engine = create_engine(settings.connection_string())
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
    assert result == 1, "PostgreSQL connection failed"


def test_mssql_connection():
    settings = load_mssql_settings()
    engine = create_engine(settings.connection_string())
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
    assert result == 1, "MSSQL connection failed"


# ==============================================================================
# Schema existence
# ==============================================================================

def test_dw_schemas_exist():
    settings = load_postgres_settings()
    engine = create_engine(settings.connection_string())
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('dw', 'staging', 'mart')")
        ).fetchall()
    actual = {r[0] for r in rows}
    expected = {"dw", "staging", "mart"}
    assert expected.issubset(actual), f"Missing schemas: {expected - actual}"


def test_dw_tables_exist():
    settings = load_postgres_settings()
    engine = create_engine(settings.connection_string())
    expected = {
        "dw.dim_date", "dw.dim_product", "dw.dim_customer", "dw.dim_territory", "dw.dim_employee",
        "dw.fact_sales", "dw.fact_inventory",
        "dw.ml_customer_segments", "dw.ml_inventory_anomaly", "dw.decision_support",
        "mart.kpi_snapshot", "mart.rfm_snapshot", "mart.customer_migration",
        "mart.inventory_snapshot", "mart.period_comparison",
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_schema IN ('dw', 'mart')")
        ).fetchall()
    actual = {r[0] for r in rows}
    missing = expected - actual
    assert not missing, f"Missing tables: {missing}"


# ==============================================================================
# Fact & dimension data integrity
# ==============================================================================

def test_fact_sales_has_rows():
    settings = load_postgres_settings()
    engine = create_engine(settings.connection_string())
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM dw.fact_sales")).scalar()
    assert count > 0, "fact_sales is empty"


def test_fact_sales_fk_integrity():
    settings = load_postgres_settings()
    engine = create_engine(settings.connection_string())
    queries = [
        ("product_key", "dw.dim_product"),
        ("customer_key", "dw.dim_customer"),
        ("territory_key", "dw.dim_territory"),
    ]
    with engine.connect() as conn:
        for fk_col, ref_table in queries:
            count = conn.execute(
                text(f"""
                    SELECT COUNT(*) FROM dw.fact_sales fs
                    LEFT JOIN {ref_table} d ON fs.{fk_col} = d.{fk_col.split('_')[0]}_key
                    WHERE d.{fk_col.split('_')[0]}_key IS NULL
                """)
            ).scalar()
            assert count == 0, f"{count} orphan {fk_col} in fact_sales"
