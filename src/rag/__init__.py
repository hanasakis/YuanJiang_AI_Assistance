"""rag — Document conversion, chunking, hybrid retrieval, and SOP-grounded QA.

Responsibilities:
- Convert SOP documents (PDF/Markdown) to text via Docling / PyMuPDF4LLM
- Semantic chunking with section-aware boundaries
- Hybrid retrieval: FTS (SQLite FTS5) + BM25 + optional vector
- Assemble retrieved SOP context for LLM grounding

Retrieval: local-only, no external embedding API.
"""

__all__: list[str] = []
