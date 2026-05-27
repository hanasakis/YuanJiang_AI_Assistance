"""Tests for src/rag/answer.py — grounded SOP answer generation.

These tests validate the answer pipeline WITHOUT calling the real Ollama
server. We test the answer structure, refusal logic, and source tracking.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.rag.answer import _ANSWER_PROMPT, answer_sop
from src.rag.chunker import chunk_directory
from src.rag.fts_index import build_fts_index

SOP_DIR = Path("docs/sop")


@pytest.fixture
def indexed_db():
    """Build a temp FTS index from real SOP files."""
    if not SOP_DIR.exists():
        pytest.skip("docs/sop/ not found")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_sop.db"
        chunks = chunk_directory(str(SOP_DIR))
        build_fts_index(chunks, db_path=db_path)
        yield db_path


class TestAnswerPrompt:
    def test_prompt_contains_required_sections(self):
        assert "NO_EVIDENCE" in _ANSWER_PROMPT
        assert "source" in _ANSWER_PROMPT.lower()
        assert "{context}" in _ANSWER_PROMPT
        assert "{question}" in _ANSWER_PROMPT
        assert "fabricate" in _ANSWER_PROMPT.lower() or "never" in _ANSWER_PROMPT.lower()


class TestAnswerSop:
    def test_answer_without_ollama_returns_sources(self, indexed_db):
        """Even without Ollama, answer_sop retrieves sources."""
        # Mock chat to avoid real LLM call
        mock_response = {
            "message": {
                "content": (
                    "<think>Checking SOP-DELIVERY-001 for delay thresholds</think>\n"
                    "According to SOP-DELIVERY-001 [source: docs/sop/seller_delivery_risk.md, "
                    "section: 风险等级判定], delay_rate > 30% triggers P0 critical alert. "
                    "For 15%-30%, it is P1 important."
                )
            }
        }

        with mock.patch("src.rag.answer.chat", return_value=mock_response):
            result = answer_sop(
                "What is the delay threshold for P0?",
                top_k=3,
                db_path=indexed_db,
            )

        assert result["question"] == "What is the delay threshold for P0?"
        assert not result["refused"]
        assert len(result["sources"]) > 0
        assert "model" in result

    def test_no_evidence_refusal(self, indexed_db):
        """When LLM returns NO_EVIDENCE, refused=True."""
        mock_response = {
            "message": {
                "content": "NO_EVIDENCE: The available SOP documents "
                           "do not contain information about this."
            }
        }

        with mock.patch("src.rag.answer.chat", return_value=mock_response):
            result = answer_sop(
                "What is the recipe for chocolate cake?",
                top_k=3,
                db_path=indexed_db,
            )

        assert result["refused"]
        assert result["answer"].startswith("NO_EVIDENCE")

    def test_llm_failure_handled(self, indexed_db):
        """When Ollama is down, answer gracefully."""
        with mock.patch(
            "src.rag.answer.chat",
            side_effect=ConnectionError("Ollama not running"),
        ):
            result = answer_sop(
                "What is the delay threshold?",
                top_k=3,
                db_path=indexed_db,
            )

        assert result["refused"]
        assert "ERROR" in result["answer"] or "LLM call failed" in result["answer"]

    def test_result_structure_complete(self, indexed_db):
        """Every result must have all required keys."""
        mock_response = {
            "message": {
                "content": "According to the SOP, the threshold is 30% for P0."
            }
        }

        with mock.patch("src.rag.answer.chat", return_value=mock_response):
            result = answer_sop("delay threshold", top_k=3, db_path=indexed_db)

        for key in ("question", "answer", "sources", "refused", "model"):
            assert key in result, f"Missing key: {key}"

    def test_sources_have_required_fields(self, indexed_db):
        """Each source dict must have source, section, content_type, chunk_id."""
        mock_response = {
            "message": {"content": "The SOP states..."}
        }

        with mock.patch("src.rag.answer.chat", return_value=mock_response):
            result = answer_sop("delivery risk", top_k=3, db_path=indexed_db)

        for src in result["sources"]:
            assert "source" in src
            assert "section" in src
            assert "content_type" in src
            assert "chunk_id" in src

    def test_empty_index_returns_refused(self, tmp_path):
        """When no index exists, answer should refuse."""
        db_path = tmp_path / "empty.db"
        # Don't create the db — simulate missing index

        # But wait, retrieve_sop auto-builds. Let's mock retrieve_sop
        with mock.patch(
            "src.rag.answer.get_sop_context", return_value=""
        ):
            result = answer_sop(
                "any question",
                top_k=3,
                db_path=db_path,
            )

        assert result["refused"]
