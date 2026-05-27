# Document Processing — Why Not Simple Text Extraction

## Problem

Naive text extraction (`cat file.pdf | strings` or `PyPDF2.extract_text()`) produces
flat, unstructured text that loses all document semantics:

```
Raw output (PyPDF2):
"1.2 P0 30% 1.2 P0 P1 15% 30% avg_delivery_delay_days..."

The human reads this and understands it's a table. The LLM sees a stream of
tokens with no column boundaries, no row associations, and no context about
which section this belongs to.
```

## What Docling Solves

Docling is a document understanding library that preserves:

### 1. Reading Order

Multi-column PDFs often confuse naive extractors. Docling detects the column
layout and outputs text in the correct reading order:

```
Naive (left column, then right):
"P0 P1 P0 P1 P0 delay_rate 30% 15%   low_review 50% 30%   defect 40% 20%"

Docling (row-by-row):
"| Level | delay_rate | low_review | defect |
 | P0    | > 30%      | > 50%      | > 40%  |
 | P1    | 15%-30%    | 30%-50%    | 20%-40% |"
```

### 2. Table Structure

SOP documents are dense with tables (thresholds, checklists, routing rules).
Docling preserves table structure as structured markdown, which the LLM can
parse reliably.

### 3. Section Hierarchy

Docling understands heading levels (H1 → H2 → H3), so we can track which
section each chunk belongs to. This is critical for attribution:
"According to SOP-DELIVERY-001 §3.2..."

### 4. Multi-Format Support

Docling handles PDF, DOCX, PPTX, HTML, and images with a unified API.
Operations teams may provide SOPs in any of these formats.

## Why PyMuPDF4LLM as Fallback

PyMuPDF4LLM is lighter weight (~15 MB vs Docling's ~500 MB with ML models)
and handles 90% of PDFs correctly. It converts PDF to Markdown using
PyMuPDF's layout analysis, which covers:

- Text extraction with font size and position
- Basic table detection
- Heading detection by font characteristics

When to fall back:
- Docling import fails (not installed)
- Docling crashes on a complex layout
- Memory-constrained environments (PyMuPDF4LLM needs less RAM)

PyMuPDF4LLM does NOT handle: DOCX, HTML, images, or complex multi-column
detection as well as Docling. But for the 90% case of single-column SOP
PDFs, it is sufficient.

## Why Metadata Matters

Each DocumentElement carries 5 metadata fields:

### page (approximate page number)

When the LLM answers "According to SOP §2.1...", a human auditor needs to
verify the claim. The `page` field lets them jump directly to the right
page in the original document.

### section (heading path)

The `section` field records the full heading path (e.g., "风险等级判定 >
P0 紧急"), so the LLM can cite the specific clause, not just "the document
says...". This transforms retrieval from "somewhere in this file" to
"this specific clause in this file".

### content_type (checklist / rule / threshold / example / procedure)

Different content types serve different purposes in an answer:
- `threshold` → the LLM should use this to judge severity
- `procedure` → the LLM should use this to suggest next steps
- `example` → the LLM should use this to illustrate, not to derive rules
- `checklist` → the LLM should itemize when generating tasks

Without content_type, the LLM treats all text equally and may cite
an *example* as if it were a *rule*.

### source (file path)

When the knowledge base has 20 SOP documents, `source` lets the LLM
distinguish "SOP-REVIEW-002 says escalate at 50%" from "SOP-DELIVERY-001
says escalate at 30%". Without source tracking, all text collapses into
one undifferentiated pool.

### element_id (stable hash)

Each element has a content-based hash ID. This means:
- Same content → same ID (deduplication across re-indexing)
- Different content → different ID (detecting SOP updates)
- IDs survive database rebuilds (deterministic, no auto-increment)

## The Document Conversion Pipeline

```
Input file (.pdf / .md / .docx)
    │
    ▼
Docling (primary)
    │  success → structured markdown with layout
    │  failure → PyMuPDF4LLM (PDF only)
    │            failure → raw text (readable error)
    ▼
Markdown → sections (split by ## headings)
    │
    ▼
Sections → elements (paragraph-level chunks)
    │
    ▼
Each element tagged: text + source + section + page + content_type + element_id
    │
    ▼
DocumentElement list → RAG index (FTS5 / BM25)
```
