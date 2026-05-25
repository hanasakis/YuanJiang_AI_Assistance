"""Tests for src/data_ops/sql_guard.py — SQL safety validation."""
from __future__ import annotations

import pytest

from src.data_ops.sql_guard import (
    ALLOWED_TABLES,
    GuardResult,
    inspect_sql,
    validate_sql,
)


# ============================================================
# validate_sql — safe queries should pass
# ============================================================

class TestSafeSelect:
    def test_simple_select(self):
        result = validate_sql("SELECT * FROM orders")
        assert result.allowed
        assert result.tables_referenced == ["orders"]

    def test_select_with_where(self):
        result = validate_sql(
            "SELECT seller_id, delay_rate_pct "
            "FROM seller_delivery_metrics "
            "WHERE delay_rate_pct > 15"
        )
        assert result.allowed
        assert set(result.tables_referenced) == {"seller_delivery_metrics"}

    def test_select_with_join(self):
        result = validate_sql(
            "SELECT o.order_id, r.review_score "
            "FROM orders o "
            "JOIN order_reviews r ON o.order_id = r.order_id"
        )
        assert result.allowed
        assert set(result.tables_referenced) == {"orders", "order_reviews"}

    def test_select_with_cte(self):
        result = validate_sql(
            "WITH risky AS ("
            "  SELECT seller_id FROM seller_delivery_metrics "
            "  WHERE delay_rate_pct > 20"
            ") "
            "SELECT * FROM risky"
        )
        assert result.allowed
        # CTE "risky" should NOT appear as an external table
        assert set(result.tables_referenced) == {"seller_delivery_metrics"}

    def test_select_from_view(self):
        result = validate_sql("SELECT * FROM orders_enriched")
        assert result.allowed

    def test_select_with_aggregation(self):
        result = validate_sql(
            "SELECT seller_id, COUNT(*) as cnt, AVG(delay_rate_pct) "
            "FROM seller_delivery_metrics "
            "GROUP BY seller_id "
            "HAVING cnt > 5 "
            "ORDER BY cnt DESC "
            "LIMIT 10"
        )
        assert result.allowed

    def test_select_with_subquery(self):
        result = validate_sql(
            "SELECT * FROM ("
            "  SELECT seller_id, delay_rate_pct "
            "  FROM seller_delivery_metrics "
            "  WHERE delay_rate_pct > 10"
            ") sub"
        )
        assert result.allowed

    def test_case_insensitive_select(self):
        result = validate_sql("select * from orders")
        assert result.allowed


# ============================================================
# validate_sql — dangerous queries should be BLOCKED
# ============================================================

class TestDangerousBlocked:
    def test_insert_blocked(self):
        result = validate_sql("INSERT INTO orders VALUES (1, 'test')")
        assert not result.allowed
        assert "INSERT" in result.reason.upper()

    def test_update_blocked(self):
        result = validate_sql("UPDATE orders SET order_status = 'xxx'")
        assert not result.allowed
        assert "UPDATE" in result.reason.upper()

    def test_delete_blocked(self):
        result = validate_sql("DELETE FROM orders WHERE order_id = '1'")
        assert not result.allowed
        assert "DELETE" in result.reason.upper()

    def test_drop_blocked(self):
        result = validate_sql("DROP TABLE orders")
        assert not result.allowed
        assert "DROP" in result.reason.upper()

    def test_alter_blocked(self):
        result = validate_sql("ALTER TABLE orders ADD COLUMN x INTEGER")
        assert not result.allowed
        assert "ALTER" in result.reason.upper()

    def test_create_blocked(self):
        result = validate_sql("CREATE TABLE hack (id INT)")
        assert not result.allowed
        assert "CREATE" in result.reason.upper()

    def test_truncate_blocked(self):
        result = validate_sql("TRUNCATE TABLE orders")
        assert not result.allowed

    def test_multiple_statements_blocked(self):
        result = validate_sql(
            "SELECT * FROM orders; DROP TABLE orders;"
        )
        assert not result.allowed
        assert "multiple" in result.reason.lower()

    def test_semicolon_injection_blocked(self):
        result = validate_sql(
            "SELECT * FROM orders; INSERT INTO orders VALUES (1)"
        )
        assert not result.allowed


class TestTableWhitelist:
    def test_unknown_table_blocked(self):
        result = validate_sql("SELECT * FROM secret_table")
        assert not result.allowed
        assert "not in whitelist" in result.reason.lower()

    def test_unknown_table_in_join_blocked(self):
        result = validate_sql(
            "SELECT * FROM orders JOIN hack_table ON 1=1"
        )
        assert not result.allowed
        assert "hack_table" in result.reason.lower()

    def test_unknown_table_in_subquery_blocked(self):
        result = validate_sql(
            "SELECT * FROM (SELECT * FROM secret) sub"
        )
        assert not result.allowed

    def test_custom_whitelist(self):
        custom = {"my_view", "my_table"}
        assert validate_sql("SELECT * FROM my_view", allowed_tables=custom).allowed
        assert not validate_sql("SELECT * FROM orders", allowed_tables=custom).allowed

    def test_all_default_tables_are_allowed(self):
        for table in ALLOWED_TABLES:
            result = validate_sql(f"SELECT * FROM {table}")
            assert result.allowed, f"Table '{table}' should be in whitelist"


# ============================================================
# Edge cases
# ============================================================

class TestEdgeCases:
    def test_empty_sql(self):
        result = validate_sql("")
        assert not result.allowed

    def test_whitespace_only(self):
        result = validate_sql("   \n  \t  ")
        assert not result.allowed

    def test_gibberish(self):
        result = validate_sql("not a sql statement at all")
        assert not result.allowed

    def test_guard_result_bool(self):
        assert bool(GuardResult(True, "OK")) is True
        assert bool(GuardResult(False, "bad")) is False


# ============================================================
# inspect_sql
# ============================================================

class TestInspectSql:
    def test_inspect_returns_structure(self):
        info = inspect_sql(
            "SELECT order_id, review_score FROM orders_enriched LIMIT 5"
        )
        assert info["valid"]
        assert info["kind"] == "select"
        assert "orders_enriched" in info["tables"]
        assert "order_id" in info["columns_approx"]
        assert "review_score" in info["columns_approx"]

    def test_inspect_invalid_sql(self):
        info = inspect_sql("FOO BAR BAZ")
        assert not info["valid"]
        assert len(info["issues"]) > 0

    def test_inspect_unsafe_kind(self):
        info = inspect_sql("DROP TABLE orders")
        assert info["kind"] == "drop"
        assert len(info["issues"]) > 0
