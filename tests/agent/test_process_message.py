from __future__ import annotations

from typing import Any

import pytest

from mira.agent.process_message import process_inbound_message
from mira.agent.turn_context import TurnContext, TurnState
from mira.bus.events import InboundMessage, OutboundMessage


class _Delivery:
    def __init__(self, session_key: str) -> None:
        self.session_key = session_key
        self.streamed: list[str] = []
        self.stream_ends: list[dict[str, Any]] = []

    async def on_stream(self, delta: str) -> None:
        self.streamed.append(delta)

    async def on_stream_end(self, **kwargs: Any) -> None:
        self.stream_ends.append(kwargs)


class _DeliveryFactory:
    def __init__(self) -> None:
        self.created: list[tuple[InboundMessage, str]] = []
        self.delivery: _Delivery | None = None

    def create(self, msg: InboundMessage, session_key: str) -> _Delivery:
        self.created.append((msg, session_key))
        self.delivery = _Delivery(session_key)
        return self.delivery


class _Loop:
    _TRANSITIONS = {
        (TurnState.RESTORE, "ok"): TurnState.RUN,
        (TurnState.RUN, "ok"): TurnState.RESPOND,
        (TurnState.RESPOND, "ok"): TurnState.DONE,
    }

    def __init__(self) -> None:
        self.turn_delivery_factory = _DeliveryFactory()
        self.seen: list[tuple[TurnState, str]] = []
        self.respond_ctx: TurnContext | None = None

    async def _state_restore(self, ctx: TurnContext) -> str:
        self.seen.append((ctx.state, ctx.session_key))
        return "ok"

    async def _state_run(self, ctx: TurnContext) -> str:
        assert ctx.on_stream is not None
        assert ctx.on_stream_end is not None
        await ctx.on_stream("visible")
        await ctx.on_stream_end(resuming=True, merge_next=True)
        self.seen.append((ctx.state, ctx.session_key))
        return "ok"

    async def _state_respond(self, ctx: TurnContext) -> str:
        ctx.outbound = OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="done",
        )
        self.respond_ctx = ctx
        self.seen.append((ctx.state, ctx.session_key))
        return "ok"


@pytest.mark.asyncio
async def test_process_inbound_message_drives_state_machine_and_tracks_streaming() -> None:
    loop = _Loop()
    msg = InboundMessage(channel="cli", sender_id="user", chat_id="chat", content="hello")

    response = await process_inbound_message(loop, msg)

    assert response is not None
    assert response.content == "done"
    assert loop.turn_delivery_factory.created == [(msg, msg.session_key)]
    assert loop.seen == [
        (TurnState.RESTORE, msg.session_key),
        (TurnState.RUN, msg.session_key),
        (TurnState.RESPOND, msg.session_key),
    ]
    assert loop.respond_ctx is not None
    assert loop.respond_ctx.streamed_content is True
    assert [entry.state for entry in loop.respond_ctx.trace] == [
        TurnState.RESTORE,
        TurnState.RUN,
        TurnState.RESPOND,
    ]
    assert loop.turn_delivery_factory.delivery is not None
    assert loop.turn_delivery_factory.delivery.streamed == ["visible"]
    assert loop.turn_delivery_factory.delivery.stream_ends == [
        {"resuming": True, "merge_next": True},
    ]


@pytest.mark.asyncio
async def test_process_inbound_message_rejects_mismatched_delivery_session() -> None:
    loop = _Loop()
    msg = InboundMessage(channel="cli", sender_id="user", chat_id="chat", content="hello")

    with pytest.raises(ValueError, match="turn delivery session"):
        await process_inbound_message(loop, msg, delivery=_Delivery("other-session"))
