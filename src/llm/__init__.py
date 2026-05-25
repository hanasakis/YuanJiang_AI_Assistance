"""llm — Ollama DeepSeek-R1 inference, prompt templates, and output cleaning.

Responsibilities:
- Wrap ollama Python client for chat completion
- Manage system prompts and few-shot templates
- Strip <｜end▁of▁thinking｜> thinking chain wrappers from raw R1 output
- Token budgeting and context window management

Runtime model: local Ollama deepseek-r1:8b (never cloud / API).
"""

__all__: list[str] = []
