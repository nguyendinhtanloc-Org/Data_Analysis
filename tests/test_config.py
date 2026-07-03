"""Basic smoke tests — requires DWH environment with pandas/sqlalchemy installed.
Run inside Docker: docker-compose run --rm etl pytest tests/
"""
from src.config import PostgresSettings, MSSQLSettings


def test_postgres_settings_defaults():
    s = PostgresSettings(
        host="localhost",
        port=5432,
        name="testdb",
        user="testuser",
        password="testpass",
    )
    conn = s.connection_string()
    assert "postgresql" in conn
    assert "testuser" in conn


def test_mssql_settings_defaults():
    s = MSSQLSettings(
        host="localhost",
        port="1433",
        name="testdb",
        user="testuser",
        password="testpass",
    )
    conn = s.connection_string()
    assert "mssql" in conn and "pymssql" in conn
