"""Per-session dispatch orchestration for AgentLoop."""

from __future__ import annotations

import asyncio
import dataclasses
from contextlib import nullcontext
from typing import Any

from mira.bus.events import InboundMessage
from mira.session import turn_continuation
from mira.utils.logging import session_logger


async def dispatch_inbound_turn(loop: Any, msg: InboundMessage) -> None:
    """Process one inbound message with session serialization and delivery cleanup."""
    session_key = loop._effective_session_key(msg)
    if session_key != msg.session_key:
        msg = dataclasses.replace(msg, session_key_override=session_key)
    lock = loop._session_locks.setdefault(session_key, asyncio.Lock())
    gate = loop._concurrency_gate or nullcontext()

    delivery = loop.turn_delivery_factory.unrouted(msg, session_key)
    pending: asyncio.Queue[InboundMessage] | None = None
    process: Any | None = None
    try:
        async with lock, gate:
            await loop.execution_gate.wait_for_turn_admission()
            process = loop.turn_processes.spawn(msg)
            # Only the task that owns the session lock may publish the active
            # mid-turn injection queue for this session.
            pending = asyncio.Queue(maxsize=20)
            loop._pending_queues[session_key] = pending
            try:
                delivery = loop.turn_delivery_factory.create(
                    msg,
                    session_key,
                    enable_stream=True,
                )
                response = await loop._process_message(
                    msg,
                    on_stream=delivery.on_stream,
                    on_stream_end=delivery.on_stream_end,
                    pending_queue=pending,
                    delivery=delivery,
                )
                continuing = turn_continuation.internal_continuation_pending(msg.metadata)
                await delivery.complete(response, publish_completion=not continuing)
                loop.turn_processes.complete(process, session_key, reason="completed")
                for _, coordinator in loop._automation_turn_coordinators:
                    coordinator.complete(msg, response=response)
            except asyncio.CancelledError:
                for _, coordinator in loop._automation_turn_coordinators:
                    coordinator.complete(msg, error=asyncio.CancelledError())
                session_logger(session_key).info("Task cancelled for session {}", session_key)
                await _abort_delivery(delivery, session_key)
                await _restore_cancelled_checkpoint(loop, msg, session_key)
                loop.turn_processes.stop_for_swap(process, session_key, reason="cancelled")
                raise
            except BaseException as exc:
                if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                    raise
                session_logger(session_key).exception(
                    "Error processing message for session {}",
                    session_key,
                )
                await delivery.fail(
                    publish_completion=not turn_continuation.internal_continuation_pending(
                        msg.metadata
                    )
                )
                for _, coordinator in loop._automation_turn_coordinators:
                    coordinator.complete(msg, error=exc)
                loop.turn_processes.complete(
                    process,
                    session_key,
                    reason=f"error: {type(exc).__name__}",
                )
            finally:
                await _cleanup_pending_queue(loop, session_key, pending)
                if not turn_continuation.internal_continuation_pending(msg.metadata):
                    await delivery.idle()
                await loop._publish_next_deferred_automation_turn(session_key)
    finally:
        if pending is None:
            await delivery.idle()
            await loop._publish_next_deferred_automation_turn(session_key)


async def _abort_delivery(delivery: Any, session_key: str) -> None:
    try:
        await delivery.abort_stream()
    except (OSError, RuntimeError, ValueError):
        session_logger(session_key).debug(
            "Could not close stream for cancelled session {}",
            session_key,
            exc_info=True,
        )


async def _restore_cancelled_checkpoint(loop: Any, msg: InboundMessage, session_key: str) -> None:
    # Preserve partial context from the interrupted turn so the user does not
    # lose tool results and assistant messages accumulated before /stop.
    try:
        key = loop._effective_session_key(msg)
        session = loop.sessions.get_or_create(key)
        if loop._restore_runtime_checkpoint(session):
            loop._clear_pending_user_turn(session)
            loop.sessions.save(session)
            session_logger(key).info(
                "Restored partial context for cancelled session {}",
                key,
            )
    except (OSError, RuntimeError, ValueError):
        session_logger(session_key).debug(
            "Could not restore checkpoint for cancelled session {}",
            session_key,
            exc_info=True,
        )


async def _cleanup_pending_queue(
    loop: Any,
    session_key: str,
    pending: asyncio.Queue[InboundMessage] | None,
) -> None:
    # Drain any messages still in the pending queue and re-publish them to the
    # bus so they are processed as fresh inbound messages rather than lost. Only
    # remove our own queue; a later task waiting on the lock must not steal
    # cleanup ownership.
    queue = None
    if loop._pending_queues.get(session_key) is pending:
        queue = loop._pending_queues.pop(session_key, None)
    else:
        queue = pending
    if queue is None:
        return
    leftover = 0
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        await loop.bus.publish_inbound(item)
        leftover += 1
    if leftover:
        session_logger(session_key).info(
            "Re-published {} leftover message(s) to bus for session {}",
            leftover,
            session_key,
        )
