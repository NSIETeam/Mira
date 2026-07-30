from __future__ import annotations

from typing import Any

from mira.providers import registry as provider_registry
from mira.providers.registry import ProviderSpec


class _FakeEntryPoint:
    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self._value = value

    def load(self) -> Any:
        return self._value


def test_discovers_external_provider_specs(monkeypatch) -> None:
    provider_registry.provider_specs.cache_clear()
    spec = ProviderSpec(
        name="acme",
        keywords=("acme",),
        env_key="ACME_API_KEY",
        display_name="Acme",
    )

    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        if group == "mira.providers":
            return [_FakeEntryPoint("acme", spec)]
        return []

    monkeypatch.setattr(provider_registry, "entry_points", fake_entry_points)

    try:
        assert provider_registry.find_by_name("acme") is spec
        assert spec in provider_registry.provider_specs()
    finally:
        provider_registry.provider_specs.cache_clear()


def test_discovers_unified_provider_plugin_specs(monkeypatch) -> None:
    provider_registry.provider_specs.cache_clear()
    spec = ProviderSpec(
        name="acme",
        keywords=("acme",),
        env_key="ACME_API_KEY",
        display_name="Acme",
    )

    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        if group == "mira.plugins":
            return [
                _FakeEntryPoint("provider-acme", lambda: spec),
                _FakeEntryPoint("channel-ignored", object()),
            ]
        return []

    monkeypatch.setattr(provider_registry, "entry_points", fake_entry_points)

    try:
        assert provider_registry.find_by_name("acme") is spec
        assert provider_registry.find_by_name("channel_ignored") is None
    finally:
        provider_registry.provider_specs.cache_clear()
