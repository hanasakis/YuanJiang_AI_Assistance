"""SOP document chunker — title-level semantic chunking.

Chunks DocumentElement output from doc_convert into searchable segments.
Rules:
  - Split on H2 (##) title boundaries
  - Preserve parent_section chain (H1 → H2 → H3)
  - Tables and checklists are never split mid-way
  - Minimum chunk size: 50 chars (merge with next if shorter)
  - Maximum chunk size: 2000 chars (split at paragraph boundary)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.rag.doc_convert import DocumentElement, convert_directory

# Min/max chunk sizes in characters
MIN_CHUNK_SIZE = 50
MAX_CHUNK_SIZE = 2000

# Content types that must be kept intact (never split)
_ATOMIC_TYPES = {"checklist", "table", "template", "code"}


@dataclass
class Chunk:
    """A searchable SOP segment with section provenance."""

    text: str
    source: str
    section: str = ""
    parent_section: str = ""
    content_type: str = "paragraph"
    chunk_id: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "section": self.section,
            "parent_section": self.parent_section,
            "content_type": self.content_type,
            "chunk_id": self.chunk_id,
        }


# ============================================================
# Chunking
# ============================================================

def chunk_elements(
    elements: list[DocumentElement],
    min_size: int = MIN_CHUNK_SIZE,
    max_size: int = MAX_CHUNK_SIZE,
) -> list[Chunk]:
    """Group DocumentElements into search-optimized Chunks.

    Strategy:
    1. Start a new chunk at each element that has a section heading change
    2. Atomic types (checklist, table) always stay together
    3. Merge undersized chunks with the previous chunk
    4. Split oversized chunks at paragraph boundaries

    Args:
        elements: DocumentElement list from convert_directory().
        min_size: Minimum chars per chunk.
        max_size: Maximum chars per chunk.

    Returns:
        List of Chunk objects ready for FTS indexing.
    """
    if not elements:
        return []

    chunks: list[Chunk] = []
    buf: list[DocumentElement] = []
    current_section = ""
    current_parent = ""
    chunk_counter = 0

    def _make_chunk() -> Chunk:
        nonlocal chunk_counter
        text = "\n\n".join(e.text for e in buf)
        first = buf[0]
        chunk_counter += 1
        return Chunk(
            text=text,
            source=first.source,
            section=first.section or current_section,
            parent_section=current_parent,
            content_type=first.content_type,
            chunk_id=f"{first.source}_{chunk_counter:04d}",
        )

    for el in elements:
        # Detect section change → flush current chunk
        if el.section and el.section != current_section:
            # Update parent
            parts = el.section.split(" > ")
            if len(parts) > 1:
                current_parent = " > ".join(parts[:-1])
            else:
                current_parent = ""
            current_section = el.section

            if buf:
                chunks.append(_make_chunk())
                buf.clear()

        # Atomic content types: don't split internally
        if buf and buf[-1].content_type in _ATOMIC_TYPES:
            # Keep atomic content with its section
            pass

        buf.append(el)

        # Check if current buffer exceeds max_size
        buf_text = "\n\n".join(e.text for e in buf)
        if len(buf_text) >= max_size and el.content_type not in _ATOMIC_TYPES:
            chunks.append(_make_chunk())
            buf.clear()

    # Final flush
    if buf:
        chunks.append(_make_chunk())

    # ---- Post-processing: merge undersized chunks ----
    merged: list[Chunk] = []
    for ch in chunks:
        if merged and len(ch.text) < min_size:
            merged[-1].text += "\n\n" + ch.text
            # Update section to reflect the merger
            if ch.section and ch.section not in merged[-1].section:
                merged[-1].section = merged[-1].section or ch.section
        else:
            merged.append(ch)

    return merged


def chunk_directory(
    dir_path: str = "docs/sop",
    glob_pattern: str = "**/*.md",
) -> list[Chunk]:
    """Full pipeline: convert → chunk all SOP files in a directory.

    Args:
        dir_path: Path to SOP directory.
        glob_pattern: File pattern to match.

    Returns:
        List of Chunk objects.
    """
    elements = convert_directory(dir_path, glob_pattern)
    return chunk_elements(elements)
