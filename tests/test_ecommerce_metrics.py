"""Tests for src/data_ops/metrics.py — e-commerce risk metrics.

Uses data/sample/olist DB built by build_duckdb.py. All tests are read-only.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.data_ops.build_duckdb import build_database
from src.data_ops.metrics import (
    RISK_WEIGHTS,
    RiskWeights,
    get_category_quality_risk,
    get_order_risk,
    get_seller_profile,
    get_top_risky_sellers,
)

SAMPLE_DIR = Path("data/sample/olist")


@pytest.fixture
def sample_db():
    """Build a temp DuckDB from sample CSVs and return its path."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "olist.duckdb"
        build_database(csv_dir=SAMPLE_DIR, db_path=db_path, overwrite=True)
        yield db_path


# ============================================================
# RiskWeights
# ============================================================

class TestRiskWeights:
    def test_default_weights_sum_to_one(self):
        w = RiskWeights()
        total = w.delay_rate + w.low_review_rate + w.cancel_rate + w.freight_ratio
        assert abs(total - 1.0) < 0.001

    def test_validate_passes_for_valid_weights(self):
        w = RiskWeights(0.4, 0.3, 0.2, 0.1)
        w.validate()  # should not raise

    def test_validate_raises_for_invalid_weights(self):
        w = RiskWeights(0.5, 0.5, 0.5, 0.5)
        with pytest.raises(ValueError, match="sum to 1.0"):
            w.validate()

    def test_module_default_weights_sum_to_one(self):
        total = (
            RISK_WEIGHTS.delay_rate
            + RISK_WEIGHTS.low_review_rate
            + RISK_WEIGHTS.cancel_rate
            + RISK_WEIGHTS.freight_ratio
        )
        assert abs(total - 1.0) < 0.001


# ============================================================
# get_top_risky_sellers
# ============================================================

class TestGetTopRiskySellers:
    def test_returns_list_of_sellers(self, sample_db):
        results = get_top_risky_sellers(limit=10, db_path=sample_db)
        assert isinstance(results, list)
        assert len(results) > 0
        assert len(results) <= 10

    def test_each_seller_has_required_fields(self, sample_db):
        results = get_top_risky_sellers(limit=5, db_path=sample_db)
        for seller in results:
            assert "seller_id" in seller
            assert "risk_score" in seller
            assert "risk_level" in seller
            assert "risk_breakdown" in seller
            assert "delay_rate_pct" in seller
            assert "cancel_rate_pct" in seller
            assert "low_review_rate_pct" in seller

    def test_risk_score_is_between_0_and_100(self, sample_db):
        results = get_top_risky_sellers(limit=10, db_path=sample_db)
        for seller in results:
            assert 0.0 <= seller["risk_score"] <= 100.0, (
                f"{seller['seller_id']}: risk_score={seller['risk_score']}"
            )

    def test_risk_level_is_valid(self, sample_db):
        results = get_top_risky_sellers(limit=10, db_path=sample_db)
        for seller in results:
            assert seller["risk_level"] in ("P0", "P1", "P2", "P3")

    def test_risk_breakdown_sums_to_score(self, sample_db):
        results = get_top_risky_sellers(limit=10, db_path=sample_db)
        for seller in results:
            bd = seller["risk_breakdown"]
            computed = sum(bd.values())
            assert abs(computed - seller["risk_score"]) < 0.15, (
                f"{seller['seller_id']}: breakdown sum {computed} != "
                f"risk_score {seller['risk_score']}"
            )

    def test_results_sorted_by_risk_desc(self, sample_db):
        results = get_top_risky_sellers(limit=10, db_path=sample_db)
        scores = [s["risk_score"] for s in results]
        assert scores == sorted(scores, reverse=True)

    def test_limit_respected(self, sample_db):
        for limit in [1, 3]:
            results = get_top_risky_sellers(limit=limit, db_path=sample_db)
            assert len(results) <= limit

    def test_custom_weights_affect_ranking(self, sample_db):
        """Different weights should produce different scores."""
        default = get_top_risky_sellers(limit=10, db_path=sample_db)

        delay_heavy = RiskWeights(delay_rate=0.7, low_review_rate=0.1,
                                   cancel_rate=0.1, freight_ratio=0.1)
        delay_heavy.validate()
        alt = get_top_risky_sellers(limit=10, db_path=sample_db,
                                     weights=delay_heavy)

        # Scores should differ (unless all metrics are zero)
        for d, a in zip(default, alt):
            assert d["seller_id"] == a["seller_id"]  # same sellers
            # scores may differ


# ============================================================
# get_order_risk
# ============================================================

class TestGetOrderRisk:
    def test_returns_none_for_missing_order(self, sample_db):
        result = get_order_risk("nonexistent_order", db_path=sample_db)
        assert result is None

    def test_returns_risk_for_known_order(self, sample_db):
        result = get_order_risk("ord_001", db_path=sample_db)
        assert result is not None
        assert result["order_id"] == "ord_001"
        assert "order_status" in result
        assert "delivery_delay_days" in result
        assert "risk_flags" in result
        assert isinstance(result["risk_flags"], list)

    def test_canceled_order_has_canceled_flag(self, sample_db):
        result = get_order_risk("ord_004", db_path=sample_db)
        assert result is not None
        assert result["order_status"] == "canceled"
        assert "canceled" in result["risk_flags"]


# ============================================================
# get_seller_profile
# ============================================================

class TestGetSellerProfile:
    def test_returns_none_for_missing_seller(self, sample_db):
        result = get_seller_profile("nonexistent_seller", db_path=sample_db)
        assert result is None

    def test_returns_profile_for_known_seller(self, sample_db):
        result = get_seller_profile("seller_A", db_path=sample_db)
        assert result is not None
        assert result["seller_id"] == "seller_A"
        assert "delivery_metrics" in result
        assert "review_metrics" in result
        assert "recent_orders" in result
        assert result["delivery_metrics"]["total_orders"] > 0

    def test_missing_db_raises(self):
        with pytest.raises(FileNotFoundError):
            get_seller_profile("seller_A", db_path="/nonexistent/db.duckdb")


# ============================================================
# get_category_quality_risk
# ============================================================

class TestGetCategoryQualityRisk:
    def test_returns_all_categories(self, sample_db):
        results = get_category_quality_risk(db_path=sample_db)
        assert isinstance(results, list)
        assert len(results) > 0
        for cat in results:
            assert "product_category_name" in cat
            assert "defect_rate_pct" in cat
            assert "risk_level" in cat

    def test_risk_level_is_valid(self, sample_db):
        results = get_category_quality_risk(db_path=sample_db)
        for cat in results:
            assert cat["risk_level"] in ("P0", "P1", "P2", "P3")

    def test_filter_by_category(self, sample_db):
        results = get_category_quality_risk(
            category="electronics", db_path=sample_db
        )
        assert len(results) > 0
        for cat in results:
            assert "electronics" in cat["product_category_name"].lower()

    def test_results_sorted_by_defect_desc(self, sample_db):
        results = get_category_quality_risk(db_path=sample_db)
        rates = [c["defect_rate_pct"] for c in results]
        assert rates == sorted(rates, reverse=True)
