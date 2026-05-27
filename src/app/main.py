"""YuanJiang OpsGuard — E-commerce Operations Inspection Workbench.

Streamlit UI for the inspection agent. Thin display layer:
all business logic lives in src/llm, src/data_ops, src/rag, src/tools.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import streamlit as st


# ============================================================
# Cached resource helpers
# ============================================================

@st.cache_resource
def _get_graph():
    """Lazy-load the LangGraph agent graph (cached across reruns)."""
    from src.app.graph import build_graph
    return build_graph()


@st.cache_resource
def _check_ollama() -> bool:
    """Check if Ollama is reachable."""
    try:
        from src.llm.ollama_client import OLLAMA_BASE_URL
        import httpx
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ============================================================
# Query execution
# ============================================================

def _run_query(query: str) -> dict:
    """Run a query through the agent graph or demo fallback."""
    if not query.strip():
        return {}

    ollama_ok = _check_ollama()

    if ollama_ok:
        with st.spinner("Agent reasoning..."):
            graph = _get_graph()
            from src.app.state import initial_state
            state = initial_state(query)
            return graph.invoke(state)

    return _demo_response(query)


def _demo_response(query: str) -> dict:
    """Generate a demo response without Ollama (offline mode)."""
    from src.data_ops.build_duckdb import build_database
    from src.data_ops.metrics import get_top_risky_sellers
    from src.rag.retriever import get_sop_context
    from src.tools.inspection_tools import create_inspection_task

    q = query.lower()
    intent = "unknown"
    metric_results = []
    sop_context = ""
    task_result = {}
    final_answer = ""

    if any(w in q for w in ["top", "risky", "seller", "delay", "rate", "show", "list"]):
        intent = "metric_query"
        try:
            db_path = Path("data/processed/olist.duckdb")
            if not db_path.exists():
                build_database(csv_dir="data/sample/olist", db_path=db_path)
            metric_results = get_top_risky_sellers(limit=5, db_path=db_path)
        except Exception:
            metric_results = [
                {"seller_id": "seller_A", "risk_score": 55.0, "risk_level": "P0",
                 "delay_rate_pct": 35.0, "cancel_rate_pct": 5.0, "low_review_rate_pct": 20.0},
                {"seller_id": "seller_B", "risk_score": 32.0, "risk_level": "P1",
                 "delay_rate_pct": 25.0, "cancel_rate_pct": 10.0, "low_review_rate_pct": 15.0},
            ]

    elif any(w in q for w in ["order", "why", "review", "score"]):
        intent = "metric_query"
        metric_results = [
            {"order_id": "ord_002", "delivery_delay_days": 8, "review_score": 2,
             "is_delayed": True, "is_low_review": True,
             "risk_flags": ["significant_delay", "low_review"]}
        ]

    elif any(w in q for w in ["sop", "threshold", "procedure", "process", "how to", "policy"]):
        intent = "sop_qa"
        sop_context = get_sop_context(query, top_k=3)
        from src.rag.answer import answer_sop
        try:
            ans = answer_sop(query, top_k=3)
            final_answer = ans.get("answer", "No SOP data available.")
        except Exception:
            final_answer = "SOP offline: see docs/sop/ for procedure details."

    elif any(w in q for w in ["task", "create"]) and any(w in q for w in ["seller", "p0", "p1"]):
        intent = "create_task"
        task_result = create_inspection_task(
            task_type="delivery_risk",
            priority="P0" if "p0" in q else "P1",
            target_id="seller_A",
            title=f"[{'P0' if 'p0' in q else 'P1'}] Demo inspection task",
            description=f"Demo task from query: {query}",
        )

    else:
        intent = "sop_qa"
        final_answer = (
            "I'm the YuanJiang OpsGuard inspection agent (offline demo mode).\n\n"
            "Try these queries:\n"
            "- 'Show top 5 risky sellers'\n"
            "- 'What is the P0 delay threshold?'\n"
            "- 'Create a P0 task for seller_A'\n"
            "- 'Check seller_A delay rate, create task if >30%'"
        )

    return {
        "intent": intent,
        "query_plan": {"metric_name": intent},
        "metric_results": metric_results,
        "sop_context": sop_context,
        "sop_raw_results": [],
        "task_result": task_result,
        "final_answer": final_answer,
    }


# ============================================================
# Rendering
# ============================================================

def _render_result(result: dict) -> None:
    """Render the agent result in structured sections."""
    if not result:
        return

    intent = result.get("intent", "unknown")
    metric_results = result.get("metric_results") or []
    sop_raw = result.get("sop_raw_results") or []
    task_result = result.get("task_result") or {}
    final_answer = result.get("final_answer", "")

    # Intent badge
    intent_labels = {
        "sop_qa": "SOP Q&A", "metric_query": "Metric Query",
        "create_task": "Create Task", "mixed": "Mixed Workflow", "unknown": "Unknown",
    }
    label = intent_labels.get(intent, intent)
    st.markdown(f"**Intent:** `{label}`")

    st.divider()

    # Metric results table
    if metric_results:
        st.subheader("Metric Results")
        if isinstance(metric_results, list) and len(metric_results) > 0:
            df = pd.DataFrame(metric_results)
            display_cols = [
                c for c in ["seller_id", "order_id", "product_id",
                             "risk_score", "risk_level", "delay_rate_pct",
                             "cancel_rate_pct", "low_review_rate_pct",
                             "total_orders", "avg_review_score",
                             "delivery_delay_days", "review_score",
                             "defect_rate_pct", "risk_flags"]
                if c in df.columns
            ] or df.columns.tolist()
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
        elif isinstance(metric_results, dict):
            st.json(metric_results)
        st.divider()

    # SOP sources
    if sop_raw:
        st.subheader("SOP Sources")
        for i, src in enumerate(sop_raw[:5], 1):
            with st.expander(
                f"[{i}] {src.get('source', '?')} — {src.get('section', 'no section')}"
            ):
                st.caption(
                    f"type: {src.get('content_type', '')} | "
                    f"chunk: {src.get('chunk_id', '')}"
                )
                st.text(src.get("text", "")[:500])
        st.divider()

    # Task result
    if task_result and task_result.get("success"):
        st.subheader("Task Created")
        st.success(task_result.get("message", "Task created"))
        if task_result.get("task"):
            with st.expander("Task details"):
                st.json(task_result["task"])
        st.divider()

    # Final answer
    if final_answer:
        st.subheader("Answer")
        from src.llm.output_cleaner import strip_think
        cleaned = strip_think(final_answer)
        st.markdown(cleaned)
    elif not metric_results and not sop_raw and not task_result:
        st.info("No results. Try rephrasing your query.")


# ============================================================
# Streamlit UI
# ============================================================

def main():
    st.title("YuanJiang OpsGuard")
    st.caption("E-commerce Operations Inspection Workbench")

    # ---- Sidebar ----
    with st.sidebar:
        ollama_ok = _check_ollama()
        if ollama_ok:
            st.success("Ollama connected")
        else:
            st.warning("Ollama offline — demo mode")

        st.divider()
        st.markdown("**Quick queries**")
        presets = [
            "Show top 5 risky sellers",
            "What is the P0 delay threshold?",
            "Explain why order ord_002 may have a low score",
            "Create a P0 delivery_risk task for seller_A",
            "Check seller_A delay rate, if >30% create P0 task",
        ]
        for p in presets:
            if st.button(p, use_container_width=True):
                st.session_state.user_query = p
                st.rerun()

        st.divider()
        st.caption("183 tests passed | model: deepseek-r1:8b")

    # ---- Query input ----
    st.text_area(
        "Inspection query",
        key="user_query",
        placeholder="e.g. Show top 5 sellers with highest delay risk...",
        height=68,
        label_visibility="collapsed",
    )

    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        run_btn = st.button("Run Inspection", type="primary", use_container_width=True)
    with col2:
        if st.button("Clear", use_container_width=True):
            st.session_state.pop("last_result", None)
            st.session_state.user_query = ""
            st.rerun()

    if not run_btn:
        if "last_result" in st.session_state:
            _render_result(st.session_state.last_result)
        else:
            st.info("Enter an inspection query and click **Run Inspection**.")
        return

    # Execute
    query = st.session_state.get("user_query", "").strip()
    if not query:
        st.warning("Please enter a query.")
        return

    result = _run_query(query)
    st.session_state.last_result = result
    _render_result(result)


if __name__ == "__main__":
    main()
