"""Query planner: convert natural language to structured JSON query plans.

Uses local Ollama DeepSeek-R1 to parse user intent from natural language
and produce a JSON query plan. The plan may optionally contain a SQL
fragment, which MUST pass through sql_guard before execution.

Key principle: the LLM plans; the guard validates; the caller executes.
"""
from __future__ import annotations

import json
from typing import Any

from src.data_ops.metrics import (
    RiskWeights,
    get_category_quality_risk,
    get_order_risk,
    get_seller_profile,
    get_top_risky_sellers,
)
from src.data_ops.sql_guard import ALLOWED_TABLES, validate_sql
from src.llm.ollama_client import chat
from src.llm.output_cleaner import extract_json_block

# ============================================================
# Query plan schema (documented as the prompt template)
# ============================================================

_QUERY_PLAN_PROMPT = """You are a query planner for an e-commerce operations database.
Convert the user's natural language request into a JSON query plan.

## Available metrics (use these exact metric_name values):
- top_risky_sellers: ranked list of sellers by composite risk score
- seller_profile: detailed metrics for one seller
- order_risk: risk assessment for a single order
- category_quality: quality risk by product category

## Available filters:
- seller_id, category_name, start_date, end_date, limit
- For dates use YYYY-MM-DD format

## SQL generation (only when needed):
If the user asks for a custom metric not covered above, set need_sql=true
and include a safe SELECT query. The SQL will be validated before execution.

## Output format — respond ONLY with this JSON structure:
```json
{
  "intent": "<what the user wants to know, one sentence>",
  "metric_name": "top_risky_sellers | seller_profile | order_risk | category_quality",
  "filters": {
    "seller_id": null,
    "category_name": null,
    "start_date": null,
    "end_date": null,
    "limit": 10
  },
  "risk_level_filter": null,
  "need_sql": false,
  "sql": null
}
```

## Rules:
1. NEVER set need_sql=true if one of the 4 built-in metrics can answer the query.
2. If need_sql=true, the SQL must SELECT ONLY from these tables: {allowed_tables}
3. Dates must be in YYYY-MM-DD format.
4. If the user doesn't specify a date range, leave it as null.
5. Respond ONLY with the JSON block — no other text.
"""


def _plan_prompt(user_query: str) -> str:
    return _QUERY_PLAN_PROMPT.format(
        allowed_tables=", ".join(sorted(ALLOWED_TABLES))
    ) + f"\n\nUser query: {user_query}"


def plan_query(
    user_query: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Convert a natural language query to a structured JSON query plan.

    Calls local Ollama DeepSeek-R1 to parse intent.

    Args:
        user_query: Natural language inspection request.
        model: Override the Ollama model name.

    Returns:
        Query plan dict:
        {
          "intent": "...",
          "metric_name": "top_risky_sellers | seller_profile | order_risk | category_quality",
          "filters": {"seller_id": ..., "category_name": ..., "start_date": ..., "end_date": ..., "limit": ...},
          "risk_level_filter": "P0" | null,
          "need_sql": false,
          "sql": null,
          "sql_validation": null  (populated if need_sql=true)
        }
    """
    prompt = _plan_prompt(user_query)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = chat(messages, temperature=0.05, model=model)
        raw = response.get("message", {}).get("content", "")
    except Exception as exc:
        return {
            "intent": user_query,
            "metric_name": None,
            "filters": {},
            "risk_level_filter": None,
            "need_sql": False,
            "sql": None,
            "sql_validation": None,
            "error": f"LLM call failed: {exc}",
        }

    # Clean R1 output and extract JSON
    from src.llm.output_cleaner import strip_think

    cleaned = strip_think(raw)
    plan = extract_json_block(cleaned)

    if plan is None:
        return {
            "intent": user_query,
            "metric_name": None,
            "filters": {},
            "risk_level_filter": None,
            "need_sql": False,
            "sql": None,
            "sql_validation": None,
            "error": "Failed to extract JSON plan from LLM output",
            "raw_output": raw[:500],
        }

    # Ensure required fields exist
    plan.setdefault("intent", user_query)
    plan.setdefault("metric_name", None)
    plan.setdefault("filters", {})
    plan.setdefault("risk_level_filter", None)
    plan.setdefault("need_sql", False)
    plan.setdefault("sql", None)

    # If the LLM generated SQL, validate it
    if plan.get("need_sql") and plan.get("sql"):
        validation = validate_sql(plan["sql"])
        plan["sql_validation"] = {
            "allowed": validation.allowed,
            "reason": validation.reason,
            "tables_referenced": validation.tables_referenced,
        }
    else:
        plan["sql_validation"] = None

    return plan


def execute_plan(
    plan: dict[str, Any],
    db_path: str | None = None,
    weights: RiskWeights | None = None,
) -> dict[str, Any]:
    """Execute a validated query plan and return structured results.

    This function ONLY routes to pre-built metric functions — it NEVER
    executes raw SQL directly.

    Args:
        plan: Query plan dict from plan_query().
        db_path: Path to DuckDB file.
        weights: Optional risk weight override.

    Returns:
        Dict with keys: plan, results, error (if any).
    """
    metric = plan.get("metric_name")
    filters = plan.get("filters", {}) or {}
    risk_filter = plan.get("risk_level_filter")

    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path
    if weights:
        kwargs["weights"] = weights

    try:
        if metric == "top_risky_sellers":
            limit = int(filters.get("limit", 10))
            results = get_top_risky_sellers(
                limit=limit,
                start_date=filters.get("start_date"),
                end_date=filters.get("end_date"),
                **kwargs,
            )
            if risk_filter:
                results = [r for r in results if r["risk_level"] == risk_filter]
            return {"plan": plan, "results": results}

        elif metric == "seller_profile":
            sid = filters.get("seller_id")
            if not sid:
                return {"plan": plan, "results": None,
                        "error": "seller_id is required for seller_profile"}
            results = get_seller_profile(sid, **{k: v for k, v in kwargs.items()
                                                  if k == "db_path"})
            return {"plan": plan, "results": results}

        elif metric == "order_risk":
            oid = filters.get("order_id") or filters.get("seller_id")
            if not oid:
                return {"plan": plan, "results": None,
                        "error": "order_id is required for order_risk"}
            results = get_order_risk(oid, **{k: v for k, v in kwargs.items()
                                              if k == "db_path"})
            return {"plan": plan, "results": results}

        elif metric == "category_quality":
            results = get_category_quality_risk(
                category=filters.get("category_name"),
                start_date=filters.get("start_date"),
                end_date=filters.get("end_date"),
                **{k: v for k, v in kwargs.items() if k == "db_path"},
            )
            if risk_filter:
                results = [r for r in results
                          if r.get("risk_level") == risk_filter]
            return {"plan": plan, "results": results}

        else:
            return {
                "plan": plan,
                "results": None,
                "error": f"Unknown metric: {metric}. "
                         f"Available: top_risky_sellers, seller_profile, "
                         f"order_risk, category_quality",
            }

    except Exception as exc:
        return {"plan": plan, "results": None, "error": str(exc)}
