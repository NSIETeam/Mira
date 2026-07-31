"""Turn state-machine driver for inbound messages."""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from mira.agent.hook import AgentHook, AgentTurnHookFactory
from mira.agent.tools.registry import ToolRegistry
from mira.agent.turn_context import (
    StateTraceEntry,
    TurnContext,
    TurnKind,
    TurnState,
)
from mira.agent.turn_delivery import TurnDelivery
from mira.bus.events import InboundMessage, OutboundMessage
from mira.session import turn_continuation
from mira.utils.llm_runtime import LLMRuntime
from mira.utils.logging import turn_logger


def _ctx_logger(ctx: TurnContext) -> Any:
    return turn_logger(ctx.session_key, ctx.turn_id)


def _message_session_key(msg: InboundMessage, session_key: str | None, kind: TurnKind) -> str:
    if kind is TurnKind.SYSTEM:
        destination = msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id)
        return session_key or msg.session_key_override or f"{destination[0]}:{destination[1]}"
    return session_key or msg.session_key


def _stream_end_accepts_merge_next(callback: Callable[..., Awaitable[None]] | None) -> bool:
    if callback is None:
        return False
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return False
    return "merge_next" in signature.parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _track_streamed_content(ctx: TurnContext) -> None:
    """Track whether the latest streamed segment emitted visible content."""
    if ctx.on_stream is None:
        return

    stream_callback = ctx.on_stream
    stream_end_callback = ctx.on_stream_end
    stream_end_accepts_merge_next = _stream_end_accepts_merge_next(stream_end_callback)
    segment_streamed_content = False

    async def _tracked_stream(delta: str) -> None:
        nonlocal segment_streamed_content
        if delta:
            segment_streamed_content = True
        await stream_callback(delta)

    async def _tracked_stream_end(
        *,
        resuming: bool = False,
        merge_next: bool = False,
    ) -> None:
        nonlocal segment_streamed_content
        ctx.streamed_content = segment_streamed_content
        segment_streamed_content = False
        if stream_end_callback is not None:
            if merge_next and stream_end_accepts_merge_next:
                await stream_end_callback(resuming=resuming, merge_next=True)
            else:
                await stream_end_callback(resuming=resuming)

    ctx.on_stream = _tracked_stream
    ctx.on_stream_end = _tracked_stream_end


async def process_inbound_message(
    loop: Any,
    msg: InboundMessage,
    session_key: str | None = None,
    on_progress: Callable[..., Awaitable[None]] | None = None,
    on_stream: Callable[[str], Awaitable[None]] | None = None,
    on_stream_end: Callable[..., Awaitable[None]] | None = None,
    pending_queue: Any = None,
    ephemeral: bool = False,
    run_extra_hooks_for_ephemeral: bool = False,
    hooks: list[AgentHook] | None = None,
    hook_factories: list[AgentTurnHookFactory] | None = None,
    tools: ToolRegistry | None = None,
    runtime: LLMRuntime | None = None,
    delivery: TurnDelivery | None = None,
    on_runtime_admitted: Callable[[LLMRuntime], Awaitable[None]] | None = None,
) -> OutboundMessage | None:
    """Process a single inbound message through the loop state machine."""
    kind = TurnKind.SYSTEM if msg.channel == "system" else TurnKind.USER
    key = _message_session_key(msg, session_key, kind)
    if delivery is None:
        delivery = loop.turn_delivery_factory.create(msg, key)
    elif delivery.session_key != key:
        raise ValueError("turn delivery session does not match the processing session")
    if on_stream is None:
        on_stream = delivery.on_stream
    if on_stream_end is None:
        on_stream_end = delivery.on_stream_end

    t0 = time.time()
    ctx = TurnContext(
        msg=msg,
        session=None,
        session_key=key,
        state=TurnState.RESTORE,
        turn_id=f"{key}:{time.time_ns()}",
        runtime=runtime,
        kind=kind,
        delivery=delivery,
        original_user_text=(
            None
            if kind is TurnKind.SYSTEM
            or turn_continuation.internal_continuation_inbound(msg.metadata)
            else msg.content
        ),
        turn_wall_started_at=t0,
        visible_run_started_at=turn_continuation.internal_continuation_run_started_at(
            msg.metadata,
        ),
        on_progress=on_progress,
        on_stream=on_stream,
        on_stream_end=on_stream_end,
        on_runtime_admitted=on_runtime_admitted,
        pending_queue=pending_queue,
        ephemeral=ephemeral,
        run_extra_hooks_for_ephemeral=run_extra_hooks_for_ephemeral,
        hooks=list(hooks or []),
        hook_factories=list(hook_factories or []),
        tools=tools,
    )
    _track_streamed_content(ctx)

    while ctx.state is not TurnState.DONE:
        handler_name = f"_state_{ctx.state.name.lower()}"
        handler = getattr(loop, handler_name, None)
        if handler is None:
            raise RuntimeError(f"Missing state handler for {ctx.state}")

        state_started_at = time.perf_counter()
        try:
            event = await handler(ctx)
        except BaseException:
            duration = (time.perf_counter() - state_started_at) * 1000
            ctx.trace.append(
                StateTraceEntry(
                    state=ctx.state,
                    started_at=state_started_at,
                    duration_ms=duration,
                    event="",
                    error="exception",
                )
            )
            raise

        duration = (time.perf_counter() - state_started_at) * 1000
        ctx.trace.append(
            StateTraceEntry(
                state=ctx.state,
                started_at=state_started_at,
                duration_ms=duration,
                event=event,
            )
        )
        _ctx_logger(ctx).debug(
            "[turn {}] State {} took {:.1f}ms -> event {}",
            ctx.turn_id,
            ctx.state.name,
            duration,
            event,
        )

        next_state = loop._TRANSITIONS.get((ctx.state, event))
        if next_state is None:
            raise RuntimeError(
                f"[turn {ctx.turn_id}] No transition from {ctx.state} on event {event!r}"
            )
        ctx.state = next_state

    _ctx_logger(ctx).debug(
        "[turn {}] Turn completed after {} states",
        ctx.turn_id,
        len(ctx.trace),
    )
    return ctx.outbound
