"""Build Olist DuckDB database from CSV files.

Reads Olist CSV files from data/sample (for testing) or data/raw (production),
creates tables, and builds four analytical views for the inspection agent.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb

_DB_PATH = Path("data/processed/olist.duckdb")

# Maps CSV filename → table name
_TABLE_MAP = {
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "olist_customers_dataset.csv": "customers",
    "olist_geolocation_dataset.csv": "geolocation",
    "product_category_name_translation.csv": "category_translation",
}

# CSV → table column type hints for critical timestamp columns
_TYPE_HINTS: dict[str, dict[str, str]] = {
    "orders": {
        "order_purchase_timestamp": "TIMESTAMP",
        "order_approved_at": "TIMESTAMP",
        "order_delivered_carrier_date": "TIMESTAMP",
        "order_delivered_customer_date": "TIMESTAMP",
        "order_estimated_delivery_date": "TIMESTAMP",
    },
    "order_items": {
        "shipping_limit_date": "TIMESTAMP",
    },
    "order_reviews": {
        "review_creation_date": "TIMESTAMP",
        "review_answer_timestamp": "TIMESTAMP",
    },
}


def build_database(
    csv_dir: str | Path = "data/sample/olist",
    db_path: str | Path = _DB_PATH,
    overwrite: bool = True,
) -> Path:
    """Build the Olist DuckDB database from CSV files.

    Args:
        csv_dir: Directory containing Olist CSV files.
        db_path: Output DuckDB file path.
        overwrite: If True, delete existing database before rebuilding.

    Returns:
        Path to the built DuckDB file.
    """
    csv_dir = Path(csv_dir)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if overwrite and db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    loaded: list[str] = []

    try:
        # ---- Phase 1: Load CSVs into raw tables ----
        for csv_file, table_name in _TABLE_MAP.items():
            csv_path = csv_dir / csv_file
            if not csv_path.exists():
                print(f"  [SKIP] {csv_file} not found in {csv_dir}")
                continue

            print(f"  Loading {csv_file} → {table_name} ...")
            con.execute(
                f"CREATE TABLE {table_name} AS SELECT * FROM "
                f"read_csv_auto('{csv_path.as_posix()}', header=true, all_varchar=true)"
            )
            loaded.append(table_name)

        if not loaded:
            print("  No CSV files loaded. Check csv_dir path.")
            con.close()
            return db_path

        print(f"  Loaded {len(loaded)} tables: {loaded}")

        # ---- Phase 2: Cast timestamp columns ----
        for table_name, columns in _TYPE_HINTS.items():
            if table_name not in loaded:
                continue
            for col, dtype in columns.items():
                try:
                    con.execute(
                        f"ALTER TABLE {table_name} "
                        f"ALTER COLUMN \"{col}\" TYPE {dtype} "
                        f"USING strptime(\"{col}\", '%Y-%m-%d %H:%M:%S')"
                    )
                except Exception:
                    pass  # Column may not exist in sample data

        # ---- Phase 3: Create analytical views ----
        _create_orders_enriched_view(con, loaded)
        _create_seller_delivery_metrics(con, loaded)
        _create_review_risk_metrics(con, loaded)
        _create_product_quality_metrics(con, loaded)

        # ---- Verify ----
        views = con.execute(
            "SELECT table_name FROM information_schema.views "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
        print(f"  Views created: {[v[0] for v in views]}")

    finally:
        con.close()

    print("Done.")
    return db_path


def _create_orders_enriched_view(con, loaded: list[str]) -> None:
    """orders_enriched: orders joined with customers, payments, reviews."""
    required = {"orders", "customers", "order_payments", "order_reviews"}
    if not required.issubset(set(loaded)):
        print("  [SKIP] orders_enriched: missing required tables")
        return

    con.execute("""
        CREATE OR REPLACE VIEW orders_enriched AS
        SELECT
            o.order_id,
            o.customer_id,
            c.customer_city,
            c.customer_state,
            o.order_status,
            o.order_purchase_timestamp,
            o.order_approved_at,
            o.order_delivered_carrier_date,
            o.order_delivered_customer_date,
            o.order_estimated_delivery_date,
            -- compute delivery delay in days
            DATEDIFF(
                'day',
                o.order_estimated_delivery_date,
                o.order_delivered_customer_date
            ) AS delivery_delay_days,
            -- payment aggregation
            p.total_payment,
            p.payment_types,
            -- review scores
            r.review_score
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        LEFT JOIN (
            SELECT
                order_id,
                SUM(TRY_CAST(payment_value AS DOUBLE)) AS total_payment,
                STRING_AGG(DISTINCT payment_type, ', ') AS payment_types
            FROM order_payments
            GROUP BY order_id
        ) p ON o.order_id = p.order_id
        LEFT JOIN (
            SELECT DISTINCT
                order_id,
                FIRST_VALUE(TRY_CAST(review_score AS INTEGER))
                    OVER (PARTITION BY order_id ORDER BY review_creation_date DESC)
                AS review_score
            FROM order_reviews
        ) r ON o.order_id = r.order_id
    """)


def _create_seller_delivery_metrics(con, loaded: list[str]) -> None:
    """seller_delivery_metrics: seller-level delivery performance."""
    required = {"orders", "order_items", "sellers"}
    if not required.issubset(set(loaded)):
        print("  [SKIP] seller_delivery_metrics: missing required tables")
        return

    con.execute("""
        CREATE OR REPLACE VIEW seller_delivery_metrics AS
        SELECT
            s.seller_id,
            s.seller_city,
            s.seller_state,
            COUNT(DISTINCT oi.order_id) AS total_orders,
            COUNT(DISTINCT CASE WHEN o.order_status = 'delivered'
                THEN oi.order_id END) AS delivered_orders,
            COUNT(DISTINCT CASE WHEN o.order_status = 'canceled'
                THEN oi.order_id END) AS canceled_orders,
            -- delivery timing (delivered orders only)
            AVG(CASE WHEN o.order_status = 'delivered'
                AND o.order_delivered_customer_date IS NOT NULL
                AND o.order_estimated_delivery_date IS NOT NULL
                THEN DATEDIFF('day',
                    o.order_estimated_delivery_date,
                    o.order_delivered_customer_date)
                END) AS avg_delivery_delay_days,
            -- delay rate: orders delivered AFTER estimated date
            ROUND(
                COUNT(DISTINCT CASE
                    WHEN o.order_status = 'delivered'
                    AND o.order_delivered_customer_date IS NOT NULL
                    AND o.order_estimated_delivery_date IS NOT NULL
                    AND o.order_delivered_customer_date > o.order_estimated_delivery_date
                    THEN oi.order_id END
                ) * 100.0 / NULLIF(
                    COUNT(DISTINCT CASE WHEN o.order_status = 'delivered'
                        THEN oi.order_id END), 0
                ), 2
            ) AS delay_rate_pct,
            -- cancel rate
            ROUND(
                COUNT(DISTINCT CASE WHEN o.order_status = 'canceled'
                    THEN oi.order_id END) * 100.0 / NULLIF(
                    COUNT(DISTINCT oi.order_id), 0
                ), 2
            ) AS cancel_rate_pct,
            -- average order value
            AVG(TRY_CAST(oi.price AS DOUBLE)) AS avg_price,
            SUM(TRY_CAST(oi.price AS DOUBLE)) AS total_revenue
        FROM order_items oi
        JOIN sellers s ON oi.seller_id = s.seller_id
        LEFT JOIN orders o ON oi.order_id = o.order_id
        GROUP BY s.seller_id, s.seller_city, s.seller_state
    """)


def _create_review_risk_metrics(con, loaded: list[str]) -> None:
    """review_risk_metrics: order-level review risk indicators."""
    required = {"orders", "order_items", "order_reviews", "sellers"}
    if not required.issubset(set(loaded)):
        print("  [SKIP] review_risk_metrics: missing required tables")
        return

    con.execute("""
        CREATE OR REPLACE VIEW review_risk_metrics AS
        SELECT
            oi.seller_id,
            COUNT(DISTINCT r.order_id) AS reviewed_orders,
            AVG(TRY_CAST(r.review_score AS DOUBLE)) AS avg_review_score,
            COUNT(DISTINCT CASE
                WHEN TRY_CAST(r.review_score AS INTEGER) <= 2
                THEN r.order_id END
            ) AS negative_reviews,
            COUNT(DISTINCT CASE
                WHEN TRY_CAST(r.review_score AS INTEGER) >= 4
                THEN r.order_id END
            ) AS positive_reviews,
            -- negative review rate
            ROUND(
                COUNT(DISTINCT CASE
                    WHEN TRY_CAST(r.review_score AS INTEGER) <= 2
                    THEN r.order_id END
                ) * 100.0 / NULLIF(COUNT(DISTINCT r.order_id), 0), 2
            ) AS negative_review_rate_pct,
            -- review response time
            AVG(
                DATEDIFF('day',
                    TRY_CAST(r.review_creation_date AS TIMESTAMP),
                    TRY_CAST(r.review_answer_timestamp AS TIMESTAMP)
                )
            ) AS avg_review_response_days,
            -- worst recent review
            MIN(TRY_CAST(r.review_score AS INTEGER)) AS worst_review_score
        FROM order_reviews r
        JOIN orders o ON r.order_id = o.order_id
        JOIN order_items oi ON o.order_id = oi.order_id
        GROUP BY oi.seller_id
    """)


def _create_product_quality_metrics(con, loaded: list[str]) -> None:
    """product_quality_metrics: product-level quality indicators."""
    required = {"order_items", "order_reviews", "products", "orders"}
    if not required.issubset(set(loaded)):
        print("  [SKIP] product_quality_metrics: missing required tables")
        return

    con.execute("""
        CREATE OR REPLACE VIEW product_quality_metrics AS
        SELECT
            p.product_id,
            p.product_category_name,
            COUNT(DISTINCT oi.order_id) AS total_orders,
            COUNT(DISTINCT r.order_id) AS reviewed_orders,
            AVG(TRY_CAST(r.review_score AS DOUBLE)) AS avg_review_score,
            -- defect signal: low review + high price
            COUNT(DISTINCT CASE
                WHEN TRY_CAST(r.review_score AS INTEGER) <= 2
                THEN r.order_id END
            ) AS defect_signals,
            ROUND(
                COUNT(DISTINCT CASE
                    WHEN TRY_CAST(r.review_score AS INTEGER) <= 2
                    THEN r.order_id END
                ) * 100.0 / NULLIF(COUNT(DISTINCT r.order_id), 0), 2
            ) AS defect_rate_pct,
            AVG(TRY_CAST(oi.price AS DOUBLE)) AS avg_unit_price,
            TRY_CAST(p.product_weight_g AS DOUBLE) AS weight_g,
            TRY_CAST(p.product_photos_qty AS INTEGER) AS photos_qty
        FROM products p
        JOIN order_items oi ON p.product_id = oi.product_id
        LEFT JOIN orders o ON oi.order_id = o.order_id
        LEFT JOIN order_reviews r ON oi.order_id = r.order_id
        GROUP BY p.product_id, p.product_category_name,
                 p.product_weight_g, p.product_photos_qty
    """)


def verify_database(db_path: str | Path = _DB_PATH) -> dict:
    """Verify the built Olist DuckDB database integrity.

    Args:
        db_path: Path to the DuckDB file.

    Returns:
        Dict with verification results.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"status": "missing", "error": f"{db_path} not found"}

    con = duckdb.connect(str(db_path))
    results: dict = {"status": "ok", "tables": {}, "views": {}, "issues": []}

    try:
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' AND table_type='BASE TABLE'"
        ).fetchall()
        for (tname,) in tables:
            cnt = con.execute(f'SELECT count(*) FROM "{tname}"').fetchone()[0]
            results["tables"][tname] = cnt

        views = con.execute(
            "SELECT table_name FROM information_schema.views "
            "WHERE table_schema='main'"
        ).fetchall()
        for (vname,) in views:
            cnt = con.execute(f'SELECT count(*) FROM "{vname}"').fetchone()[0]
            results["views"][vname] = cnt

        if not tables:
            results["issues"].append("No base tables found")
        if not views:
            results["issues"].append("No views found")

        if results["issues"]:
            results["status"] = "warning"

    finally:
        con.close()

    return results


if __name__ == "__main__":
    # Default: build from sample data
    csv_source = os.getenv("OLIST_CSV_DIR", "data/sample/olist")
    build_database(csv_source)
    result = verify_database()
    print()
    print("Verification:", result["status"])
    print("Tables:", result["tables"])
    print("Views:", result["views"])
    for issue in result.get("issues", []):
        print(f"  [!] {issue}")
