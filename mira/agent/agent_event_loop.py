"""Top-level inbound event loop for AgentLoop."""

from __future__ import annotations

import asyncio
import dataclasses
from functools import partial
from typing import Any

from loguru import logger

from mira.agent import context as agent_context
from mira.bus.events import InboundMessage
from mira.utils.cancellation import task_is_cancelling
from mira.utils.logging import session_logger


async def run_agent_event_loop(loop: Any) -> None:
    """Consume inbound messages and schedule per-session dispatch tasks."""
    loop._running = True
    try:
        await loop._connect_mcp()
        session_logger(None).info("Agent loop started")

        while loop._running:
            msg = await _consume_next_message(loop)
            if msg is None:
                continue
            if await _route_or_schedule_message(loop, msg):
                continue
    finally:
        # MCP stdio transports use AnyIO cancel scopes; close them from the task that opened them.
        await loop.close_mcp()


async def _consume_next_message(loop: Any) -> InboundMessage | None:
    try:
        return await asyncio.wait_for(loop.bus.consume_inbound(), timeout=1.0)
    except TimeoutError:
        loop._check_expired_sessions_if_due()
        return None
    except asyncio.CancelledError:
        # Preserve real task cancellation so shutdown can complete cleanly.
        # Only ignore non-task CancelledError signals that may leak from integrations.
        if not loop._running or task_is_cancelling():
            raise
        logger.warning("Ignoring leaked CancelledError while consuming inbound messages")
        return None
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        session_logger(None).warning(
            "Error consuming inbound message: {}, continuing...",
            exc,
        )
        return None


async def _route_or_schedule_message(loop: Any, msg: InboundMessage) -> bool:
    raw = msg.content.strip()
    effective_key = loop._effective_session_key(msg)
    if await agent_context.handle_runtime_control(loop, msg, loop.tools):
        return True
    if loop.commands.is_priority(raw):
        await loop._dispatch_command_inline(
            msg,
            effective_key,
            raw,
            loop.commands.dispatch_priority,
        )
        return True
    if _defer_automation_turn(loop, msg, effective_key):
        return True
    if await _route_to_pending_queue(loop, msg, effective_key, raw):
        return True

    task = asyncio.create_task(loop._dispatch(msg))
    loop._active_tasks.setdefault(effective_key, []).append(task)
    task.add_done_callback(partial(loop._forget_active_task, session_key=effective_key))
    return True


def _defer_automation_turn(loop: Any, msg: InboundMessage, effective_key: str) -> bool:
    for label, coordinator in loop._automation_turn_coordinators:
        if coordinator.defer_if_active(
            msg,
            session_key=effective_key,
            active_session_keys=loop._pending_queues.keys(),
        ):
            session_logger(effective_key).info(
                "Deferred {} turn for active session {}",
                label,
                effective_key,
            )
            return True
    return False


async def _route_to_pending_queue(
    loop: Any,
    msg: InboundMessage,
    effective_key: str,
    raw: str,
) -> bool:
    # If this session already has an active pending queue, route the message
    # there for mid-turn injection instead of creating a competing task.
    if effective_key not in loop._pending_queues:
        return False

    # Non-priority commands must not be queued for injection; dispatch them directly.
    if loop.commands.is_dispatchable_command(raw):
        await loop._dispatch_command_inline(
            msg,
            effective_key,
            raw,
            loop.commands.dispatch,
        )
        return True

    pending_msg = msg
    if effective_key != msg.session_key:
        pending_msg = dataclasses.replace(
            msg,
            session_key_override=effective_key,
        )
    try:
        loop._pending_queues[effective_key].put_nowait(pending_msg)
    except asyncio.QueueFull:
        session_logger(effective_key).warning(
            "Pending queue full for session {}, falling back to queued task",
            effective_key,
        )
        return False

    session_logger(effective_key).info(
        "Routed follow-up message to pending queue for session {}",
        effective_key,
    )
    return True
