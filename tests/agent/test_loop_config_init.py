from __future__ import annotations

import pytest

from mira.agent.loop import AgentLoop, AgentLoopConfig
from mira.bus.queue import MessageBus
from mira.providers.base import LLMProvider


class FakeProvider(LLMProvider):
    def __init__(self, default_model: str = "test-model") -> None:
        self._default_model = default_model

    def get_default_model(self) -> str:
        return self._default_model

    async def chat(self, *args, **kwargs):  # pragma: no cover - not used by these tests
        raise AssertionError("chat should not be called")


def test_agent_loop_accepts_config_object(tmp_path):
    bus = MessageBus()
    provider = FakeProvider()

    loop = AgentLoop(
        config=AgentLoopConfig(
            bus=bus,
            provider=provider,
            workspace=tmp_path,
            model="configured-model",
            context_window_tokens=4096,
        )
    )

    assert loop.bus is bus
    assert loop.model == "configured-model"
    assert loop.context_window_tokens == 4096


def test_agent_loop_keeps_legacy_positional_compatibility(tmp_path):
    bus = MessageBus()
    provider = FakeProvider()

    loop = AgentLoop(bus, provider, tmp_path, model="legacy-model")

    assert loop.bus is bus
    assert loop.model == "legacy-model"


def test_agent_loop_rejects_mixed_config_and_legacy_args(tmp_path):
    config = AgentLoopConfig(
        bus=MessageBus(),
        provider=FakeProvider(),
        workspace=tmp_path,
    )

    with pytest.raises(TypeError, match="either config=AgentLoopConfig or legacy"):
        AgentLoop(MessageBus(), config=config)
