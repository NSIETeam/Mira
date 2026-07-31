from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from mira.agent.run_turn import RunTurnHandler
from mira.agent.turn_context import TurnContext, TurnKind, TurnState
from mira.agent.turn_delivery import TurnDelivery
from mira.bus.events import InboundMessage
from mira.session.manager import Session
from mira.utils.llm_runtime import LLMRuntime


class _Delivery:
    route = SimpleNamespace(channel="cli", chat_id="chat")

    def __init__(self) -> None:
        self.started_at: float | None = None

    async def running(self, *, started_at: float) -> None:
        self.started_at = started_at


class _Loop:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def _run_agent_loop(
        self,
        initial_messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> tuple[str, list[str], list[dict[str, Any]], str, bool]:
        self.calls.append({"initial_messages": initial_messages, **kwargs})
        return (
            "final",
            ["shell"],
            [*initial_messages, {"role": "assistant", "content": "final"}],
            "stop",
            True,
        )


@pytest.mark.asyncio
async def test_run_turn_calls_runner_and_records_result() -> None:
    loop = _Loop()
    session = Session("cli:chat")
    runtime = cast(LLMRuntime, SimpleNamespace(model="test-model"))
    delivery = _Delivery()
    ctx = TurnContext(
        msg=InboundMessage(
            channel="cli",
            sender_id="system",
            chat_id="chat",
            content="run",
            metadata={"message_id": "m1"},
        ),
        session_key=session.key,
        state=TurnState.RUN,
        turn_id="turn-1",
        runtime=runtime,
        kind=TurnKind.SYSTEM,
        delivery=cast(TurnDelivery, delivery),
        session=session,
        initial_messages=[{"role": "user", "content": "run"}],
    )

    event = await RunTurnHandler(loop).handle(ctx, runtime=runtime, session=session)

    assert event == "ok"
    assert delivery.started_at is not None
    assert ctx.final_content == "final"
    assert ctx.tools_used == ["shell"]
    assert ctx.all_messages[-1] == {"role": "assistant", "content": "final"}
    assert ctx.stop_reason == "stop"
    assert ctx.had_injections is True
    assert loop.calls[0]["runtime"] is runtime
    assert loop.calls[0]["session"] is session
    assert loop.calls[0]["message_id"] == "m1"
