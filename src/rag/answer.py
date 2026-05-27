"""Grounded SOP answer generation using local DeepSeek-R1.

Takes a user question + retrieved SOP context, calls DeepSeek-R1,
and returns an answer with mandatory source citations.
Refuses to answer when no relevant context is found.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.llm.ollama_client import chat
from src.llm.output_cleaner import strip_think
from src.rag.retriever import get_sop_context

_DEFAULT_DB = Path("data/fts/sop_index.db")

_ANSWER_PROMPT = """You are YuanJiang OpsGuard SOP assistant.
Answer the user's question using ONLY the SOP context provided below.
If the context does not contain relevant information, respond with:
"NO_EVIDENCE: The available SOP documents do not contain information about this."

## Rules
1. Every claim MUST cite the source and section (e.g., [source: SOP-DELIVERY-001, section: 风险等级判定]).
2. If thresholds or numbers are cited, quote them exactly — do not paraphrase.
3. If the context describes a multi-step procedure, list the steps in order.
4. If multiple SOPs apply, mention all relevant ones.
5. If the context is insufficient, respond with NO_EVIDENCE — never fabricate.

## SOP Context
{context}

## User Question
{question}

## Answer (with sources):"""


def answer_sop(
    question: str,
    top_k: int = 5,
    db_path: str | Path = _DEFAULT_DB,
    model: str | None = None,
    temperature: float = 0.1,
) -> dict[str, Any]:
    """Answer an SOP question using retrieved context + DeepSeek-R1.

    Args:
        question: User's natural language question.
        top_k: Number of SOP chunks to retrieve as context.
        db_path: Path to FTS5 index.
        model: Override the Ollama model name.
        temperature: LLM sampling temperature.

    Returns:
        Dict with keys:
          - question: original question
          - answer: grounded answer with citations, or NO_EVIDENCE block
          - sources: list of source dicts used
          - refused: True if NO_EVIDENCE was returned
          - model: name of model used
    """
    # Step 1: Retrieve relevant SOP context
    context = get_sop_context(question, top_k=top_k, db_path=db_path)

    if not context:
        return {
            "question": question,
            "answer": "NO_EVIDENCE: No SOP documents are indexed. "
                      "Add documents to docs/sop/ and rebuild the FTS index.",
            "sources": [],
            "refused": True,
            "model": model or "deepseek-r1:8b",
        }

    # Step 2: Build prompt with retrieved context
    prompt = _ANSWER_PROMPT.format(context=context, question=question)
    messages = [{"role": "user", "content": prompt}]

    # Step 3: Call DeepSeek-R1
    try:
        response = chat(messages, temperature=temperature, model=model)
        raw = response.get("message", {}).get("content", "")
    except Exception as exc:
        return {
            "question": question,
            "answer": f"ERROR: LLM call failed: {exc}",
            "sources": [],
            "refused": True,
            "model": model or "deepseek-r1:8b",
        }

    # Step 4: Clean R1 output
    cleaned = strip_think(raw)

    # Step 5: Check for refusal
    refused = cleaned.strip().upper().startswith("NO_EVIDENCE")

    # Step 6: Re-retrieve sources for provenance
    from src.rag.retriever import retrieve_sop

    retrieved = retrieve_sop(question, top_k=top_k, db_path=db_path)
    sources = [
        {
            "source": r["source"],
            "section": r["section"],
            "content_type": r["content_type"],
            "chunk_id": r["chunk_id"],
        }
        for r in retrieved
    ]

    return {
        "question": question,
        "answer": cleaned.strip(),
        "sources": sources,
        "refused": refused,
        "model": model or "deepseek-r1:8b",
    }
