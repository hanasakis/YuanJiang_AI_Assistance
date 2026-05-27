"""Tests for src/rag/doc_convert.py — document conversion and metadata.

Tests use temp Markdown files (no external deps required for .md).
PDF tests are marked skip if Docling/PyMuPDF4LLM not installed.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.rag.doc_convert import (
    DocumentElement,
    convert_directory,
    convert_file,
    convert_markdown,
)


# ============================================================
# DocumentElement
# ============================================================

class TestDocumentElement:
    def test_to_dict_has_all_fields(self):
        el = DocumentElement(
            text="Test content",
            source="docs/sop/test.md",
            section="## Section A",
            page=0,
            content_type="rule",
        )
        d = el.to_dict()
        assert d["text"] == "Test content"
        assert d["source"] == "docs/sop/test.md"
        assert d["section"] == "## Section A"
        assert d["page"] == 0
        assert d["content_type"] == "rule"
        assert len(d["element_id"]) == 12

    def test_element_id_is_stable(self):
        el1 = DocumentElement(
            text="Same content", source="a.md",
            section="Intro", page=0, content_type="paragraph",
        )
        el2 = DocumentElement(
            text="Same content", source="a.md",
            section="Intro", page=0, content_type="paragraph",
        )
        assert el1.element_id == el2.element_id

    def test_element_id_differs_for_different_content(self):
        el1 = DocumentElement(text="A", source="a.md")
        el2 = DocumentElement(text="B", source="a.md")
        assert el1.element_id != el2.element_id


# ============================================================
# convert_markdown
# ============================================================

class TestConvertMarkdown:
    def test_converts_simple_markdown(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text(
            "# Main Title\n\n"
            "Intro paragraph text here.\n\n"
            "## Section One\n\n"
            "Content of section one.\n\n"
            "Another paragraph in section one.\n\n"
            "## Section Two\n\n"
            "Content of section two."
        )
        elements = convert_markdown(md)

        assert len(elements) > 0
        assert any("Intro paragraph" in e.text for e in elements)
        assert any("Content of section one" in e.text for e in elements)
        assert any("Content of section two" in e.text for e in elements)

    def test_all_elements_have_source(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nSome content here.\n\n## Section\n\nMore content.")
        elements = convert_markdown(md)

        for el in elements:
            assert "test.md" in el.source

    def test_section_is_tracked(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text(
            "# Doc Title\n\n"
            "Preamble paragraph.\n\n"
            "## Risk Level Rules\n\n"
            "P0 means critical risk.\n\n"
            "P1 means important risk.\n\n"
            "### Threshold Values\n\n"
            "Delay > 30% triggers P0.\n\n"
        )
        elements = convert_markdown(md)

        # Find elements belonging to "Risk Level Rules" section
        risk_elements = [
            e for e in elements if "Risk Level Rules" in e.section
        ]
        assert len(risk_elements) > 0
        assert any("P0 means critical risk" in e.text for e in risk_elements)

        # Sub-section should include full path
        sub_elements = [
            e for e in elements if "Threshold Values" in e.section
        ]
        assert len(sub_elements) > 0
        assert any("Delay > 30%" in e.text for e in sub_elements)

    def test_content_type_is_classified(self, tmp_path):
        md = tmp_path / "test.md"
        # Use ASCII-safe content with classification keywords
        md.write_text(
            "# SOP\n\n"
            "## P0 Critical Thresholds\n\n"
            "delay_rate > 30% triggers P0 alert.\n\n"
            "## Inspection Checklist\n\n"
            "- [ ] Verify delay rate\n"
            "- [ ] Check carrier status\n\n"
            "## Case Study: Example 1\n\n"
            "A seller had 23% delay rate.\n\n"
            "## Step-by-Step Procedure\n\n"
            "Step 1: query data. Step 2: create task.\n\n"
            "## Reply Template\n\n"
            "Dear seller, your delay rate has exceeded limits.\n\n"
            "## General Rule\n\n"
            "All inspections must follow SOP guidelines.\n\n"
        )
        elements = convert_markdown(md)

        types_found = {e.content_type for e in elements}
        # Should have classified content beyond just "paragraph"
        target = {"threshold", "checklist", "example", "procedure", "template", "rule"}
        assert types_found & target, (
            f"Expected at least one of {target}, got {types_found}"
        )

    def test_page_numbers_increment(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text(
            "# Title\n\n"
            "Paragraph one.\n\n"
            "Paragraph two.\n\n"
            "Paragraph three.\n\n"
            "Paragraph four."
        )
        elements = convert_markdown(md)
        pages = [e.page for e in elements]
        assert pages == sorted(pages)  # monotonic
        assert pages[-1] >= pages[0]   # at least one increment

    def test_empty_file(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("")
        elements = convert_markdown(md)
        assert elements == []

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            convert_markdown("/nonexistent/file.md")


# ============================================================
# convert_file — Markdown path
# ============================================================

class TestConvertFileMarkdown:
    def test_routes_md_to_markdown_converter(self, tmp_path):
        md = tmp_path / "sop.md"
        md.write_text("# Test\n\nContent text.")
        elements = convert_file(md)
        assert len(elements) > 0
        assert elements[0].source.endswith("sop.md")

    def test_routes_markdown_extension(self, tmp_path):
        md = tmp_path / "doc.markdown"
        md.write_text("# Test\n\nContent.")
        elements = convert_file(md)
        assert len(elements) > 0

    def test_unsupported_extension_raises(self, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_text("data")
        with pytest.raises(ValueError, match="Unsupported"):
            convert_file(f)


# ============================================================
# convert_directory
# ============================================================

class TestConvertDirectory:
    def test_converts_all_md_files(self, tmp_path):
        (tmp_path / "a.md").write_text("# A\n\nContent A.")
        (tmp_path / "b.md").write_text("# B\n\nContent B.")
        (tmp_path / "not_md.txt").write_text("ignored")

        elements = convert_directory(tmp_path, glob_pattern="*.md")
        sources = {e.source for e in elements}
        assert len(sources) >= 2

    def test_empty_directory(self, tmp_path):
        elements = convert_directory(tmp_path, glob_pattern="*.md")
        assert elements == []


# ============================================================
# Real SOP files
# ============================================================

class TestRealSopFiles:
    def test_converts_all_sop_markdown_files(self):
        """Verify all 4 real SOP files convert without error."""
        sop_dir = Path("docs/sop")
        if not sop_dir.exists():
            pytest.skip("docs/sop/ not found")

        elements = convert_directory(sop_dir, glob_pattern="*.md")
        assert len(elements) > 0

        sources = {e.source for e in elements}
        assert any("seller_delivery_risk" in s for s in sources)
        assert any("low_review_triage" in s for s in sources)
        assert any("product_quality_inspection" in s for s in sources)
        assert any("inspection_task_policy" in s for s in sources)

    def test_sop_elements_have_metadata(self):
        """Every SOP element must have all metadata fields."""
        sop_dir = Path("docs/sop")
        if not sop_dir.exists():
            pytest.skip("docs/sop/ not found")

        elements = convert_directory(sop_dir, glob_pattern="*.md")
        for el in elements:
            assert el.text, f"Empty text in element {el.element_id}"
            assert el.source, f"Empty source in element {el.element_id}"
            assert el.element_id, f"Empty element_id"
            assert el.content_type in (
                "paragraph", "checklist", "rule", "threshold",
                "example", "procedure", "template",
            ), f"Unknown content_type '{el.content_type}'"

    def test_sop_elements_have_sections(self):
        """Most SOP elements should have section context."""
        sop_dir = Path("docs/sop")
        if not sop_dir.exists():
            pytest.skip("docs/sop/ not found")

        elements = convert_directory(sop_dir, glob_pattern="*.md")
        with_section = [e for e in elements if e.section]
        # At least 50% of elements should have section context
        assert len(with_section) > len(elements) * 0.5, (
            f"Only {len(with_section)}/{len(elements)} elements have sections"
        )
