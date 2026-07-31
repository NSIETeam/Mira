from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from mira.agent.save_turn import SaveTurnHandler
from mira.agent.turn_context import TurnContext, TurnKind, TurnState
from mira.agent.turn_delivery import TurnDelivery
from mira.bus.events import InboundMessage
from mira.session.manager import Session
from mira.utils.llm_runtime import LLMRuntime
from mira.utils.runtime import EMPTY_FINAL_RESPONSE_MESSAGE


class _Delivery:
    def __init__(self) -> None:
        self.latency_ms: int | None = None

    def record_latency(self, latency_ms: int) -> None:
        self.latency_ms = latency_ms


class _Consolidator:
    async def maybe_consolidate_by_tokens(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _Sessions:
    def __init__(self) -> None:
        self.saved: list[str] = []

    def save(self, session: Session) -> None:
        self.saved.append(session.key)


class _Loop:
    def __init__(self) -> None:
        self.sessions = _Sessions()
        self.saved_turns: list[dict[str, Any]] = []
        self.cleared_pending: list[str] = []
        self.cleared_runtime: list[str] = []

    def _save_turn(
        self,
        session: Session,
        messages: list[dict[str, Any]],
        skip: int,
        *,
        turn_latency_ms: int | None,
    ) -> None:
        self.saved_turns.append(
            {
                "session": session.key,
                "messages": messages,
                "skip": skip,
                "turn_latency_ms": turn_latency_ms,
            }
        )

    def _memory_store_for_metadata(self, metadata: dict[str, Any]) -> Any:
        return SimpleNamespace(raw_archive=lambda **_kwargs: None)

    def _consolidator_for_metadata(self, metadata: dict[str, Any]) -> _Consolidator:
        return _Consolidator()

    def _schedule_background(self, awaitable: Any) -> None:
        awaitable.close()

    def _clear_pending_user_turn(self, session: Session) -> None:
        self.cleared_pending.append(session.key)

    def _clear_runtime_checkpoint(self, session: Session) -> None:
        self.cleared_runtime.append(session.key)


@pytest.mark.asyncio
async def test_save_turn_persists_latency_and_clears_recovery_state() -> None:
    loop = _Loop()
    session = Session("cli:chat")
    delivery = _Delivery()
    runtime = cast(LLMRuntime, SimpleNamespace(context_window_tokens=1000))
    ctx = TurnContext(
        msg=InboundMessage(channel="cli", sender_id="user", chat_id="chat", content="hi"),
        session_key=session.key,
        state=TurnState.SAVE,
        turn_id="turn-1",
        runtime=runtime,
        kind=TurnKind.USER,
        delivery=cast(TurnDelivery, delivery),
        session=session,
        final_content="",
        all_messages=[{"role": "assistant", "content": "saved"}],
    )

    event = await SaveTurnHandler(loop).handle(ctx, session=session, runtime=runtime)

    assert event == "ok"
    assert ctx.final_content == EMPTY_FINAL_RESPONSE_MESSAGE
    assert isinstance(ctx.turn_latency_ms, int)
    assert delivery.latency_ms == ctx.turn_latency_ms
    assert loop.saved_turns[0]["messages"] == [{"role": "assistant", "content": "saved"}]
    assert loop.cleared_pending == ["cli:chat"]
    assert loop.cleared_runtime == ["cli:chat"]
    assert loop.sessions.saved == ["cli:chat"]
