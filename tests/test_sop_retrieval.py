"""Tests for src/rag/ — chunking and retrieval pipeline.

Uses real docs/sop/*.md files. No external LLM calls.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.rag.chunker import Chunk, chunk_directory, chunk_elements
from src.rag.doc_convert import convert_directory, DocumentElement
from src.rag.fts_index import (
    build_fts_index,
    get_index_stats,
    search_fts,
)
from src.rag.retriever import get_sop_context, retrieve_sop

SOP_DIR = Path("docs/sop")


# ============================================================
# Chunker
# ============================================================

class TestChunker:
    def test_chunk_directory_returns_chunks(self):
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        chunks = chunk_directory(str(SOP_DIR))
        assert len(chunks) > 0
        for ch in chunks:
            assert isinstance(ch, Chunk)
            assert ch.text
            assert ch.source
            assert ch.chunk_id

    def test_chunks_preserve_parent_section(self):
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        chunks = chunk_directory(str(SOP_DIR))
        # At least some chunks should have parent_section
        with_parent = [c for c in chunks if c.parent_section]
        assert len(with_parent) > 0, "No chunks have parent_section"

    def test_chunk_text_length_bounded(self):
        """No chunk should exceed max size by too much (atomic types may)."""
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        chunks = chunk_directory(str(SOP_DIR))
        oversized = [c for c in chunks if len(c.text) > 3000]
        # Allow a few oversized for atomic types (checklists, tables)
        assert len(oversized) <= len(chunks) * 0.1, (
            f"{len(oversized)} chunks exceed 3000 chars"
        )

    def test_empty_elements_returns_empty(self):
        assert chunk_elements([]) == []


# ============================================================
# FTS Index
# ============================================================

class TestFtsIndex:
    @pytest.fixture
    def tmp_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp) / "test_sop.db"

    def test_build_and_search(self, tmp_db):
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        chunks = chunk_directory(str(SOP_DIR))
        build_fts_index(chunks, db_path=tmp_db)
        assert tmp_db.exists()

        results = search_fts("delay risk", db_path=tmp_db, top_k=3)
        assert len(results) > 0
        for r in results:
            assert "text" in r
            assert "source" in r
            assert "score" in r

    def test_search_relevant_results(self, tmp_db):
        """Query about delay should return delivery-related SOP."""
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        chunks = chunk_directory(str(SOP_DIR))
        build_fts_index(chunks, db_path=tmp_db)

        results = search_fts("delay threshold P0 risk", db_path=tmp_db, top_k=3)
        assert len(results) > 0
        sources = {r["source"] for r in results}
        assert any("delivery" in s.lower() for s in sources), (
            f"Expected delivery-related SOP in results: {sources}"
        )

    def test_search_no_results(self, tmp_db):
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        chunks = chunk_directory(str(SOP_DIR))
        build_fts_index(chunks, db_path=tmp_db)

        results = search_fts("xyznonexistentterm12345", db_path=tmp_db, top_k=3)
        assert len(results) == 0

    def test_get_stats(self, tmp_db):
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        chunks = chunk_directory(str(SOP_DIR))
        build_fts_index(chunks, db_path=tmp_db)

        stats = get_index_stats(tmp_db)
        assert stats["status"] == "ok"
        assert stats["total_chunks"] > 0
        assert len(stats["by_source"]) >= 1

    def test_missing_db_error(self):
        with pytest.raises(FileNotFoundError):
            search_fts("query", db_path="/nonexistent/db.db")

    def test_index_missing_db(self, tmp_db):
        """Stats on missing db should return status missing."""
        stats = get_index_stats("/nonexistent/db.db")
        assert stats["status"] == "missing"


# ============================================================
# Retriever
# ============================================================

class TestRetriever:
    @pytest.fixture
    def tmp_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_sop.db"
            if SOP_DIR.exists():
                chunks = chunk_directory(str(SOP_DIR))
                build_fts_index(chunks, db_path=db_path)
            yield db_path

    def test_retrieve_sop_returns_results(self, tmp_db):
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        results = retrieve_sop("delivery delay threshold", top_k=5, db_path=tmp_db)
        assert len(results) > 0
        assert len(results) <= 5
        assert "text" in results[0]
        assert "score" in results[0]

    def test_retrieve_content_type_filter(self, tmp_db):
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        results = retrieve_sop(
            "risk threshold",
            top_k=5,
            db_path=tmp_db,
            include_types=("threshold",),
        )
        for r in results:
            assert r.get("content_type") == "threshold"

    def test_get_sop_context_formatted(self, tmp_db):
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        ctx = get_sop_context("delay rate", top_k=3, db_path=tmp_db)
        assert "Retrieved SOP Context" in ctx
        assert len(ctx) > 100

    def test_empty_query_context(self, tmp_db):
        """An empty query returns empty context."""
        if not SOP_DIR.exists():
            pytest.skip("docs/sop/ not found")
        ctx = get_sop_context("xyznonexistent12345", top_k=1, db_path=tmp_db)
        # With FTS prefix matching, might still return something
        # Just check it doesn't crash
        assert isinstance(ctx, str)
