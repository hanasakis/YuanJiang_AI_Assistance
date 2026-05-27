"""LangGraph workflow for YuanJiang OpsGuard inspection agent.

Graph structure:

    classify_intent
        ├── sop_qa ─────→ retrieve_sop ────→ final_answer
        ├── metric_query → plan → run_metric → final_answer
        ├── create_task ─→ create_task ──────→ final_answer
        ├── mixed ───────→ plan → run_metric → retrieve_sop
        │                   → conditional_create → final_answer
        └── unknown ─────→ ask_clarification → final_answer

Each node is a pure function: (AgentState) → partial AgentState.
LangGraph handles state merging and edge routing.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.app.intent import classify_intent
from src.app.query_planner import execute_plan, plan_query
from src.app.state import AgentState, initial_state
from src.data_ops.metrics import get_top_risky_sellers
from src.llm.ollama_client import chat
from src.llm.output_cleaner import strip_think
from src.rag.answer import answer_sop
from src.rag.retriever import get_sop_context, retrieve_sop
from src.tools.inspection_tools import (
    close_inspection_task,
    create_inspection_task,
    list_inspection_tasks,
)
from src.tools.schemas import InspectionTaskCreate

# ============================================================
# Node implementations
# ============================================================

_FINAL_PROMPT = """You are YuanJiang OpsGuard. Answer the user's question
based on the data and context provided below. Be concise and actionable.

## User Question
{question}

## Intent
{intent}

## Metric Results (if any)
{metrics}

## SOP Context (if any)
{sop}

## Task Result (if any)
{task}

