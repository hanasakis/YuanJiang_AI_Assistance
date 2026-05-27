"""SOP retriever — keyword search + content-type-aware ranking.

Provides retrieve_sop(query, top_k) as the single entry point for
finding relevant SOP chunks.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.rag.chunker import Chunk, chunk_directory
from src.rag.fts_index import build_fts_index, search_fts

_DEFAULT_DB = Path("data/fts/sop_index.db")


def retrieve_sop(
    query: str,
    top_k: int = 5,
    db_path: str | Path = _DEFAULT_DB,
    include_types: tuple[str, ...] = (),
    prefer_sections: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Retrieve relevant SOP chunks for a natural language query.

    Strategy:
    1. FTS5 BM25 keyword search → candidate pool
    2. Boost results matching prefer_sections
    3. Return top_k results with full metadata

    Args:
        query: Natural language question about SOP procedures.
        top_k: Number of results to return.
        db_path: Path to FTS5 index.
        include_types: Optional content_type filter.
        prefer_sections: Boost results from these sections.

    Returns:
        List of result dicts with text, source, section, content_type,
        chunk_id, score.
    """
    db_path = Path(db_path)

    # Auto-build index if needed
    if not db_path.exists():
        chunks = chunk_directory("docs/sop")
        if not chunks:
            return []
        build_fts_index(chunks, db_path=db_path)

    # Get more candidates than needed for reranking
    candidates = search_fts(query, db_path=db_path, top_k=top_k * 3)

    # Apply content type filter if specified
    if include_types:
        candidates = [
            c for c in candidates
            if c.get("content_type", "") in include_types
        ]

    # Boost results whose section matches prefer_sections
    if prefer_sections:
        for c in candidates:
            section = c.get("section", "").lower()
            boost = 0.0
            for pref in prefer_sections:
                if pref.lower() in section:
                    boost += 0.5
            # FTS score is lower = better, so subtract boost
            c["score"] = max(0.0, float(c["score"]) - boost)

        candidates.sort(key=lambda x: float(x["score"]))

    return candidates[:top_k]


def get_sop_context(
    query: str,
    top_k: int = 5,
    db_path: str | Path = _DEFAULT_DB,
) -> str:
    """Retrieve SOP context as a formatted string for LLM prompting.

    Args:
        query: User question.
        top_k: Number of chunks to retrieve.
        db_path: Path to FTS5 index.

    Returns:
        Formatted string with numbered SOP citations.
    """
    results = retrieve_sop(query, top_k=top_k, db_path=db_path)

    if not results:
        return ""

    lines = ["## Retrieved SOP Context\n"]
    for i, r in enumerate(results, 1):
        source = r.get("source", "unknown")
        section = r.get("section", "")
        ctype = r.get("content_type", "")
        label = f"source={source}"
        if section:
            label += f", section={section}"
        if ctype:
            label += f", type={ctype}"

        lines.append(f"### [{i}] {label}")
        lines.append(r.get("text", ""))
        lines.append("")

    return "\n".join(lines)
