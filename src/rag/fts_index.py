"""SQLite FTS5 keyword search index for SOP chunks.

Provides full-text search over chunked SOP documents without any external
embedding model. Uses SQLite FTS5 with BM25 ranking.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.rag.chunker import Chunk, chunk_directory

_DEFAULT_DB = Path("data/fts/sop_index.db")


def build_fts_index(
    chunks: list[Chunk] | None = None,
    sop_dir: str = "docs/sop",
    db_path: str | Path = _DEFAULT_DB,
    overwrite: bool = True,
) -> Path:
    """Build or rebuild the FTS5 index from SOP chunks.

    Args:
        chunks: Pre-chunked list. If None, runs chunk_directory(sop_dir).
        sop_dir: Path to SOP documents (used if chunks is None).
        db_path: SQLite database path.
        overwrite: If True, drop and recreate the index.

    Returns:
        Path to the built SQLite FTS database.
    """
    if chunks is None:
        chunks = chunk_directory(sop_dir)

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if overwrite and db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL")

    # FTS5 table with content + metadata columns
    con.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS sop_chunks USING fts5(
            text,
            source,
            section,
            parent_section,
            content_type,
            chunk_id UNINDEXED,
            tokenize='porter unicode61'
        )
    """)

    # Batch insert
    rows = [
        (
            ch.text,
            ch.source,
            ch.section,
            ch.parent_section,
            ch.content_type,
            ch.chunk_id,
        )
        for ch in chunks
        if ch.text.strip()
    ]

    con.executemany(
        "INSERT INTO sop_chunks "
        "(text, source, section, parent_section, content_type, chunk_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )

    con.commit()
    con.close()

    print(f"FTS index built: {len(rows)} chunks in {db_path}")
    return db_path


def search_fts(
    query: str,
    db_path: str | Path = _DEFAULT_DB,
    top_k: int = 5,
    content_type_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Search the FTS5 index and return ranked results.

    Uses FTS5 built-in BM25 ranking via the bm25() auxiliary function.

    Args:
        query: Search keywords.
        db_path: Path to the FTS5 SQLite database.
        top_k: Max results to return.
        content_type_filter: Optional filter by content_type.

    Returns:
        List of result dicts with keys: text, source, section,
        content_type, chunk_id, score (bm25 rank, lower = better).
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"FTS index not found at {db_path}. Run build_fts_index() first."
        )

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    where = ""
    if content_type_filter:
        where = f"AND content_type = '{content_type_filter}'"

    base_sql = f"""
        SELECT
            text,
            source,
            section,
            parent_section,
            content_type,
            chunk_id,
            bm25(sop_chunks, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0) AS score
        FROM sop_chunks
        WHERE sop_chunks MATCH ?
        {where}
        ORDER BY score
        LIMIT ?
    """

    # Phase 1: AND query (all terms required)
    and_query = _sanitize_fts_query(query, operator="AND")
    try:
        rows = con.execute(base_sql, [and_query, top_k]).fetchall()
    except sqlite3.OperationalError:
        rows = []

    # Phase 2: If AND returned nothing, try OR (any term)
    if not rows and len(query.split()) > 1:
        or_query = _sanitize_fts_query(query, operator="OR")
        try:
            rows = con.execute(base_sql, [or_query, top_k]).fetchall()
        except sqlite3.OperationalError:
            rows = []

    # Phase 3: If still nothing, fall back to LIKE
    if not rows:
        try:
            like_pattern = f"%{query.replace('%', '%%')}%"
            rows = con.execute(
                f"""
                SELECT
                    text, source, section, parent_section, content_type, chunk_id,
                    999 AS score
                FROM sop_chunks
                WHERE text LIKE ?
                {where}
                LIMIT ?
                """,
                [like_pattern, top_k],
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

    con.close()

    return [
        {
            "text": r["text"],
            "source": r["source"],
            "section": r["section"],
            "parent_section": r["parent_section"],
            "content_type": r["content_type"],
            "chunk_id": r["chunk_id"],
            "score": round(float(r["score"]), 4),
        }
        for r in rows
    ]


def get_index_stats(db_path: str | Path = _DEFAULT_DB) -> dict[str, Any]:
    """Return basic statistics about the FTS index."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {"status": "missing"}

    con = sqlite3.connect(str(db_path))
    total = con.execute("SELECT count(*) FROM sop_chunks").fetchone()[0]
    sources = con.execute(
        "SELECT source, count(*) as cnt FROM sop_chunks GROUP BY source"
    ).fetchall()
    types = con.execute(
        "SELECT content_type, count(*) as cnt FROM sop_chunks GROUP BY content_type"
    ).fetchall()
    con.close()

    return {
        "status": "ok",
        "total_chunks": total,
        "db_path": str(db_path),
        "by_source": {s: c for s, c in sources},
        "by_content_type": {t: c for t, c in types},
    }


def _sanitize_fts_query(query: str, operator: str = "AND") -> str:
    """Sanitize user input for FTS5 MATCH syntax.

    FTS5 treats these characters specially: * " ( ) -
    We quote each term and add prefix matching with the given operator.

    Args:
        query: Raw user query string.
        operator: "AND" (all terms required) or "OR" (any term).
    """
    sanitized = query.replace('"', "").replace("*", "").replace("-", " ")
    words = sanitized.split()
    if not words:
        return '""'
    terms = [f'"{w}"*' for w in words]
    return f" {operator} ".join(terms)
