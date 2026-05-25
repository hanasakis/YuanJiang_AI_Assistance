"""Shared pytest fixtures for YuanJiang OpsGuard.

Fixtures provided:
- temp_duckdb: in-memory DuckDB with Olist schema pre-created
- sample_orders_df: small DataFrame of synthetic order rows
- mock_ollama_response: canned DeepSeek-R1 style output for deterministic tests
"""

import pytest


@pytest.fixture
def temp_duckdb():
    """Return an in-memory DuckDB connection with Olist tables pre-created."""
    import duckdb
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture
def sample_orders_df():
    """Return a small pandas DataFrame matching the olist_orders schema."""
    import pandas as pd
    return pd.DataFrame({
        "order_id": ["abc123", "def456"],
        "customer_id": ["c1", "c2"],
        "order_status": ["delivered", "shipped"],
        "order_purchase_timestamp": ["2024-01-01", "2024-01-02"],
        "order_delivered_carrier_date": ["2024-01-05", "2024-01-06"],
        "order_delivered_customer_date": ["2024-01-10", None],
        "order_estimated_delivery_date": ["2024-01-08", "2024-01-09"],
    })
