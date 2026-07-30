from __future__ import annotations

from typing import cast

import pytest

from mira.agent.respond_turn import RespondTurnHandler
from mira.agent.turn_context import TurnContext, TurnKind, TurnState
from mira.agent.turn_delivery import TurnDelivery
from mira.bus.events import InboundMessage, OutboundMessage


class _Delivery:
    def background_response(
        self,
        content: str | None,
        *,
        stop_reason: str,
        streamed: bool,
        latency_ms: int | None,
    ) -> OutboundMessage:
        return OutboundMessage(
            channel="cli",
            chat_id="chat",
            content=content or "done",
            metadata={
                "stop_reason": stop_reason,
                "streamed": streamed,
                "latency_ms": latency_ms,
            },
        )


def _ctx(*, kind: TurnKind = TurnKind.USER) -> TurnContext:
    return TurnContext(
        msg=InboundMessage(channel="cli", sender_id="user", chat_id="chat", content="hi"),
        session_key="cli:chat",
        state=TurnState.RESPOND,
        turn_id="turn-1",
        runtime=None,
        kind=kind,
        delivery=cast(TurnDelivery, _Delivery()),
        final_content="final",
        stop_reason="stop",
        turn_latency_ms=42,
    )


@pytest.mark.asyncio
async def test_respond_turn_suppresses_response() -> None:
    ctx = _ctx()
    ctx.suppress_response = True

    event = await RespondTurnHandler(lambda _ctx: None).handle(ctx)

    assert event == "ok"
    assert ctx.outbound is None


@pytest.mark.asyncio
async def test_respond_turn_uses_background_response_for_system_turn() -> None:
    ctx = _ctx(kind=TurnKind.SYSTEM)
    ctx.streamed_content = True

    event = await RespondTurnHandler(lambda _ctx: None).handle(ctx)

    assert event == "ok"
    assert ctx.outbound is not None
    assert ctx.outbound.content == "final"
    assert ctx.outbound.metadata["stop_reason"] == "stop"
    assert ctx.outbound.metadata["streamed"] is True
    assert ctx.outbound.metadata["latency_ms"] == 42


@pytest.mark.asyncio
async def test_respond_turn_adds_ephemeral_stop_reason_to_user_response() -> None:
    ctx = _ctx()
    ctx.ephemeral = True

    def assemble(_ctx: TurnContext) -> OutboundMessage:
        return OutboundMessage(channel="cli", chat_id="chat", content="assembled")

    event = await RespondTurnHandler(assemble).handle(ctx)

    assert event == "ok"
    assert ctx.outbound is not None
    assert ctx.outbound.content == "assembled"
    assert ctx.outbound.metadata["_stop_reason"] == "stop"
