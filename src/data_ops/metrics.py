"""E-commerce risk metrics for seller inspection.

All functions are read-only against the Olist DuckDB database.
They return structured dicts — never natural language.
Risk score weights are configurable via RISK_WEIGHTS.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

_DEFAULT_DB = Path(os.getenv("OLIST_DB_PATH", "data/processed/olist.duckdb"))


# ============================================================
# Configurable risk weights
# ============================================================

@dataclass
class RiskWeights:
    """Composite risk score weights. All should sum to 1.0."""

    delay_rate: float = 0.30
    low_review_rate: float = 0.30
    cancel_rate: float = 0.25
    freight_ratio: float = 0.15

    def validate(self) -> None:
        total = self.delay_rate + self.low_review_rate + self.cancel_rate + self.freight_ratio
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Risk weights must sum to 1.0, got {total}")


RISK_WEIGHTS = RiskWeights()


# ============================================================
# Helper
# ============================================================

def _connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    path = Path(db_path) if db_path else _DEFAULT_DB
    if not path.exists():
        raise FileNotFoundError(
            f"DuckDB not found at {path}. Run build_duckdb.py first."
        )
    return duckdb.connect(str(path), read_only=True)


def _date_filter(start: str | None, end: str | None) -> str:
    """Build a SQL WHERE clause for date range filtering."""
    parts: list[str] = []
    if start:
        parts.append(f"o.order_purchase_timestamp >= '{start}'")
    if end:
        parts.append(f"o.order_purchase_timestamp <= '{end}'")
    return " AND ".join(parts) if parts else "1=1"


# ============================================================
# Public API
# ============================================================

def get_top_risky_sellers(
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
    weights: RiskWeights | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return top-N sellers ranked by composite risk score.

    Args:
        limit: Max number of sellers to return.
        start_date: Optional start of order purchase window (YYYY-MM-DD).
        end_date: Optional end of order purchase window (YYYY-MM-DD).
        weights: Optional RiskWeights override. Uses RISK_WEIGHTS if None.
        db_path: Path to DuckDB file. Uses default if None.

    Returns:
        List of seller dicts sorted by risk_score descending:
        [
          {
            "seller_id": "seller_A",
            "seller_city": "Sao Paulo",
            "seller_state": "SP",
            "total_orders": 3,
            "delay_rate_pct": 33.33,
            "cancel_rate_pct": 0.0,
            "low_review_rate_pct": 33.33,
            "avg_freight_ratio": 0.17,
            "avg_delivery_delay_days": 5.0,
            "risk_score": 44.8,
            "risk_level": "P1",
            "risk_breakdown": {
              "delay_risk": 10.0,
              "review_risk": 10.0,
              "cancel_risk": 0.0,
              "freight_risk": 5.1
            }
          },
          ...
        ]
    """
    w = weights or RISK_WEIGHTS
    w.validate()

    date_clause = _date_filter(start_date, end_date)
    con = _connect(db_path)

    try:
        # Combine seller_delivery_metrics + review_risk_metrics
        rows = con.execute(
            f"""
            SELECT
                sdm.seller_id,
                sdm.seller_city,
                sdm.seller_state,
                sdm.total_orders,
                COALESCE(sdm.delay_rate_pct, 0.0) AS delay_rate_pct,
                COALESCE(sdm.cancel_rate_pct, 0.0) AS cancel_rate_pct,
                COALESCE(rrm.negative_review_rate_pct, 0.0) AS low_review_rate_pct,
                COALESCE(sdm.avg_delivery_delay_days, 0.0) AS avg_delivery_delay_days,
                -- freight ratio: freight / price from order_items
                COALESCE(
                    (SELECT AVG(TRY_CAST(freight_value AS DOUBLE)
                        / NULLIF(TRY_CAST(price AS DOUBLE), 0))
                    FROM order_items oi2
                    JOIN orders o2 ON oi2.order_id = o2.order_id
                    WHERE oi2.seller_id = sdm.seller_id
                      AND {date_clause}),
                    0.0
                ) AS avg_freight_ratio,
                COALESCE(sdm.avg_price, 0.0) AS avg_price,
                COALESCE(sdm.total_revenue, 0.0) AS total_revenue
            FROM seller_delivery_metrics sdm
            LEFT JOIN review_risk_metrics rrm
                ON sdm.seller_id = rrm.seller_id
            WHERE sdm.total_orders > 0
            ORDER BY sdm.total_orders DESC
            """
        ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            (
                seller_id, city, state, total_orders,
                delay_rate, cancel_rate, low_review_rate,
                avg_delay_days, freight_ratio, avg_price, total_revenue,
            ) = row

            # Normalize each metric to 0-1
            d_risk = min(float(delay_rate) / 30.0, 1.0)
            r_risk = min(float(low_review_rate) / 30.0, 1.0)
            c_risk = min(float(cancel_rate) / 20.0, 1.0)
            f_risk = min(float(freight_ratio) / 0.5, 1.0)

            breakdown = {
                "delay_risk": round(d_risk * w.delay_rate * 100, 1),
                "review_risk": round(r_risk * w.low_review_rate * 100, 1),
                "cancel_risk": round(c_risk * w.cancel_rate * 100, 1),
                "freight_risk": round(f_risk * w.freight_ratio * 100, 1),
            }
            risk_score = sum(breakdown.values())

            results.append({
                "seller_id": seller_id,
                "seller_city": city,
                "seller_state": state,
                "total_orders": total_orders,
                "delay_rate_pct": round(float(delay_rate), 2),
                "cancel_rate_pct": round(float(cancel_rate), 2),
                "low_review_rate_pct": round(float(low_review_rate), 2),
                "avg_freight_ratio": round(float(freight_ratio), 4),
                "avg_delivery_delay_days": round(float(avg_delay_days), 2),
                "risk_score": round(risk_score, 1),
                "risk_level": _score_to_level(risk_score),
                "risk_breakdown": breakdown,
            })

        results.sort(key=lambda x: x["risk_score"], reverse=True)
        return results[:limit]

    finally:
        con.close()


def get_order_risk(
    order_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return full risk profile for a single order.

    Args:
        order_id: The order ID to look up.
        db_path: Path to DuckDB file.

    Returns:
        Dict with order risk details, or None if order not found.
    """
    con = _connect(db_path)
    try:
        row = con.execute(
            """
            SELECT
                order_id, customer_id, customer_city, customer_state,
                order_status, order_purchase_timestamp,
                order_delivered_customer_date, order_estimated_delivery_date,
                delivery_delay_days, total_payment, payment_types, review_score
            FROM orders_enriched
            WHERE order_id = ?
            """,
            [order_id],
        ).fetchone()

        if row is None:
            return None

        return {
            "order_id": row[0],
            "customer_id": row[1],
            "customer_city": row[2],
            "customer_state": row[3],
            "order_status": row[4],
            "order_purchase_timestamp": row[5],
            "delivered_date": row[6],
            "estimated_date": row[7],
            "delivery_delay_days": round(float(row[8] or 0), 2),
            "total_payment": round(float(row[9] or 0), 2),
            "payment_types": row[10],
            "review_score": int(row[11]) if row[11] is not None else None,
            "is_delayed": bool(row[8] and float(row[8]) > 0),
            "is_low_review": bool(row[11] and int(row[11]) <= 2),
            "risk_flags": _order_flags(row),
        }
    finally:
        con.close()


def get_seller_profile(
    seller_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return complete metric profile for a seller.

    Args:
        seller_id: The seller ID to look up.
        db_path: Path to DuckDB file.

    Returns:
        Dict with all seller metrics, or None if not found.
    """
    con = _connect(db_path)
    try:
        # Check seller exists
        srow = con.execute(
            "SELECT seller_id, seller_city, seller_state FROM sellers WHERE seller_id = ?",
            [seller_id],
        ).fetchone()
        if srow is None:
            return None

        # Delivery metrics
        drow = con.execute(
            "SELECT * FROM seller_delivery_metrics WHERE seller_id = ?",
            [seller_id],
        ).fetchone()

        # Review metrics
        rrow = con.execute(
            "SELECT * FROM review_risk_metrics WHERE seller_id = ?",
            [seller_id],
        ).fetchone()

        # Recent orders
        orders = con.execute(
            """
            SELECT oe.order_id, oe.order_status, oe.delivery_delay_days, oe.review_score
            FROM orders_enriched oe
            JOIN order_items oi ON oe.order_id = oi.order_id
            WHERE oi.seller_id = ?
            ORDER BY oe.order_purchase_timestamp DESC
            LIMIT 10
            """,
            [seller_id],
        ).fetchall()

        return {
            "seller_id": srow[0],
            "seller_city": srow[1],
            "seller_state": srow[2],
            "delivery_metrics": {
                "total_orders": drow[3] if drow else 0,
                "delivered_orders": drow[4] if drow else 0,
                "canceled_orders": drow[5] if drow else 0,
                "avg_delivery_delay_days": round(float(drow[6] or 0), 2) if drow else 0,
                "delay_rate_pct": round(float(drow[7] or 0), 2) if drow else 0,
                "cancel_rate_pct": round(float(drow[8] or 0), 2) if drow else 0,
                "avg_price": round(float(drow[9] or 0), 2) if drow else 0,
                "total_revenue": round(float(drow[10] or 0), 2) if drow else 0,
            },
            "review_metrics": {
                "reviewed_orders": rrow[1] if rrow else 0,
                "avg_review_score": round(float(rrow[2] or 0), 2) if rrow else 0,
                "negative_reviews": rrow[3] if rrow else 0,
                "positive_reviews": rrow[4] if rrow else 0,
                "negative_review_rate_pct": round(float(rrow[5] or 0), 2) if rrow else 0,
                "avg_review_response_days": round(float(rrow[6] or 0), 2) if rrow else 0,
                "worst_review_score": int(rrow[7]) if rrow and rrow[7] else None,
            },
            "recent_orders": [
                {
                    "order_id": o[0],
                    "order_status": o[1],
                    "delivery_delay_days": round(float(o[2] or 0), 2),
                    "review_score": int(o[3]) if o[3] is not None else None,
                }
                for o in orders
            ],
        }
    finally:
        con.close()


def get_category_quality_risk(
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return quality risk for product categories.

    Args:
        category: Specific category name (partial match). If None, returns all.
        start_date: Optional start of order window.
        end_date: Optional end of order window.
        db_path: Path to DuckDB file.

    Returns:
        List of category risk dicts sorted by defect_rate_pct descending.
    """
    con = _connect(db_path)
    try:
        where = "WHERE 1=1"
        params: list = []
        if category:
            where += " AND product_category_name LIKE ?"
            params.append(f"%{category}%")

        rows = con.execute(
            f"""
            SELECT
                product_category_name,
                COUNT(DISTINCT product_id) AS product_count,
                SUM(total_orders) AS total_orders,
                SUM(defect_signals) AS total_defects,
                AVG(avg_review_score) AS category_avg_score,
                ROUND(
                    SUM(defect_signals) * 100.0
                    / NULLIF(SUM(reviewed_orders), 0), 2
                ) AS defect_rate_pct,
                AVG(avg_unit_price) AS avg_price
            FROM product_quality_metrics
            {where}
            GROUP BY product_category_name
            ORDER BY defect_rate_pct DESC
            """,
            params,
        ).fetchall()

        return [
            {
                "product_category_name": r[0],
                "product_count": r[1],
                "total_orders": r[2],
                "total_defects": r[3],
                "category_avg_score": round(float(r[4] or 0), 2),
                "defect_rate_pct": round(float(r[5] or 0), 2),
                "avg_price": round(float(r[6] or 0), 2),
                "risk_level": _category_risk_level(
                    round(float(r[5] or 0), 2)
                ),
            }
            for r in rows
        ]
    finally:
        con.close()


# ============================================================
# Internal helpers
# ============================================================

def _score_to_level(score: float) -> str:
    """Map risk score to P0-P3 level."""
    if score >= 50:
        return "P0"
    elif score >= 30:
        return "P1"
    elif score >= 15:
        return "P2"
    return "P3"


def _category_risk_level(defect_rate: float) -> str:
    if defect_rate >= 40:
        return "P0"
    elif defect_rate >= 20:
        return "P1"
    elif defect_rate >= 10:
        return "P2"
    return "P3"


def _order_flags(row) -> list[str]:
    """Extract risk flags from an order row."""
    flags = []
    # row: (order_id, cust_id, city, state, status, purchase_ts,
    #        delivered_date, estimated_date, delay_days, total_pmt,
    #        pmt_types, review_score)
    status = row[4]
    delay_days = float(row[8] or 0)
    review_score = row[11]

    if status == "canceled":
        flags.append("canceled")
    if delay_days > 3:
        flags.append("significant_delay")
    elif delay_days > 0:
        flags.append("minor_delay")
    if review_score is not None and int(review_score) <= 2:
        flags.append("low_review")
    if review_score is None and status == "delivered":
        flags.append("missing_review")

    return flags
