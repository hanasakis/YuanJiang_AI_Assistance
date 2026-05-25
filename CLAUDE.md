# CLAUDE.md — YuanJiang OpsGuard Development Rules

## Project Identity

YuanJiang OpsGuard is a local-first, Ollama-powered e-commerce fulfillment inspection agent.
It uses LangGraph to orchestrate a ReAct loop over Olist data (DuckDB), SOP documents (FTS/BM25),
and inspection task tools (Pydantic schemas).

## Cardinal Rules

1. **Runtime LLM is ALWAYS local Ollama DeepSeek-R1.** Never change the runtime model to any
   cloud API (OpenAI, Anthropic, DeepSeek API). Claude sub-agents participate in development,
   code review, and testing only — never in runtime inference.

2. **OLLAMA_MODEL must reflect the actual local tag.** The tag is `deepseek-r1:8b` on this
   machine (verified via `ollama list`). If the user pulls a different tag, update `.env.example`.

3. **Never read `.env` directly.** Claude should only read `.env.example`. Real secrets stay in
   `.env` (gitignored).

4. **Never commit `data/raw/` or `data/processed/`.** These contain the Olist dataset (~120 MB)
   and intermediate artifacts. Use `data/sample/` for small test fixtures.

5. **Never weaken business logic to pass tests.** The Test Agent must not modify `src/` to make
   a test green. If a test fails, report it as a bug to the lead agent.

## Sub-Agent Architecture

Nine specialized sub-agents handle different modules. Each sub-agent has a role definition in
`.claude/agents/`. The lead agent (Claude Opus 4.7) orchestrates them.

| Agent | Module | Write Scope |
|-------|--------|-------------|
| Data Agent | `src/data_ops/` | Olist ingestion, DuckDB, metrics |
| Document Agent | `src/rag/` (document part) | SOP loading, chunking |
| RAG Agent | `src/rag/` (retrieval part) | FTS/BM25, context assembly |
| Tool Agent | `src/tools/` | Inspection tools, Pydantic schemas |
| Workflow Agent | `src/app/` | LangGraph graph, state, routing |
| Test Agent | `tests/` | Unit + integration tests |
| Sandbox Guard Agent | read-only | Permission audit, sandbox policy |
| Git Guard Agent | read-only | Pre-commit diff audit |
| Tutor Agent | `docs/tutorial/`, `docs/interview/` | Learning notes |

## Phase Workflow

```
Sandbox Guard audit → Sub-agent dev → Test Agent verify
→ Sandbox Guard + Git Guard review → Commit → Tutor notes
```

## Code Conventions

- Python 3.11+, type hints on public interfaces
- Pydantic for all data models crossing module boundaries
- SQL queries via DuckDB, validated with sqlglot before execution
- Function-calling schemas follow OpenAI tool-use JSON format
- Streamlit UI is thin — all logic lives in `src/`

## Testing

- `pytest` for all modules
- Each `src/<module>/` has a corresponding `tests/<module>/`
- Minimum 80% branch coverage for data_ops, rag, tools
- Fixtures in `tests/conftest.py`
- Test data in `tests/fixtures/` or `data/sample/`

## Git Rules

- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`)
- Never commit: `.env`, `data/raw/`, `data/processed/`, `data/runtime/`, `data/chroma/`,
  `models/`, `*.key`, `*.pem`, `credentials.*`, `.claude/settings.local.json`
- Pre-commit hooks enforced by Git Guard Agent
