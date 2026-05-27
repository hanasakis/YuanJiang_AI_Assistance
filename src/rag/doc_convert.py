"""Document converter for SOP files (Markdown, PDF, DOCX, HTML).

Priority: Docling (primary) → PyMuPDF4LLM (PDF fallback) → raw text.
Output: unified DocumentElement list with full metadata.

Docling is preferred because it preserves:
- Document layout and reading order
- Table structure
- Section hierarchy
- Multi-column content detection
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DocumentElement:
    """A single document chunk with full provenance metadata.

    Attributes:
        text: The chunk's text content.
        source: Source file path (relative to project root).
        section: Section heading this chunk belongs to.
        page: Approximate page number (0-indexed, from source position).
        content_type: Type of content (checklist, rule, threshold, example, procedure).
        element_id: Unique stable ID (SHA1 of source + section + content preview).
    """

    text: str
    source: str
    section: str = ""
    page: int = 0
    content_type: str = "paragraph"
    element_id: str = ""

    def __post_init__(self):
        if not self.element_id:
            key = f"{self.source}|{self.section}|{self.text[:100]}"
            self.element_id = hashlib.sha1(key.encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "section": self.section,
            "page": self.page,
            "content_type": self.content_type,
            "element_id": self.element_id,
        }


# ============================================================
# Content type classification
# ============================================================

def _classify_content(text: str, section_title: str) -> str:
    """Heuristic content type classification based on patterns."""
    combined = (section_title + " " + text[:200]).lower()

    if re.search(r"checklist|检查清单|核查项", combined):
        return "checklist"
    if re.search(r"p\d|p0|p1|p2|p3|阈值|threshold|紧急|重要", combined):
        return "threshold"
    if re.search(r"案例|example|示例", combined):
        return "example"
    if re.search(r"流程|步骤|step|procedure|工作流", combined):
        return "procedure"
    if re.search(r"模板|template|回复|通知", combined):
        return "template"
    if re.search(r"规则|rule|条件|禁止|必须", combined):
        return "rule"

    return "paragraph"


# ============================================================
# Markdown converter (always available, no deps)
# ============================================================

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_MD_PAGE_BREAK = re.compile(r"---|\n\n\n+")


def convert_markdown(file_path: str | Path) -> list[DocumentElement]:
    """Convert a Markdown file into DocumentElement list.

    Splits by ## headings, assigns section hierarchy, and classifies
    content type per element.

    Args:
        file_path: Path to .md file.

    Returns:
        List of DocumentElement, one per logical section/paragraph.
    """
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8")
    source = str(file_path.as_posix())

    elements: list[DocumentElement] = []
    lines = text.splitlines()
    current_section = ""
    current_text: list[str] = []
    page_counter = 0

    def _flush():
        nonlocal page_counter
        if not current_text:
            return
        body = "\n".join(current_text).strip()
        if body:
            elements.append(DocumentElement(
                text=body,
                source=source,
                section=current_section,
                page=page_counter,
                content_type=_classify_content(body, current_section),
            ))
            page_counter += 1
        current_text.clear()

    for line in lines:
        match = _MD_HEADING.match(line)
        if match:
            _flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            if level == 1:
                current_section = title
            elif level >= 2:
                current_section = title if not current_section else f"{current_section} > {title}"
        else:
            stripped = line.strip()
            if stripped:
                current_text.append(stripped)
            elif current_text:
                # Blank line = paragraph boundary
                _flush()

    _flush()
    return elements


# ============================================================
# PDF converter with fallback chain
# ============================================================

def _convert_pdf_docling(file_path: Path) -> list[DocumentElement]:
    """Convert PDF using Docling (primary path)."""
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(file_path))
    doc = result.document

    elements: list[DocumentElement] = []
    source = str(file_path.as_posix())

    for i, item in enumerate(doc.iterate_items()):
        text = item.get_text() if hasattr(item, "get_text") else str(item)
        if not text or not text.strip():
            continue

        section = ""
        if hasattr(item, "label"):
            section = str(item.label) if item.label else ""

        elements.append(DocumentElement(
            text=text.strip(),
            source=source,
            section=section,
            page=i,  # items are ordered by reading order
            content_type=_classify_content(text.strip(), section),
        ))

    return elements


def _convert_pdf_pymupdf4llm(file_path: Path) -> list[DocumentElement]:
    """Convert PDF using PyMuPDF4LLM (fallback path)."""
    import pymupdf4llm

    md_text = pymupdf4llm.to_markdown(str(file_path))

    # Write to temp .md and reuse markdown converter
    import tempfile
    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(md_text)
        temp_path = Path(f.name)

    try:
        elements = convert_markdown(temp_path)
        for el in elements:
            el.source = str(file_path.as_posix())
        return elements
    finally:
        temp_path.unlink(missing_ok=True)


def convert_pdf(file_path: str | Path) -> list[DocumentElement]:
    """Convert a PDF file to DocumentElement list.

    Tries Docling first. Falls back to PyMuPDF4LLM on failure.
    Both unavailable → readable error.

    Args:
        file_path: Path to .pdf file.

    Returns:
        List of DocumentElement.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    # Attempt 1: Docling
    try:
        return _convert_pdf_docling(file_path)
    except ImportError:
        pass
    except Exception as exc:
        # Docling failed for non-import reasons (e.g. complex layout)
        import warnings
        warnings.warn(f"Docling failed on {file_path.name}: {exc}. Trying PyMuPDF4LLM.")

    # Attempt 2: PyMuPDF4LLM
    try:
        return _convert_pdf_pymupdf4llm(file_path)
    except ImportError:
        raise RuntimeError(
            "No PDF converter available. Install docling or pymupdf4llm:\n"
            "  pip install pymupdf pymupdf4llm"
        )
    except Exception as exc:
        raise RuntimeError(
            f"Both Docling and PyMuPDF4LLM failed on {file_path.name}: {exc}"
        )


