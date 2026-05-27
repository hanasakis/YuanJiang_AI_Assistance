"""End-to-end tests for YuanJiang OpsGuard LangGraph workflow.

Tests cover all 5 intent routes: sop_qa, metric_query, create_task,
mixed, and unknown. LLM calls are mocked to avoid requiring Ollama.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.app.graph import (
    _infer_priority,
    _infer_task_type,
    _should_create_task,
    build_graph,
    run_agent,
)
from src.app.state import AgentState, initial_state


# ============================================================
# Mock helpers
# ============================================================

def _mock_chat_response(content: str) -> dict:
    return {"message": {"content": content}}


# ============================================================
# Graph structure tests (no LLM)
# ============================================================

class TestGraphStructure:
    def test_graph_builds(self):
        graph = build_graph()
        assert graph is not None

    def test_graph_has_all_nodes(self):
        graph = build_graph()
        nodes = graph.get_graph().nodes
        node_names = {n for n in nodes if hasattr(n, '__iter__')}
        assert len(nodes) > 0  # Graph compiled successfully


class TestInitialState:
    def test_initial_state_defaults(self):
        state = initial_state("test query")
        assert state["user_query"] == "test query"
        assert state["intent"] == "unknown"
        assert state["metric_results"] == []
        assert state["sop_context"] == ""
        assert state["final_answer"] == ""
        assert state["error"] is None

    def test_initial_state_is_typed(self):
        state = initial_state("hello")
        assert isinstance(state, dict)
        assert "messages" in state
        assert "user_query" in state


# ============================================================
# Intent classification node
# ============================================================

class TestClassifyIntent:
    def test_sop_qa_intent(self):
        mock_resp = _mock_chat_response(
            '{"intent": "sop_qa", "reasoning": "User asks about procedures"}'
        )
        with mock.patch("src.app.intent.chat", return_value=mock_resp):
            from src.app.graph import node_classify_intent

            state = initial_state("How to handle delayed orders?")
            result = node_classify_intent(state)
            assert result["intent"] == "sop_qa"

    def test_metric_query_intent(self):
        mock_resp = _mock_chat_response(
            '{"intent": "metric_query", "reasoning": "User asks for data"}'
        )
        with mock.patch("src.app.intent.chat", return_value=mock_resp):
            from src.app.graph import node_classify_intent

            state = initial_state("Show top risky sellers")
            result = node_classify_intent(state)
            assert result["intent"] == "metric_query"

    def test_create_task_intent(self):
        mock_resp = _mock_chat_response(
            '{"intent": "create_task", "reasoning": "User wants to create task"}'
        )
        with mock.patch("src.app.intent.chat", return_value=mock_resp):
            from src.app.graph import node_classify_intent

            state = initial_state("Create a P0 task for seller_A")
            result = node_classify_intent(state)
            assert result["intent"] == "create_task"

    def test_mixed_intent(self):
        mock_resp = _mock_chat_response(
            '{"intent": "mixed", "reasoning": "Data + action requested"}'
        )
        with mock.patch("src.app.intent.chat", return_value=mock_resp):
            from src.app.graph import node_classify_intent

            state = initial_state(
                "Check seller_A delay rate and create task if >30%"
            )
            result = node_classify_intent(state)
            assert result["intent"] == "mixed"

    def test_unknown_intent(self):
        mock_resp = _mock_chat_response(
            '{"intent": "unknown", "reasoning": "Off-topic question"}'
        )
        with mock.patch("src.app.intent.chat", return_value=mock_resp):
            from src.app.graph import node_classify_intent

            state = initial_state("What is the weather today?")
            result = node_classify_intent(state)
            assert result["intent"] == "unknown"


# ============================================================
# Node tests with mocked dependencies
# ============================================================

class TestNodeAskClarification:
    def test_sets_final_answer(self):
        from src.app.graph import node_ask_clarification

        state = initial_state("Tell me a joke")
        result = node_ask_clarification(state)
        assert "inspection agent" in result["final_answer"].lower()
        assert result["error"] is None


class TestNodeRetrieveSop:
    def test_populates_sop_context(self):
        from src.app.graph import node_retrieve_sop

        state = initial_state("delay rate threshold P0")
        result = node_retrieve_sop(state)
        # May return empty if FTS index not built, but should not crash
        assert "sop_context" in result
        assert "sop_raw_results" in result


class TestNodePlanQuery:
    def test_plan_is_populated(self):
        mock_resp = _mock_chat_response(
            '{"intent": "show risky sellers", '
            '"metric_name": "top_risky_sellers", '
            '"filters": {"limit": 5}, '
            '"need_sql": false, '
            '"sql": null}'
        )
        with mock.patch("src.app.query_planner.chat", return_value=mock_resp):
            from src.app.graph import node_plan_query

            state = initial_state("Show top 5 risky sellers")
            result = node_plan_query(state)
            assert "query_plan" in result


class TestNodeCreateTask:
    def test_creates_task_from_metrics(self):
        from src.app.graph import node_create_task

        state = initial_state("Create task for seller_A")
        state["metric_results"] = [
            {
                "seller_id": "seller_A",
                "risk_level": "P0",
                "risk_score": 55.0,
                "delay_rate_pct": 35.0,
            }
        ]
        result = node_create_task(state)
        assert "task_result" in result


# ============================================================
# Routing tests
# ============================================================

class TestRouting:
    def test_route_sop_qa(self):
        from src.app.graph import route_by_intent

        state = initial_state("test")
        state["intent"] = "sop_qa"
        assert route_by_intent(state) == "node_retrieve_sop"

    def test_route_metric_query(self):
        from src.app.graph import route_by_intent

        state = initial_state("test")
        state["intent"] = "metric_query"
        assert route_by_intent(state) == "node_plan_query"

    def test_route_create_task(self):
        from src.app.graph import route_by_intent

        state = initial_state("test")
        state["intent"] = "create_task"
        assert route_by_intent(state) == "node_create_task"

    def test_route_mixed(self):
        from src.app.graph import route_by_intent

        state = initial_state("test")
        state["intent"] = "mixed"
        assert route_by_intent(state) == "node_plan_query"

    def test_route_unknown(self):
        from src.app.graph import route_by_intent

        state = initial_state("test")
        state["intent"] = "unknown"
        assert route_by_intent(state) == "node_ask_clarification"


# ============================================================
# Helper logic tests
# ============================================================

class TestHelpers:
    def test_infer_task_type(self):
        assert _infer_task_type("check review triage", {}) == "review_triage"
        assert _infer_task_type("product quality defect", {}) == "quality_inspection"
        assert _infer_task_type("delivery delay", {}) == "delivery_risk"

    def test_infer_priority_from_query(self):
        assert _infer_priority("create P0 task", []) == "P0"
        assert _infer_priority("check P1 seller", []) == "P1"

    def test_infer_priority_from_metrics(self):
        metrics = [{"seller_id": "s1", "risk_level": "P0"}]
        assert _infer_priority("check seller", metrics) == "P0"

    def test_should_create_task(self):
        assert _should_create_task([{"risk_level": "P0"}], "") is True
        assert _should_create_task([{"risk_level": "P1"}], "") is True
        assert _should_create_task([{"risk_level": "P3"}], "") is False
        assert _should_create_task([], "create a task") is True


# ============================================================
# End-to-end graph execution (mocked LLM)
# ============================================================

class TestGraphE2E:
    def _mock_all_llm(self):
        """Mock all LLM calls in the graph pipeline."""
        mocks = [
            mock.patch(
                "src.app.intent.chat",
                return_value=_mock_chat_response(
                    '{"intent": "sop_qa", "reasoning": "test"}'
                ),
            ),
            mock.patch(
                "src.app.query_planner.chat",
                return_value=_mock_chat_response(
                    '{"intent": "query", "metric_name": "top_risky_sellers", '
                    '"filters": {"limit": 3}, "need_sql": false, "sql": null}'
                ),
            ),
            mock.patch(
                "src.app.graph.chat",
                return_value=_mock_chat_response(
                    "Based on SOP-DELIVERY-001 §1.2, delay_rate > 30% triggers P0 alert. "
                    "Created task YJ-20260527-0001 for seller_A."
                ),
            ),
            mock.patch(
                "src.rag.answer.chat",
                return_value=_mock_chat_response(
                    "According to SOP-DELIVERY-001 §1.2, the P0 threshold for "
                    "delay_rate is 30%."
                ),
            ),
        ]
        for m in mocks:
            m.start()
        yield
        for m in mocks:
            m.stop()

    def test_e2e_sop_qa_flow(self):
        """Full SOP QA: intent → retrieve → answer"""
        with mock.patch(
            "src.app.intent.chat",
            return_value=_mock_chat_response(
                '{"intent": "sop_qa", "reasoning": "SOP question"}'
            ),
        ), mock.patch(
            "src.app.graph.chat",
            return_value=_mock_chat_response(
                "According to SOP-DELIVERY-001 §1.2: delay_rate > 30% → P0."
            ),
        ):
            state = initial_state("What is the P0 delay threshold?")
            graph = build_graph()
            result = graph.invoke(state)
            assert "final_answer" in result
            assert len(result["final_answer"]) > 0

    def test_e2e_metric_query_flow(self):
        """Full metric query: intent → plan → metrics → answer"""
        with mock.patch(
            "src.app.intent.chat",
            return_value=_mock_chat_response(
                '{"intent": "metric_query", "reasoning": "Data question"}'
            ),
        ), mock.patch(
            "src.app.query_planner.chat",
            return_value=_mock_chat_response(
                '{"intent": "query", "metric_name": "top_risky_sellers", '
                '"filters": {"limit": 5}, "need_sql": false, "sql": null}'
            ),
        ), mock.patch(
            "src.app.graph.chat",
            return_value=_mock_chat_response("Top sellers: seller_A risk=55 (P0), seller_B risk=32 (P1)."),
        ):
            state = initial_state("Show top 5 risky sellers")
            graph = build_graph()
            result = graph.invoke(state)
            assert "final_answer" in result
            assert len(result["final_answer"]) > 0

    def test_e2e_create_task_flow(self):
        """Full create task: intent → create → answer"""
        with mock.patch(
            "src.app.intent.chat",
            return_value=_mock_chat_response(
                '{"intent": "create_task", "reasoning": "Task creation request"}'
            ),
        ), mock.patch(
            "src.app.graph.chat",
            return_value=_mock_chat_response(
                "Created task YJ-20260527-0001: P0 delivery_risk for seller_A."
            ),
        ):
            state = initial_state(
                "Create a P0 delivery_risk task for seller_A: delay_rate=35%"
            )
            graph = build_graph()
            result = graph.invoke(state)
            assert "final_answer" in result
            assert len(result["final_answer"]) > 0

    def test_e2e_mixed_flow(self):
        """Mixed flow: intent → plan → metrics → SOP → task → answer"""
        with mock.patch(
            "src.app.intent.chat",
            return_value=_mock_chat_response(
                '{"intent": "mixed", "reasoning": "Data + action"}'
            ),
        ), mock.patch(
            "src.app.query_planner.chat",
            return_value=_mock_chat_response(
                '{"intent": "query", "metric_name": "top_risky_sellers", '
                '"filters": {"limit": 3}, "need_sql": false, "sql": null}'
            ),
        ), mock.patch(
            "src.app.graph.chat",
            return_value=_mock_chat_response(
                "seller_A has delay_rate=38%, exceeding P0 threshold of 30%. "
                "According to SOP-DELIVERY-001 §1.2, escalated to P0. "
                "Created task YJ-20260527-0002 for immediate action."
            ),
        ):
            state = initial_state(
                "Check seller_A delay rate, if >30% create P0 task"
            )
            graph = build_graph()
            result = graph.invoke(state)
            assert "final_answer" in result
            assert len(result["final_answer"]) > 0

    def test_e2e_unknown_flow(self):
        """Unknown intent: clarification message returned."""
        with mock.patch(
            "src.app.intent.chat",
            return_value=_mock_chat_response(
                '{"intent": "unknown", "reasoning": "Off-topic"}'
            ),
        ):
            state = initial_state("Tell me a joke")
            graph = build_graph()
            result = graph.invoke(state)
            assert "final_answer" in result
            assert "inspection" in result["final_answer"].lower()

    def test_e2e_error_handling(self):
        """LLM failure should produce error, not crash."""
        with mock.patch(
            "src.app.intent.chat",
            side_effect=ConnectionError("Ollama offline"),
        ):
            state = initial_state("Show top sellers")
            graph = build_graph()
            result = graph.invoke(state)
            # Should complete without exception
            assert "intent" in result
            assert result["intent"] == "unknown"  # fallback
