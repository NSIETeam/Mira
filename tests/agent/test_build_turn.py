from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from mira.agent.build_turn import BuildTurnHandler
from mira.agent.tools.context import RequestContext
from mira.agent.tools.registry import ToolRegistry
from mira.agent.turn_context import TurnContext, TurnKind, TurnState
from mira.agent.turn_delivery import TurnDelivery
from mira.bus.events import InboundMessage
from mira.session.manager import Session
from mira.utils.llm_runtime import LLMRuntime


class _Delivery:
    def __init__(self) -> None:
        self.runtime: Any = None

    def record_runtime(self, runtime: Any) -> None:
        self.runtime = runtime

    def progress_callback(self) -> object:
        return object()

    def retry_wait_callback(self) -> object:
        return object()


class _Consolidator:
    def __init__(self) -> None:
        self.calls: list[tuple[Session, Any, int]] = []

    async def maybe_consolidate_by_tokens(
        self,
        session: Session,
        *,
        runtime: Any,
        replay_max_messages: int,
    ) -> None:
        self.calls.append((session, runtime, replay_max_messages))


class _Loop:
    def __init__(self) -> None:
        self.runtime = cast(LLMRuntime, SimpleNamespace(context_window_tokens=1000))
        self.consolidator = _Consolidator()
        self.tools = ToolRegistry()
        self.saved_sessions: list[str] = []

    def runtime_for_session(self, session: Session) -> LLMRuntime:
        return self.runtime

    def _consolidator_for_metadata(self, metadata: dict[str, Any]) -> _Consolidator:
        return self.consolidator

    def _replay_token_budget(self, runtime: LLMRuntime) -> int:
        return 900

    def _page_virtual_context_history(
        self,
        history: list[dict[str, Any]],
        *,
        budget_tokens: int,
        session_key: str,
    ) -> list[dict[str, Any]]:
        return [*history, {"role": "system", "content": f"budget:{budget_tokens}:{session_key}"}]

    def _tools_for_metadata(self, metadata: dict[str, Any]) -> ToolRegistry:
        return self.tools

    def _request_context_for_turn(self, ctx: TurnContext) -> RequestContext:
        return RequestContext(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            session_key=ctx.session_key,
        )

    async def _resolve_runtime_context_for_turn(self, ctx: TurnContext) -> list[Any]:
        return [{"kind": "runtime"}]

    def _build_initial_messages(self, ctx: TurnContext) -> list[dict[str, Any]]:
        return [*ctx.history, {"role": "user", "content": ctx.msg.content}]

    def _persist_user_message_early(
        self,
        msg: InboundMessage,
        session: Session,
        *,
        runtime_context_blocks: list[Any],
    ) -> bool:
        session.add_message("user", msg.content, runtime_context_blocks=runtime_context_blocks)
        return True


@pytest.mark.asyncio
async def test_build_turn_prepares_runtime_history_prompt_and_callbacks() -> None:
    loop = _Loop()
    session = Session("cli:chat")
    session.add_message("user", "old")
    delivery = _Delivery()
    ctx = TurnContext(
        msg=InboundMessage(channel="cli", sender_id="user", chat_id="chat", content="new"),
        session_key=session.key,
        state=TurnState.BUILD,
        turn_id="turn-1",
        runtime=None,
        kind=TurnKind.USER,
        delivery=cast(TurnDelivery, delivery),
        session=session,
    )

    event = await BuildTurnHandler(loop).handle(ctx, session)

    assert event == "ok"
    assert ctx.runtime is loop.runtime
    assert delivery.runtime is loop.runtime
    assert ctx.history[-1]["content"] == "budget:900:cli:chat"
    assert ctx.request_context is not None
    assert ctx.request_context.session_key == "cli:chat"
    assert ctx.runtime_context_blocks == [{"kind": "runtime"}]
    assert ctx.initial_messages[-1] == {"role": "user", "content": "new"}
    assert ctx.input_persisted_early is True
    assert ctx.on_progress is not None
    assert ctx.on_retry_wait is not None
    assert loop.consolidator.calls[0][0] is session
