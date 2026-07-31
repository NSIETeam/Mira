from __future__ import annotations

from typing import cast

from mira.agent.turn_context import StateTraceEntry, TurnContext, TurnKind, TurnState
from mira.agent.turn_delivery import TurnDelivery
from mira.bus.events import InboundMessage


def test_turn_context_keeps_independent_turn_state() -> None:
    msg = InboundMessage(channel="cli", sender_id="user", chat_id="chat", content="hello")
    ctx = TurnContext(
        msg=msg,
        session_key="cli:chat",
        state=TurnState.RESTORE,
        turn_id="turn-1",
        runtime=None,
        kind=TurnKind.USER,
        delivery=cast(TurnDelivery, object()),
    )

    ctx.trace.append(
        StateTraceEntry(
            state=TurnState.RESTORE,
            started_at=1.0,
            duration_ms=2.5,
            event="ok",
        )
    )

    assert ctx.msg is msg
    assert ctx.history == []
    assert ctx.trace[0].state is TurnState.RESTORE
    assert ctx.trace[0].event == "ok"
