"""data_ops — Olist e-commerce data ingestion, DuckDB analytics, and SQL safety.

Responsibilities:
- Download Olist dataset from Kaggle / local mirror
- Build DuckDB schema with foreign-key relationships
- Compute seller-level risk metrics (delay, cancel, negative review rates)
- Validate generated SQL with sqlglot before execution

Data flow: data/raw/*.csv → DuckDB → computed metrics → tools layer.
"""

__all__: list[str] = []
