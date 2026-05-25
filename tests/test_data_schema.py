"""Tests for src/data_ops/build_duckdb.py — Olist DuckDB schema and views.

All tests use data/sample/olist/*.csv (committed sample data, no network).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import pytest

from src.data_ops.build_duckdb import build_database, verify_database

SAMPLE_DIR = Path("data/sample/olist")


class TestBuildDatabase:
    def test_builds_from_sample_data(self):
        """build_database() should succeed with sample CSVs."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            result = build_database(
                csv_dir=SAMPLE_DIR, db_path=db_path, overwrite=True
            )
            assert result == db_path
            assert db_path.exists()
            assert db_path.stat().st_size > 0

    def test_all_expected_tables_present(self):
        """All sample CSV files should be loaded as tables."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            build_database(csv_dir=SAMPLE_DIR, db_path=db_path)

            con = duckdb.connect(str(db_path))
            tables = con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main' AND table_type='BASE TABLE'"
            ).fetchall()
            table_names = {t[0] for t in tables}

            expected = {
                "orders", "order_items", "order_payments", "order_reviews",
                "products", "sellers", "customers",
            }
            assert expected.issubset(table_names)
            con.close()

    def test_verify_returns_ok(self):
        """verify_database() should report status='ok' on valid DB."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            build_database(csv_dir=SAMPLE_DIR, db_path=db_path)

            result = verify_database(db_path)
            assert result["status"] in ("ok", "warning")
            assert len(result["tables"]) > 0
            assert len(result["views"]) > 0

    def test_verify_missing_db(self):
        """verify_database() should return status='missing' for nonexistent DB."""
        result = verify_database("/nonexistent/olist.duckdb")
        assert result["status"] == "missing"

    def test_empty_csv_dir_handled(self):
        """Empty directory should not crash, should produce DB with no tables."""
        with tempfile.TemporaryDirectory() as tmp:
            csv_dir = Path(tmp) / "empty_csv"
            csv_dir.mkdir()
            db_path = Path(tmp) / "empty.duckdb"
            build_database(csv_dir=csv_dir, db_path=db_path)
            assert db_path.exists()
            result = verify_database(db_path)
            # No tables loaded → issues expected
            assert "issues" in result


class TestOrdersEnrichedView:
    def test_view_exists_and_has_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            build_database(csv_dir=SAMPLE_DIR, db_path=db_path)
            con = duckdb.connect(str(db_path))

            rows = con.execute(
                "SELECT count(*) FROM orders_enriched"
            ).fetchone()[0]
            assert rows > 0

            cols = con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='orders_enriched'"
            ).fetchall()
            col_names = {c[0] for c in cols}
            expected = {
                "order_id", "customer_id", "customer_city", "customer_state",
                "order_status", "delivery_delay_days", "total_payment",
                "payment_types", "review_score",
            }
            assert expected.issubset(col_names)
            con.close()


class TestSellerDeliveryMetrics:
    def test_has_required_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            build_database(csv_dir=SAMPLE_DIR, db_path=db_path)
            con = duckdb.connect(str(db_path))

            cols = con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='seller_delivery_metrics'"
            ).fetchall()
            col_names = {c[0] for c in cols}
            required = {
                "seller_id", "total_orders", "delivered_orders",
                "canceled_orders", "avg_delivery_delay_days",
                "delay_rate_pct", "cancel_rate_pct",
            }
            assert required.issubset(col_names)

            # Should have at least one seller
            n = con.execute(
                "SELECT count(*) FROM seller_delivery_metrics"
            ).fetchone()[0]
            assert n > 0
            con.close()

    def test_metrics_are_within_valid_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            build_database(csv_dir=SAMPLE_DIR, db_path=db_path)
            con = duckdb.connect(str(db_path))

            # delay_rate_pct should be between 0 and 100
            bad = con.execute("""
                SELECT count(*) FROM seller_delivery_metrics
                WHERE delay_rate_pct < 0 OR delay_rate_pct > 100
            """).fetchone()[0]
            assert bad == 0

            # cancel_rate_pct should be between 0 and 100
            bad = con.execute("""
                SELECT count(*) FROM seller_delivery_metrics
                WHERE cancel_rate_pct < 0 OR cancel_rate_pct > 100
            """).fetchone()[0]
            assert bad == 0

            con.close()


class TestReviewRiskMetrics:
    def test_has_required_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            build_database(csv_dir=SAMPLE_DIR, db_path=db_path)
            con = duckdb.connect(str(db_path))

            cols = con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='review_risk_metrics'"
            ).fetchall()
            col_names = {c[0] for c in cols}
            required = {
                "seller_id", "avg_review_score", "negative_reviews",
                "positive_reviews", "negative_review_rate_pct",
                "avg_review_response_days", "worst_review_score",
            }
            assert required.issubset(col_names)
            con.close()

    def test_review_score_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            build_database(csv_dir=SAMPLE_DIR, db_path=db_path)
            con = duckdb.connect(str(db_path))

            # avg review score should be between 1 and 5
            bad = con.execute("""
                SELECT count(*) FROM review_risk_metrics
                WHERE avg_review_score < 1 OR avg_review_score > 5
            """).fetchone()[0]
            assert bad == 0
            con.close()


class TestProductQualityMetrics:
    def test_has_required_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_olist.duckdb"
            build_database(csv_dir=SAMPLE_DIR, db_path=db_path)
            con = duckdb.connect(str(db_path))

            cols = con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='product_quality_metrics'"
            ).fetchall()
            col_names = {c[0] for c in cols}
            required = {
                "product_id", "product_category_name", "total_orders",
                "avg_review_score", "defect_signals", "defect_rate_pct",
                "avg_unit_price",
            }
            assert required.issubset(col_names)

            n = con.execute(
                "SELECT count(*) FROM product_quality_metrics"
            ).fetchone()[0]
            assert n > 0
            con.close()
