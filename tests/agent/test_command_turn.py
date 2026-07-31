from __future__ import annotations

from typing import Any, cast

import pytest

from mira.agent.command_turn import CommandTurnHandler
from mira.agent.turn_context import TurnContext, TurnKind, TurnState
from mira.agent.turn_delivery import TurnDelivery
from mira.bus.events import InboundMessage, OutboundMessage
from mira.command import CommandContext, CommandRouter
from mira.session.manager import Session


def _ctx(content: str) -> TurnContext:
    msg = InboundMessage(channel="cli", sender_id="user", chat_id="chat", content=content)
    return TurnContext(
        msg=msg,
        session_key="cli:chat",
        state=TurnState.COMMAND,
        turn_id="turn-1",
        runtime=None,
        kind=TurnKind.USER,
        delivery=cast(TurnDelivery, object()),
        original_user_text=content,
        session=Session("cli:chat"),
    )


def _handler(router: CommandRouter, calls: dict[str, Any]) -> CommandTurnHandler:
    def persist_user_message(
        msg: InboundMessage,
        session: Session,
        **kwargs: Any,
    ) -> bool:
        calls["persist"] = (msg.content, kwargs)
        session.add_message("user", msg.content, **kwargs)
        return True

    def save_session(session: Session) -> None:
        calls["saved"] = session.key

    def clear_pending_user_turn(session: Session) -> None:
        calls["cleared"] = session.key

    return CommandTurnHandler(
        commands=router,
        loop=object(),
        persist_user_message=persist_user_message,
        save_session=save_session,
        clear_pending_user_turn=clear_pending_user_turn,
    )


@pytest.mark.asyncio
async def test_command_turn_dispatches_plain_text() -> None:
    router = CommandRouter()
    calls: dict[str, Any] = {}
    ctx = _ctx("plain text")

    result = await _handler(router, calls).handle(ctx, cast(Session, ctx.session))

    assert result.event == "dispatch"
    assert ctx.outbound is None
    assert calls == {}


@pytest.mark.asyncio
async def test_command_turn_shortcut_persists_command_response() -> None:
    router = CommandRouter()

    async def ping(ctx: CommandContext) -> OutboundMessage:
        return OutboundMessage(channel=ctx.msg.channel, chat_id=ctx.msg.chat_id, content="pong")

    router.exact("/ping", ping)
    calls: dict[str, Any] = {}
    ctx = _ctx("/ping")

    result = await _handler(router, calls).handle(ctx, cast(Session, ctx.session))

    assert result.event == "shortcut"
    assert result.input_persisted_early is True
    assert ctx.outbound is not None
    assert ctx.outbound.content == "pong"
    assert ctx.session is not None
    assert [(m["role"], m["content"], m["_command"]) for m in ctx.session.messages] == [
        ("user", "/ping", True),
        ("assistant", "pong", True),
    ]
    assert calls["persist"] == ("/ping", {"_command": True})
    assert calls["saved"] == "cli:chat"
    assert calls["cleared"] == "cli:chat"
