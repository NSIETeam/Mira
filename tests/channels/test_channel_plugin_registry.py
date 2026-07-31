from __future__ import annotations

from typing import Any

from mira.channels import registry as channel_registry
from mira.channels.plugin import ChannelPlugin


class _FakeEntryPoint:
    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self._value = value

    def load(self) -> Any:
        return self._value


def test_discovers_external_channel_plugin_entry_points(monkeypatch) -> None:
    plugin = ChannelPlugin(
        name="acme",
        display_name="Acme",
        runtime="mira_channel_acme.runtime:AcmeChannel",
    )

    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        if group == "mira.channel_plugins":
            return [_FakeEntryPoint("acme", plugin)]
        return []

    monkeypatch.setattr(channel_registry, "entry_points", fake_entry_points)
    monkeypatch.setattr(channel_registry, "_channel_package_names", lambda: [])

    plugins = channel_registry.discover_plugins()

    assert plugins["acme"] is plugin


def test_discovers_unified_channel_plugin_entry_points(monkeypatch) -> None:
    plugin = ChannelPlugin(
        name="acme",
        display_name="Acme",
        runtime="mira_channel_acme.runtime:AcmeChannel",
    )

    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        if group == "mira.plugins":
            return [
                _FakeEntryPoint("channel-acme", lambda: plugin),
                _FakeEntryPoint("provider-ignored", object()),
            ]
        return []

    monkeypatch.setattr(channel_registry, "entry_points", fake_entry_points)
    monkeypatch.setattr(channel_registry, "_channel_package_names", lambda: [])

    plugins = channel_registry.discover_plugins()

    assert plugins["acme"] is plugin
    assert "provider_ignored" not in plugins
