"""AgentState for YuanJiang OpsGuard LangGraph workflow.

Defines the shared state dictionary that flows through every node
in the inspection agent graph.
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Shared state carried through the LangGraph workflow.

    Each node reads from and writes to this dict. LangGraph merges
    node return values into the state automatically.

    Fields:
        messages: Conversation history (auto-merged by add_messages).
        user_query: The current natural language request from the user.
        intent: Classified intent: sop_qa | metric_query | create_task | mixed | unknown.
        query_plan: JSON plan from query_planner.plan_query().
        metric_results: Results from executing the query plan.
        sop_context: Retrieved SOP chunks as formatted text.
        sop_raw_results: Raw retrieval results (list of dicts).
        task_result: Result from create/close task operations.
        final_answer: The final response shown to the user.
        error: Error message if any step fails.
        next_action: Internal routing flag for mixed flows.
    """

    messages: Annotated[list, add_messages]
    user_query: str
    intent: str
    query_plan: dict[str, Any]
    metric_results: list[dict[str, Any]]
    sop_context: str
    sop_raw_results: list[dict[str, Any]]
    task_result: dict[str, Any]
    final_answer: str
    error: str | None
    next_action: str  # internal routing: "route" | "done"


def initial_state(user_query: str) -> AgentState:
    """Create a fresh AgentState for a new user query.

    Args:
        user_query: The natural language request.

    Returns:
        AgentState with defaults and empty fields.
    """
    return AgentState(
        messages=[],
        user_query=user_query,
        intent="unknown",
        query_plan={},
        metric_results=[],
        sop_context="",
        sop_raw_results=[],
        task_result={},
        final_answer="",
        error=None,
        next_action="route",
    )
