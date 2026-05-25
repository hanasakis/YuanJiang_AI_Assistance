"""SQL safety validator for LLM-generated queries.

Uses sqlglot to parse and validate SQL before execution.
Rules:
  - Only SELECT statements allowed
  - Only whitelisted tables/views accessible
  - No subqueries that bypass the table whitelist via CREATE/INSERT
  - No multiple statements (statement injection)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError

# ============================================================
# Allowed tables and views in the Olist DuckDB
# ============================================================

ALLOWED_TABLES: set[str] = {
    # Base tables
    "orders", "order_items", "order_payments", "order_reviews",
    "products", "sellers", "customers", "geolocation",
    "category_translation",
    # Analytical views
    "orders_enriched",
    "seller_delivery_metrics",
    "review_risk_metrics",
    "product_quality_metrics",
}

# SQL statements that are NEVER allowed
_FORBIDDEN_KINDS: set[str] = {
    "insert", "update", "delete", "drop", "alter",
    "create", "truncate", "replace", "merge",
}


@dataclass
class GuardResult:
    """Result of SQL validation."""

    allowed: bool
    reason: str = ""
    tables_referenced: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.allowed


def validate_sql(
    sql: str,
    allowed_tables: set[str] | None = None,
) -> GuardResult:
    """Validate that a SQL string is safe to execute.

    Args:
        sql: The SQL string to validate.
        allowed_tables: Override the default ALLOWED_TABLES whitelist.

    Returns:
        GuardResult with allowed=False and a reason if the SQL is dangerous.
    """
    tables = allowed_tables or ALLOWED_TABLES

    # Rule 0: Must be non-empty
    stripped = sql.strip()
    if not stripped:
        return GuardResult(False, "SQL is empty")

    # Rule 1: No statement injection — only one statement
    try:
        statements = sqlglot.parse(stripped, read="duckdb")
    except ParseError as e:
        return GuardResult(False, f"SQL parse error: {e}")

    if statements is None or len(statements) == 0:
        return GuardResult(False, "No valid SQL statement found")

    if len(statements) > 1:
        return GuardResult(
            False,
            f"Multiple statements detected ({len(statements)}). "
            f"Only single SELECT allowed.",
        )

    stmt = statements[0]

    # Rule 2: Only SELECT
    kind = stmt.key.lower() if hasattr(stmt, "key") else type(stmt).__name__.lower()
    if kind in _FORBIDDEN_KINDS:
        return GuardResult(False, f"{kind.upper()} is forbidden. Only SELECT allowed.")

    if kind != "select":
        return GuardResult(
            False, f"Unknown or unsupported statement type: {kind}"
        )

    # Rule 3: All referenced tables must be in the whitelist
    try:
        referenced = _extract_tables(stmt)
    except Exception:
        return GuardResult(False, "Could not extract table references from SQL")

    unknown = [t for t in referenced if t.lower() not in tables]
    if unknown:
        return GuardResult(
            False,
            f"Table(s) not in whitelist: {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(tables))}",
        )

    return GuardResult(True, "OK", tables_referenced=referenced)


def _extract_tables(statement: exp.Expression) -> list[str]:
    """Extract all table names referenced in a SQL statement.

    Walks the AST and collects table names from FROM, JOIN, and subquery
    references. CTE names (WITH clauses) are excluded — they are temporary
    and defined within the query.
    """
    tables: list[str] = []
    cte_names: set[str] = set()

    # Collect CTE names first — these are NOT external tables
    for node in statement.walk():
        if isinstance(node, exp.CTE):
            if node.alias:
                cte_names.add(node.alias.lower())

    for node in statement.walk():
        if isinstance(node, exp.Table):
            name = node.name.lower() if node.name else ""
            if name and name not in cte_names and name not in tables:
                tables.append(name)

    return tables


def inspect_sql(sql: str) -> dict[str, Any]:
    """Return a human-readable inspection report for a SQL string.

    Does NOT execute anything — only parses and reports structure.

    Args:
        sql: The SQL string to inspect.

    Returns:
        Dict with keys: valid, kind, tables, columns_approx, issues.
    """
    result: dict[str, Any] = {
        "valid": True,
        "kind": None,
        "tables": [],
        "columns_approx": [],
        "issues": [],
    }

    try:
        parsed = sqlglot.parse(sql, read="duckdb")
    except ParseError as e:
        return {"valid": False, "kind": None, "tables": [],
                "columns_approx": [], "issues": [str(e)]}

    if not parsed:
        result["valid"] = False
        result["issues"].append("No statement found")
        return result

    stmt = parsed[0]
    result["kind"] = stmt.key.lower() if hasattr(stmt, "key") else "unknown"

    try:
        result["tables"] = _extract_tables(stmt)
    except Exception:
        result["tables"] = []

    # Approximate column list from top-level SELECT
    try:
        if isinstance(stmt, exp.Select):
            for sel in stmt.expressions:
                if isinstance(sel, exp.Column):
                    result["columns_approx"].append(sel.name)
                elif isinstance(sel, exp.Alias):
                    result["columns_approx"].append(sel.alias or "?")
    except Exception:
        pass

    if result["kind"] != "select":
        result["issues"].append(f"Non-SELECT statement: {result['kind']}")

    return result
