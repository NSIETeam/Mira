from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from mira.config.schema import Config
from mira.providers import factory as provider_factory
from mira.providers.base import LLMProvider, LLMResponse
from mira.providers.registry import ProviderSpec


class _ExternalProvider(LLMProvider):
    def __init__(self, *, default_model: str, received: dict[str, Any]) -> None:
        super().__init__()
        self.default_model = default_model
        self.received = received

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="ok", model=model or self.default_model)

    def get_default_model(self) -> str:
        return self.default_model


def test_make_provider_uses_external_provider_factory(monkeypatch) -> None:
    module = types.ModuleType("_mira_external_provider_test")
    captured: dict[str, Any] = {}

    def create_provider(**kwargs: Any) -> _ExternalProvider:
        captured.update(kwargs)
        return _ExternalProvider(default_model=kwargs["model"], received=kwargs)

    module.create_provider = create_provider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)

    spec = ProviderSpec(
        name="acme",
        keywords=("acme",),
        env_key="ACME_API_KEY",
        display_name="Acme",
        provider_factory=f"{module.__name__}:create_provider",
    )
    monkeypatch.setattr(provider_factory, "find_by_name", lambda name: spec if name == "acme" else None)
    config = Config.model_validate(
        {
            "agents": {"defaults": {"modelPreset": "primary"}},
            "modelPresets": {
                "primary": {
                    "model": "acme/model-1",
                    "provider": "acme",
                    "temperature": 0.2,
                }
            },
            "providers": {"acme": {"apiKey": "sk-acme"}},
        }
    )

    provider = provider_factory.make_provider(config)

    assert isinstance(provider, _ExternalProvider)
    assert provider.get_default_model() == "acme/model-1"
    assert provider.generation.temperature == 0.2
    assert captured["spec"] is spec
    assert captured["provider_config"].api_key == "sk-acme"
    assert captured["preset"].model == "acme/model-1"


def test_make_provider_rejects_invalid_external_provider_factory(monkeypatch) -> None:
    spec = ProviderSpec(
        name="acme",
        keywords=("acme",),
        env_key="ACME_API_KEY",
        display_name="Acme",
        provider_factory="missing-separator",
    )
    monkeypatch.setattr(provider_factory, "find_by_name", lambda name: spec if name == "acme" else None)
    config = Config.model_validate(
        {
            "agents": {"defaults": {"modelPreset": "primary"}},
            "modelPresets": {"primary": {"model": "acme/model-1", "provider": "acme"}},
            "providers": {"acme": {"apiKey": "sk-acme"}},
        }
    )

    with pytest.raises(RuntimeError, match="Invalid provider factory path"):
        provider_factory.make_provider(config)