## Instructions
- Synthesize all available information into a clear answer
- Cite SOP sources and data values
- If a task was created, mention the task ID
- Never mention <think> tags or internal processing
- If you lack information, say so honestly
"""


def node_classify_intent(state: AgentState) -> dict[str, Any]:
    """Classify user intent and set routing."""
    query = state.get("user_query", "")
    result = classify_intent(query)
    return {
        "intent": result["intent"],
        "messages": [{"role": "system", "content": f"intent={result['intent']}"}],
    }


def node_plan_query(state: AgentState) -> dict[str, Any]:
    """Convert natural language to structured query plan."""
    query = state.get("user_query", "")
    try:
        plan = plan_query(query)
    except Exception as exc:
        return {"error": f"Query planning failed: {exc}", "query_plan": {}}
    return {"query_plan": plan, "error": plan.get("error")}


def node_run_metric_tool(state: AgentState) -> dict[str, Any]:
    """Execute the query plan and collect metric results."""
    plan = state.get("query_plan", {})
    if not plan or plan.get("error"):
        return {"metric_results": [], "error": plan.get("error", "No query plan")}

    try:
        result = execute_plan(plan)
    except Exception as exc:
        return {"metric_results": [], "error": f"Metric execution failed: {exc}"}

    results = result.get("results", [])
    if isinstance(results, dict):
        results = [results]
    elif results is None:
        results = []

    return {
        "metric_results": results,
        "error": result.get("error"),
    }


def node_retrieve_sop(state: AgentState) -> dict[str, Any]:
    """Retrieve relevant SOP context for the user query."""
    query = state.get("user_query", "")
    ctx = get_sop_context(query, top_k=5)
    raw = retrieve_sop(query, top_k=5)
    return {"sop_context": ctx, "sop_raw_results": raw}


def node_create_task(state: AgentState) -> dict[str, Any]:
    """Create inspection task based on query and metric results."""
    query = state.get("user_query", "")
    metrics = state.get("metric_results", [])
    plan = state.get("query_plan", {})

    # Determine task parameters from query + results
    task_type = _infer_task_type(query, plan)
    priority = _infer_priority(query, metrics)
    target_id = _infer_target(query, metrics)
    title = f"[{priority}] Inspection for {target_id}"
    description = _build_task_description(query, metrics, state.get("sop_context", ""))

    try:
        result = create_inspection_task(
            task_type=task_type,
            priority=priority,
            target_id=target_id,
            title=title,
            description=description,
        )
    except Exception as exc:
        return {"task_result": {"success": False, "message": str(exc)}}

    return {"task_result": result}


def node_ask_clarification(state: AgentState) -> dict[str, Any]:
    """Generate a clarification request for unknown/unclear queries."""
    query = state.get("user_query", "")
    return {
        "final_answer": (
            "I'm an e-commerce operations inspection agent. I can help you with:\n\n"
            "1. **Data queries**: 'Show top 5 risky sellers', 'What is seller_A's delay rate?'\n"
            "2. **SOP questions**: 'How to handle delayed orders?', 'What is the P0 threshold?'\n"
            "3. **Task creation**: 'Create a P0 task for seller_A'\n"
            "4. **Mixed workflows**: 'Check seller_A's delay rate, create a task if >30%'\n\n"
            f"Your query: '{query}'\n"
            "Could you rephrase it in terms of seller risk, order quality, "
            "or SOP procedures?"
        ),
        "error": None,
    }


def node_final_answer(state: AgentState) -> dict[str, Any]:
    """Synthesize final answer from all collected data."""
    # If clarification was already set, keep it
    if state.get("final_answer"):
        return {}

    intent = state.get("intent", "unknown")
    metrics = state.get("metric_results", [])
    sop = state.get("sop_context", "")
    task = state.get("task_result", {})
    query = state.get("user_query", "")
    error = state.get("error")

    if error:
        return {
            "final_answer": f"An error occurred: {error}\n\n"
                            "Please check your query and try again."
        }

    # For simple SOP QA, use the grounded answer pipeline
    if intent == "sop_qa" and not metrics and not task:
        try:
            result = answer_sop(query, top_k=5)
            return {"final_answer": result.get("answer", "No SOP context found.")}
        except Exception:
            pass

    # For mixed / metric flows, call LLM to synthesize
    prompt = _FINAL_PROMPT.format(
        question=query,
        intent=intent,
        metrics=_format_metrics(metrics),
        sop=sop if sop else "(none)",
        task=_format_task(task),
    )

    try:
        response = chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        raw = response.get("message", {}).get("content", "")
        cleaned = strip_think(raw)
    except Exception:
        cleaned = _build_fallback_answer(intent, metrics, sop, task)

    return {"final_answer": cleaned}


# ============================================================
# Routing
# ============================================================

def route_by_intent(state: AgentState) -> str:
    """Route to the appropriate node based on classified intent."""
    intent = state.get("intent", "unknown")
    routes = {
        "sop_qa": "node_retrieve_sop",
        "metric_query": "node_plan_query",
        "create_task": "node_create_task",
        "mixed": "node_plan_query",
        "unknown": "node_ask_clarification",
    }
    return routes.get(intent, "node_ask_clarification")


def route_after_plan(state: AgentState) -> str:
    """After query planning, route to metric execution."""
    if state.get("error"):
        return "node_final_answer"
    return "node_run_metric_tool"


def route_after_metrics(state: AgentState) -> str:
    """After metric execution, decide next step based on intent."""
    intent = state.get("intent", "unknown")
    if state.get("error"):
        return "node_final_answer"
    if intent == "mixed":
        return "node_retrieve_sop"  # mixed: get SOP context after data
    return "node_final_answer"


def route_after_sop(state: AgentState) -> str:
    """After SOP retrieval, decide next step for mixed flows."""
    intent = state.get("intent", "unknown")
    if intent == "mixed":
        # Check if we should create a task
        metrics = state.get("metric_results", [])
        if _should_create_task(metrics, state.get("user_query", "")):
            return "node_create_task"
    return "node_final_answer"


def route_after_task(state: AgentState) -> str:
    """After task creation, route to final answer."""
    return "node_final_answer"


# ============================================================
# Graph construction
# ============================================================

def build_graph() -> StateGraph:
    """Build and return the YuanJiang OpsGuard LangGraph StateGraph.

    Returns:
        A compiled StateGraph ready for invocation.
    """
    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("node_classify_intent", node_classify_intent)
    builder.add_node("node_plan_query", node_plan_query)
    builder.add_node("node_run_metric_tool", node_run_metric_tool)
    builder.add_node("node_retrieve_sop", node_retrieve_sop)
    builder.add_node("node_create_task", node_create_task)
    builder.add_node("node_ask_clarification", node_ask_clarification)
    builder.add_node("node_final_answer", node_final_answer)

    # Set entry point
    builder.set_entry_point("node_classify_intent")

    # Conditional routing from classify_intent
    builder.add_conditional_edges(
        "node_classify_intent",
        route_by_intent,
        {
            "node_retrieve_sop": "node_retrieve_sop",
            "node_plan_query": "node_plan_query",
            "node_create_task": "node_create_task",
            "node_ask_clarification": "node_ask_clarification",
        },
    )

    # After plan → run metric
    builder.add_conditional_edges(
        "node_plan_query",
        route_after_plan,
        {
            "node_run_metric_tool": "node_run_metric_tool",
            "node_final_answer": "node_final_answer",
        },
    )

    # After metric → SOP (mixed) or final
    builder.add_conditional_edges(
        "node_run_metric_tool",
        route_after_metrics,
        {
            "node_retrieve_sop": "node_retrieve_sop",
            "node_final_answer": "node_final_answer",
        },
    )

    # After SOP → task (mixed) or final
    builder.add_conditional_edges(
        "node_retrieve_sop",
        route_after_sop,
        {
            "node_create_task": "node_create_task",
            "node_final_answer": "node_final_answer",
        },
    )

    # Terminal edges
    builder.add_edge("node_create_task", "node_final_answer")
    builder.add_edge("node_ask_clarification", END)
    builder.add_edge("node_final_answer", END)

    return builder.compile()


# ============================================================
# Convenience runner
# ============================================================

def run_agent(user_query: str) -> AgentState:
    """Run a single user query through the agent graph.

    Args:
        user_query: Natural language request.

    Returns:
        Final AgentState with final_answer populated.
    """
    graph = build_graph()
    state = initial_state(user_query)
    result = graph.invoke(state)
    return result


# ============================================================
# Internal helpers
# ============================================================

def _infer_task_type(query: str, plan: dict) -> str:
    q = query.lower() + " " + str(plan).lower()
    if "review" in q or "triage" in q:
        return "review_triage"
    if "quality" in q or "product" in q or "defect" in q:
        return "quality_inspection"
    return "delivery_risk"


def _infer_priority(query: str, metrics: list[dict]) -> str:
    q = query.lower()
    if "p0" in q:
        return "P0"
    if "p1" in q:
        return "P1"
    if "p2" in q:
        return "P2"
    if "p3" in q:
        return "P3"
    # Infer from metric risk_level
    for m in metrics:
        if isinstance(m, dict) and m.get("risk_level") in ("P0", "P1", "P2", "P3"):
            return m["risk_level"]
    return "P2"


def _infer_target(query: str, metrics: list[dict]) -> str:
    # Try to extract seller_id from metrics
    for m in metrics:
        if isinstance(m, dict):
            if "seller_id" in m:
                return m["seller_id"]
            if "product_id" in m:
                return m["product_id"]
            if "order_id" in m:
                return m["order_id"]
    # Fallback: use query as target hint
    return "unknown_target"


def _should_create_task(metrics: list[dict], query: str) -> bool:
    q = query.lower()
    if "create" in q or "task" in q or "open" in q:
        return True
    for m in metrics:
        if isinstance(m, dict) and m.get("risk_level") in ("P0", "P1"):
            return True
    return False


def _build_task_description(
    query: str, metrics: list[dict], sop: str
) -> str:
    parts = [f"Auto-generated from query: {query}"]
    if metrics:
        parts.append("Metric findings:")
        for m in metrics[:3]:
            if isinstance(m, dict):
                parts.append(f"  - {json.dumps(m, default=str)[:300]}")
    if sop:
        parts.append(f"SOP context available ({len(sop)} chars)")
    return "\n".join(parts)


def _format_metrics(metrics: list[dict]) -> str:
    if not metrics:
        return "(no metric data)"
    try:
        return json.dumps(metrics, indent=2, default=str, ensure_ascii=False)[:3000]
    except Exception:
        return str(metrics)[:3000]


def _format_task(task: dict) -> str:
    if not task:
        return "(no task created)"
    return json.dumps(task, indent=2, default=str, ensure_ascii=False)[:1000]


def _build_fallback_answer(
    intent: str, metrics: list[dict], sop: str, task: dict
) -> str:
    """Build a structured answer without LLM (offline fallback)."""
    lines = []
    if metrics:
        lines.append("## Metric Results\n")
        for m in metrics[:5]:
            if isinstance(m, dict):
                lines.append(
                    f"- {m.get('seller_id', m.get('product_id', '?'))}: "
                    f"risk={m.get('risk_score', '?')} "
                    f"({m.get('risk_level', '?')})"
                )
        lines.append("")
    if task.get("success"):
        lines.append(f"## Task Created\n- {task.get('message', 'Task created')}")
        lines.append("")
    if sop:
        lines.append("## SOP Context Available\n")
        lines.append(sop[:500])
    if not lines:
        lines.append(f"Processed intent '{intent}' but no results found.")
    return "\n".join(lines)
