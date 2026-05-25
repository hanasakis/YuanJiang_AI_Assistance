# YuanJiang OpsGuard Architecture

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit UI                          │
│                  (src/app/ui.py)                         │
└──────────────────────┬──────────────────────────────────┘
                       │ user query
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 LangGraph Workflow                       │
│                  (src/app/graph.py)                      │
│                                                         │
│   ┌─────────┐    ┌──────────┐    ┌───────────────┐     │
│   │  Think  │───▶│  Route   │───▶│  Execute Tool │     │
│   │ (R1)    │◀───│          │    │               │     │
│   └─────────┘    └──────────┘    └───────┬───────┘     │
│        │                                 │              │
│        │                          ┌──────▼──────┐      │
│        │                          │  Observe    │      │
│        │                          └──────┬──────┘      │
│        │                                 │              │
│        └─────────────────────────────────┘              │
│                    (ReAct loop)                          │
└────────┬──────────────────────────────┬─────────────────┘
         │                              │
         ▼                              ▼
┌──────────────────┐         ┌──────────────────┐
│   src/llm/        │         │  src/tools/       │
│  - ollama_client  │         │  - registry       │
│  - prompts        │         │  - risk_query     │
│  - output_cleaner │         │  - task_crud      │
└──────────────────┘         └──────┬───────────┘
                                    │
               ┌────────────────────┼────────────────────┐
               ▼                    ▼                    ▼
       ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
       │ src/data_ops/ │   │  src/rag/    │   │              │
       │ - duckdb_mgr  │   │ - retriever  │   │  (future)    │
       │ - metrics     │   │ - chunker    │   │              │
       │ - sql_guard   │   │ - doc_loader │   │              │
       └──────┬───────┘   └──────┬───────┘   └──────────────┘
              │                  │
              ▼                  ▼
       ┌──────────┐     ┌──────────────┐
       │  DuckDB  │     │  SOP Docs    │
       │ (olist)  │     │ (FTS5 index) │
       └──────────┘     └──────────────┘
```

## Data Flow

### Query → Answer (完整链路)

```
1. User types "上周物流延迟超过 3 天的卖家有哪些？"
2. Streamlit sends query → LangGraph State
3. ReAct Loop begins:
   a. Think: DeepSeek-R1 decides to query logistics_delay tool
   b. Route: Graph routes to Tool Executor node
   c. Act: Tool calls src/tools/risk_query → src/data_ops/metrics → DuckDB
   d. Observe: Tool result (list of sellers) injected back into context
   e. Think: R1 decides to also check SOP rules for delay thresholds
   f. Route: Graph routes to RAG Retrieval node
   g. Act: src/rag/retriever finds SOP §3.2 "物流延迟判定标准"
   h. Observe: SOP context injected
   i. Think: R1 synthesizes data + SOP → final risk assessment
   j. Route: Graph routes to FINAL_ANSWER
4. Structured report returned to UI with risks[] and tasks[]
```

### Module Dependency Graph

```
app ──┬── llm
      ├── tools ──┬── data_ops
      │           └── rag
      └── (Streamlit)
```

- `app` depends on `llm`, `tools`
- `tools` depends on `data_ops`, `rag`
- `llm`, `data_ops`, `rag` are leaf modules (no internal deps)
- Cross-module communication via Pydantic models only

## Key Design Decisions

1. **DuckDB over SQLite**: Olist queries are analytical (aggregations, window functions).
   DuckDB's columnar engine is 10-50x faster for OLAP workloads on the same hardware.

2. **LangGraph over custom loop**: ReAct is stateful — tool results accumulate, context
   grows, the graph may loop. LangGraph gives us checkpointing, interrupts, and
   visualization for free.

3. **sqlglot validation before execution**: LLM-generated SQL cannot be trusted.
   sqlglot parses and validates the AST before it reaches DuckDB.

4. **Hybrid retrieval (FTS5 + BM25) without dense embeddings**: On a small SOP corpus
   (~50 docs), sparse retrieval matches or beats dense embeddings while requiring zero
   GPU/API calls. Vector embedding can be added later when the corpus grows.

5. **DeepSeek-R1 response cleaning**: R1 wraps reasoning in `...` tags.
   The `output_cleaner` strips these and extracts the final answer portion.
