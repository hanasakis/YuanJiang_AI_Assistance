"""app — LangGraph workflow orchestration and Streamlit UI entry point.

The app module is the top-level layer that wires together:
- llm: Ollama DeepSeek-R1 reasoning
- data_ops: Olist data queries via DuckDB
- rag: SOP document retrieval
- tools: inspection task CRUD

It exposes the LangGraph state graph and the Streamlit UI.
"""

__all__: list[str] = []
