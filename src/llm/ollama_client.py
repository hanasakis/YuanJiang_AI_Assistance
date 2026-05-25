"""Ollama DeepSeek-R1 client wrapper.

Reads OLLAMA_BASE_URL and OLLAMA_MODEL from environment.
Default model is deepseek-r1:8b (local-only, never cloud).
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from ollama import Client


class OllamaConnectionError(Exception):
    """Raised when the Ollama server is unreachable."""


class OllamaTimeoutError(Exception):
    """Raised when an Ollama request exceeds the configured timeout."""


def _env(key: str, fallback: str) -> str:
    value = os.getenv(key, "").strip()
    return value if value else fallback


OLLAMA_BASE_URL: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = _env("OLLAMA_MODEL", "deepseek-r1:8b")

_client: Client | None = None


def get_client() -> Client:
    """Return a singleton Ollama client, lazily created."""
    global _client
    if _client is None:
        _client = Client(host=OLLAMA_BASE_URL)
    return _client


def chat(
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    model: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Send a chat completion request to the local Ollama server.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        temperature: Sampling temperature (default 0.1 for deterministic).
        model: Override the default model. If None, uses OLLAMA_MODEL env var.
        timeout: Request timeout in seconds.

    Returns:
        The Ollama response dict with keys: model, message, done, ...
        message.content contains the model's text reply.

    Raises:
        OllamaConnectionError: If Ollama server is unreachable.
        OllamaTimeoutError: If the request exceeds the timeout.
        RuntimeError: For other unexpected errors.
    """
    selected_model = model or OLLAMA_MODEL

    try:
        client = get_client()
        response = client.chat(
            model=selected_model,
            messages=messages,
            options={"temperature": temperature},
            stream=False,
        )
        return response

    except httpx.ConnectError:
        raise OllamaConnectionError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
            f"Is the server running? Try: ollama serve"
        )
    except httpx.ReadTimeout:
        raise OllamaTimeoutError(
            f"Ollama request timed out after {timeout}s. "
            f"Model '{selected_model}' may be too large or the prompt too long."
        )
    except Exception as exc:
        raise RuntimeError(
            f"Unexpected Ollama error: {type(exc).__name__}: {exc}"
        ) from exc


def get_model_info() -> dict[str, str]:
    """Return the current Ollama connection configuration.

    Does NOT make a network call — only reports env-configured values.
    """
    return {
        "base_url": OLLAMA_BASE_URL,
        "model": OLLAMA_MODEL,
    }
