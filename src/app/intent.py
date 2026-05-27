"""Intent classifier for YuanJiang OpsGuard.

Uses DeepSeek-R1 to classify user intent into one of:
  - sop_qa: Questions about SOP procedures
  - metric_query: Questions about seller/order/product metrics
  - create_task: Requests to create inspection tasks
  - mixed: Multi-step requests combining data + SOP + task creation
  - unknown: Off-topic or unclear requests
"""
from __future__ import annotations

import json
from typing import Any, Literal

from src.llm.ollama_client import chat
from src.llm.output_cleaner import extract_json_block, strip_think

Intent = Literal["sop_qa", "metric_query", "create_task", "mixed", "unknown"]

_INTENT_PROMPT = """Classify the user's intent for an e-commerce operations inspection agent.

## Intent categories:
- sop_qa: User asks about procedures, thresholds, or policies (e.g. "How to handle delayed orders?", "What is the P0 threshold?")
- metric_query: User asks for data or metrics (e.g. "Show top risky sellers", "What is seller_A's delay rate?")
- create_task: User wants to create or manage an inspection task (e.g. "Create a P0 task for seller_A", "List open tasks")
- mixed: User requests multiple things that may need data + SOP + task creation (e.g. "Check seller_A's delay rate, and if >30% create a P0 task")
- unknown: Off-topic, unclear, or cannot be handled (e.g. "What's the weather?")

## Rules:
- Default to "mixed" if the request spans multiple categories
- "mixed" is the right choice when data + action are combined
- Only use "unknown" for clearly off-topic requests

## Output format — JSON only:
{"intent": "<one of: sop_qa, metric_query, create_task, mixed, unknown>", "reasoning": "<1 sentence>"}
"""


def classify_intent(
    user_query: str,
    model: str | None = None,
) -> dict[str, str]:
    """Classify a user query into one of 5 intent categories.

    Args:
        user_query: The user's natural language request.
        model: Override the Ollama model.

    Returns:
        Dict with keys: intent (one of the 5 categories),
        reasoning (short explanation).
    """
    messages = [
        {"role": "user", "content": _INTENT_PROMPT + f"\n\nUser query: {user_query}"}
    ]

    try:
        response = chat(messages, temperature=0.0, model=model)
        raw = response.get("message", {}).get("content", "")
    except Exception:
        return {"intent": "unknown", "reasoning": "LLM call failed"}

    cleaned = strip_think(raw)
    result = extract_json_block(cleaned)

    if result is None:
        # Fallback: keyword-based classification
        return _fallback_classify(user_query)

    intent = result.get("intent", "unknown")
    if intent not in ("sop_qa", "metric_query", "create_task", "mixed", "unknown"):
        intent = "unknown"

    return {
        "intent": intent,
        "reasoning": result.get("reasoning", ""),
    }


def _fallback_classify(user_query: str) -> dict[str, str]:
    """Keyword-based fallback when LLM is unavailable."""
    q = user_query.lower()

    # Mixed patterns (data + action)
    mixed_patterns = [
        ("check" in q or "find" in q or "show" in q or "query" in q)
        and ("create" in q or "open" in q or "task" in q or "if" in q),
        "and then" in q,
        "if" in q and "create" in q,
    ]
    if any(mixed_patterns):
        return {"intent": "mixed", "reasoning": "fallback: data + action pattern detected"}

    # Create task patterns
    if any(w in q for w in ["create", "open task", "new task", "assign"]):
        return {"intent": "create_task", "reasoning": "fallback: task creation pattern"}

    # SOP patterns
    sop_keywords = ["how to", "procedure", "process", "sop", "threshold",
                     "policy", "should i", "what to do", "handle"]
    if any(w in q for w in sop_keywords):
        return {"intent": "sop_qa", "reasoning": "fallback: SOP keyword match"}

    # Metric patterns
    metric_keywords = ["show", "list", "top", "rate", "score", "metric",
                        "seller", "order", "delay", "review", "cancel"]
    if any(w in q for w in metric_keywords):
        return {"intent": "metric_query", "reasoning": "fallback: metric keyword match"}

    return {"intent": "unknown", "reasoning": "fallback: no pattern matched"}