# ============================================================
# Unified converter
# ============================================================

def convert_file(file_path: str | Path) -> list[DocumentElement]:
    """Convert any supported document to DocumentElement list.

    Auto-detects format by file extension:
      - .md / .markdown → convert_markdown()
      - .pdf → convert_pdf()  (Docling → PyMuPDF4LLM fallback)
      - .docx / .html → Docling (if available)
      - .txt → read as plain text

    Args:
        file_path: Path to the document.

    Returns:
        List of DocumentElement.
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if suffix in (".md", ".markdown"):
        return convert_markdown(file_path)

    if suffix == ".pdf":
        return convert_pdf(file_path)

    if suffix in (".docx", ".html", ".htm"):
        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            result = converter.convert(str(file_path))
            doc = result.document
            source = str(file_path.as_posix())
            elements: list[DocumentElement] = []
            for i, item in enumerate(doc.iterate_items()):
                text = item.get_text() if hasattr(item, "get_text") else str(item)
                if text and text.strip():
                    elements.append(DocumentElement(
                        text=text.strip(),
                        source=source,
                        page=i,
                        content_type="paragraph",
                    ))
            return elements
        except ImportError:
            raise RuntimeError(
                f"Cannot process {suffix} files. Install docling:\n"
                f"  pip install docling"
            )

    if suffix == ".txt":
        text = file_path.read_text(encoding="utf-8")
        return [DocumentElement(
            text=text.strip(),
            source=str(file_path.as_posix()),
            content_type="paragraph",
        )]

    raise ValueError(
        f"Unsupported file format: {suffix}. "
        f"Supported: .md, .pdf, .docx, .html, .txt"
    )


def convert_directory(
    dir_path: str | Path,
    glob_pattern: str = "**/*.md",
) -> list[DocumentElement]:
    """Convert all matching documents in a directory.

    Args:
        dir_path: Root directory to scan.
        glob_pattern: Glob pattern for files to convert.

    Returns:
        Flattened list of all DocumentElements from all files.
    """
    dir_path = Path(dir_path)
    all_elements: list[DocumentElement] = []

    for file_path in sorted(dir_path.glob(glob_pattern)):
        if file_path.is_file():
            all_elements.extend(convert_file(file_path))

    return all_elements
