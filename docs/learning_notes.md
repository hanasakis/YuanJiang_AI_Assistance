# YuanJiang OpsGuard — Learning Notes

_This file grows with each phase. Each section corresponds to a completed module._

---

## Phase 0: Sandbox Safety Configuration

_See `docs/security.md` for the full security architecture._

### Key Concepts

1. **Defense in Depth**: Three layers — `.gitignore` (prevents commits), Permissions (tool-level allow/deny), Sandbox (OS-level filesystem isolation).

2. **settings.json vs settings.local.json**: The former is the team's shared security baseline (committed); the latter is each developer's machine-specific config (gitignored). Local overrides take precedence but should never relax a deny rule.

3. **Windows Sandbox Limitation**: Windows Job Objects provide weaker filesystem isolation than Linux Landlock or macOS Seatbelt. Fallback: stricter deny rules + Sandbox Guard auditing.

### Interview Questions

Q1: Why separate sandbox policies from permission rules?
A: Permissions control *tool access* (application layer); sandbox controls *process scope* (OS layer). A bug in the permission system should not be able to escape the sandbox, and vice versa.

Q2: What happens when `settings.json` and `settings.local.json` conflict?
A: local.json wins. This is intentional — it lets developers add machine-specific allows (e.g., custom Python paths) without weakening the team baseline.

---

## Phase 1: Project Scaffold

### Key Concepts

1. **Module Boundaries**: Each `src/` subdirectory is owned by exactly one sub-agent. This prevents merge conflicts and lets agents work in parallel. The only allowed cross-module dependency is through Pydantic data models.

2. **DuckDB for OLAP**: Unlike SQLite (row-oriented, OLTP), DuckDB is columnar and vectorized — it can scan 100M rows in under a second on a laptop. Perfect for seller-level aggregation queries over the Olist dataset.

3. **LangGraph ReAct Loop**: The core workflow is `Think → Route → Act → Observe → Think`. LangGraph provides the state machine; DeepSeek-R1 provides the reasoning.

### Interview Questions

Q1: Why not use LangChain's built-in AgentExecutor?
A: LangGraph gives us explicit control over the state graph — we can add checkpoints, human-in-the-loop interrupts, and custom routing logic that AgentExecutor abstracts away.

Q2: Why validate LLM-generated SQL with sqlglot?
A: LLMs hallucinate column names, invent SQL syntax, or attempt DROP TABLE. sqlglot parses the AST and lets us reject any query that doesn't match the known schema before execution.

Q3: Why keep `data/eval/` committable but `data/runtime/` not?
A: eval contains golden-standard test data that should be versioned. runtime contains ephemeral files (temp tables, cached results) that differ per run and per machine.

---

## Future Phases

- Phase 2: Data Agent — Olist ingestion, DuckDB schema, metrics
- Phase 3: Document Agent — SOP loading, chunking, metadata
- Phase 4: RAG Agent — FTS5/BM25 retrieval, context assembly
- Phase 5: Tool Agent — Inspection tools, Pydantic schemas
- Phase 6: Workflow Agent — LangGraph graph, ReAct loop
- Phase 7: UI + Integration — Streamlit, E2E tests
