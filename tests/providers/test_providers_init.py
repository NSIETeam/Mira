"""Tests for lazy provider exports from mira.providers."""

from __future__ import annotations

import importlib
import sys


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    original_package = sys.modules["mira.providers"]
    monkeypatch.delitem(sys.modules, "mira.providers", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.anthropic_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.openai_compat_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.openai_codex_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.xai_oauth", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.xai_grok_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.github_copilot_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.azure_openai_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.bedrock_provider", raising=False)

    try:
        providers = importlib.import_module("mira.providers")

        assert "mira.providers.anthropic_provider" not in sys.modules
        assert "mira.providers.openai_compat_provider" not in sys.modules
        assert "mira.providers.openai_codex_provider" not in sys.modules
        assert "mira.providers.xai_oauth" not in sys.modules
        assert "mira.providers.xai_grok_provider" not in sys.modules
        assert "mira.providers.github_copilot_provider" not in sys.modules
        assert "mira.providers.azure_openai_provider" not in sys.modules
        assert "mira.providers.bedrock_provider" not in sys.modules
        assert providers.__all__ == [
            "LLMProvider",
            "LLMResponse",
            "AnthropicProvider",
            "OpenAICompatProvider",
            "OpenAICodexProvider",
            "XAIGrokProvider",
            "GitHubCopilotProvider",
            "AzureOpenAIProvider",
            "BedrockProvider",
        ]
    finally:
        # Importing a replacement subpackage also replaces mira.providers on the
        # parent package. Restore both views so this isolation test cannot pollute
        # later tests that resolve a module through a dotted monkeypatch target.
        monkeypatch.undo()
        setattr(sys.modules["mira"], "providers", original_package)


def test_explicit_provider_import_still_works(monkeypatch) -> None:
    original_package = sys.modules["mira.providers"]
    monkeypatch.delitem(sys.modules, "mira.providers", raising=False)
    monkeypatch.delitem(sys.modules, "mira.providers.anthropic_provider", raising=False)

    try:
        namespace: dict[str, object] = {}
        exec("from mira.providers import AnthropicProvider", namespace)

        assert namespace["AnthropicProvider"].__name__ == "AnthropicProvider"
        assert "mira.providers.anthropic_provider" in sys.modules
    finally:
        monkeypatch.undo()
        setattr(sys.modules["mira"], "providers", original_package)


def test_openai_codex_supports_progress_deltas() -> None:
    from mira.providers.openai_codex_provider import OpenAICodexProvider

    assert OpenAICodexProvider.supports_progress_deltas is True
