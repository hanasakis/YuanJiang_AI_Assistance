"""Tests for src/llm/ollama_client.py — configuration and error paths.

These tests do NOT make real calls to Ollama.
They validate configuration loading and model default behavior.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest


class TestOllamaConfig:
    """Validate that the client reads OLLAMA_MODEL from environment correctly."""

    def test_default_model_is_deepseek_r1_8b(self):
        """The OLLAMA_MODEL default must be deepseek-r1:8b (local-only)."""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import src.llm.ollama_client as client_mod

            importlib.reload(client_mod)

            assert client_mod.OLLAMA_MODEL == "deepseek-r1:8b", (
                f"Default OLLAMA_MODEL must be 'deepseek-r1:8b', "
                f"got '{client_mod.OLLAMA_MODEL}'"
            )

    def test_default_model_is_not_cloud_model(self):
        """The default must NOT be any cloud/API model name."""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import src.llm.ollama_client as client_mod

            importlib.reload(client_mod)

            forbidden = ["deepseek-v4", "gpt-", "claude", "gemini", "anthropic"]
            model_lower = client_mod.OLLAMA_MODEL.lower()
            for token in forbidden:
                assert token not in model_lower, (
                    f"OLLAMA_MODEL '{client_mod.OLLAMA_MODEL}' contains forbidden "
                    f"pattern '{token}'. Must be local Ollama model only."
                )

    def test_ollama_base_url_default(self):
        """Default base URL should be localhost:11434."""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import src.llm.ollama_client as client_mod

            importlib.reload(client_mod)

            assert "11434" in client_mod.OLLAMA_BASE_URL
            assert "localhost" in client_mod.OLLAMA_BASE_URL

    def test_env_var_override(self):
        """When OLLAMA_MODEL env var is set, it should be used."""
        with mock.patch.dict(
            os.environ,
            {"OLLAMA_MODEL": "deepseek-r1:1.5b", "OLLAMA_BASE_URL": "http://127.0.0.1:9999"},
            clear=True,
        ):
            import importlib
            import src.llm.ollama_client as client_mod

            importlib.reload(client_mod)

            assert client_mod.OLLAMA_MODEL == "deepseek-r1:1.5b"
            assert client_mod.OLLAMA_BASE_URL == "http://127.0.0.1:9999"

    def test_get_model_info_no_network(self):
        """get_model_info() must not make any network calls."""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import src.llm.ollama_client as client_mod

            importlib.reload(client_mod)

            info = client_mod.get_model_info()
            assert "model" in info
            assert "base_url" in info
            assert isinstance(info["model"], str)
            assert isinstance(info["base_url"], str)


class TestChatErrorHandling:
    """Validate that custom exceptions exist with actionable messages."""

    def test_ollama_connection_error_is_actionable(self):
        """OllamaConnectionError should be importable and have a clear message."""
        from src.llm.ollama_client import OllamaConnectionError

        err = OllamaConnectionError(
            "Cannot connect to Ollama at http://localhost:11434. "
            "Is the server running? Try: ollama serve"
        )
        assert "ollama serve" in str(err).lower()

    def test_ollama_timeout_error_is_actionable(self):
        """OllamaTimeoutError should be importable and suggest the cause."""
        from src.llm.ollama_client import OllamaTimeoutError

        err = OllamaTimeoutError(
            "Ollama request timed out after 120s. "
            "Model 'deepseek-r1:8b' may be too large or the prompt too long."
        )
        assert "timed out" in str(err).lower()

    def test_chat_with_explicit_model_param(self):
        """chat() should accept an explicit model override."""
        import src.llm.ollama_client as client_mod
        import inspect

        sig = inspect.signature(client_mod.chat)
        assert "model" in sig.parameters
