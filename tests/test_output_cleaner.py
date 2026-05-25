"""Tests for src/llm/output_cleaner.py — strip_think and extract_json_block."""
from __future__ import annotations

import pytest
from src.llm.output_cleaner import extract_json_block, strip_think


# ============================================================
# strip_think
# ============================================================

class TestStripThink:
    def test_strips_simple_think_block(self):
        output = strip_think("<think>reasoning here</think>The final answer.")
        assert output == "The final answer."

    def test_strips_multiple_think_blocks(self):
        output = strip_think(
            "<think>step 1</think>data <think>step 2</think>result: 42"
        )
        assert output == "data result: 42"

    def test_plain_text_unchanged(self):
        output = strip_think("Plain answer without any thinking.")
        assert output == "Plain answer without any thinking."

    def test_empty_string(self):
        assert strip_think("") == ""

    def test_only_think_block(self):
        output = strip_think("<think>hidden reasoning</think>")
        assert output == ""

    def test_nested_think_tags_removed(self):
        output = strip_think("<think>outer <think>inner</think>tail")
        assert output == "tail"

    def test_multiline_think_block(self):
        output = strip_think(
            "<think>\n"
            "Step 1: check data\n"
            "Step 2: verify threshold\n"
            "</think>\n"
            "The seller is at risk."
        )
        assert output == "The seller is at risk."

    def test_lowercase_think_tags(self):
        output = strip_think("<think>lowercase reasoning</think>Final answer.")
        assert output == "Final answer."

    def test_think_with_spaces(self):
        output = strip_think("< think >reasoning</ think > result")
        assert output == "result"

    def test_realistic_r1_output(self):
        raw = (
            "<think>\n"
            "user query needs logistics delay check\n"
            "I should call query_logistics_delay tool\n"
            "</think>\n\n"
            "Based on query results, the following sellers have risk:\n\n"
            "```json\n"
            '{"risks": [{"seller_id": "abc", "level": "P1"}]}\n'
            "```"
        )
        cleaned = strip_think(raw)
        assert "<think>" not in cleaned
        assert "sellers have risk" in cleaned
        assert "```json" in cleaned

    def test_unicode_think_markers(self):
        """DeepSeek-R1 via some Ollama builds uses Unicode THINK markers."""
        start = "\U0002DFE8think\U0002DFE9"
        end = "\U0002DFE8/think\U0002DFE9"
        raw = f"{start}hidden reasoning{end}Visible answer."
        output = strip_think(raw)
        assert output == "Visible answer."


# ============================================================
# extract_json_block
# ============================================================

class TestExtractJsonBlock:
    def test_extracts_fenced_json_object(self):
        result = extract_json_block('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_extracts_fenced_json_array(self):
        result = extract_json_block("```json\n[1, 2, 3]\n```")
        assert result == [1, 2, 3]

    def test_extracts_fenced_without_lang_specifier(self):
        result = extract_json_block("```\n{\"a\": 1}\n```")
        assert result == {"a": 1}

    def test_extracts_bare_json_object(self):
        result = extract_json_block('The answer is {"score": 0.9, "label": "P1"}.')
        assert result == {"score": 0.9, "label": "P1"}

    def test_extracts_bare_json_array(self):
        result = extract_json_block("Results: [{\"id\": 1}, {\"id\": 2}]")
        assert result == [{"id": 1}, {"id": 2}]

    def test_no_json_returns_none(self):
        result = extract_json_block("No structured data here.")
        assert result is None

    def test_empty_string_returns_none(self):
        assert extract_json_block("") is None

    def test_invalid_json_returns_none(self):
        result = extract_json_block("{invalid json here}")
        assert result is None

    def test_nested_json_extracts_outermost(self):
        result = extract_json_block(
            '{"outer": {"inner": [1, 2, 3]}, "other": "value"}'
        )
        assert result == {"outer": {"inner": [1, 2, 3]}, "other": "value"}

    def test_fence_priority_over_bare(self):
        result = extract_json_block(
            '```json\n{"from_fence": true}\n```\nOutside: {"from_bare": false}'
        )
        assert result == {"from_fence": True}

    def test_realistic_inspection_report(self):
        raw = (
            "According to SOP 3.2 thresholds, risks identified:\n\n"
            "```json\n"
            "{\n"
            '  "risks": [\n'
            '    {"seller_id": "s001", "risk_type": "logistics_delay", "level": "P1"},\n'
            '    {"seller_id": "s002", "risk_type": "negative_review", "level": "P2"}\n'
            "  ],\n"
            '  "summary": "2 sellers at risk"\n'
            "}\n"
            "```"
        )
        result = extract_json_block(raw)
        assert result is not None
        assert len(result["risks"]) == 2
        assert result["risks"][0]["seller_id"] == "s001"
        assert result["risks"][0]["level"] == "P1"
        assert result["summary"] == "2 sellers at risk"

    def test_json_with_special_chars(self):
        result = extract_json_block(
            '{"message": "delay rate > 30% triggers P0 alert", "threshold": 0.3}'
        )
        assert result["message"] == "delay rate > 30% triggers P0 alert"
        assert result["threshold"] == 0.3
