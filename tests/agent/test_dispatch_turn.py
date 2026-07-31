from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from mira.agent.dispatch_turn import dispatch_inbound_turn
from mira.bus.events import InboundMessage, OutboundMessage


class _Delivery:
    def __init__(self) -> None:
        self.completed: list[dict[str, Any]] = []
        self.idle_count = 0
        self.failed = 0
        self.aborted = 0

    async def on_stream(self, _delta: str) -> None:
        return None

    async def on_stream_end(self, **_kwargs: Any) -> None:
        return None

    async def complete(self, response: Any, *, publish_completion: bool) -> None:
        self.completed.append({
            "response": response,
            "publish_completion": publish_completion,
        })

    async def idle(self) -> None:
        self.idle_count += 1

    async def fail(self, *, publish_completion: bool) -> None:
        self.failed += int(publish_completion)

    async def abort_stream(self) -> None:
        self.aborted += 1


class _DeliveryFactory:
    def __init__(self) -> None:
        self.unrouted_delivery = _Delivery()
        self.created_delivery = _Delivery()

    def unrouted(self, _msg: InboundMessage, _session_key: str) -> _Delivery:
        return self.unrouted_delivery

    def create(self, _msg: InboundMessage, _session_key: str, *, enable_stream: bool) -> _Delivery:
        assert enable_stream is True
        return self.created_delivery


class _Bus:
    def __init__(self) -> None:
        self.published: list[InboundMessage] = []

    async def publish_inbound(self, msg: InboundMessage) -> None:
        self.published.append(msg)


class _TurnProcesses:
    def __init__(self) -> None:
        self.completed: list[tuple[Any, str, str]] = []

    def spawn(self, msg: InboundMessage) -> str:
        return f"proc:{msg.session_key}"

    def complete(self, process: Any, session_key: str, *, reason: str) -> None:
        self.completed.append((process, session_key, reason))

    def stop_for_swap(self, _process: Any, _session_key: str, *, reason: str) -> None:
        raise AssertionError(f"unexpected stop_for_swap: {reason}")


class _Loop:
    def __init__(self) -> None:
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._concurrency_gate = None
        self._pending_queues: dict[str, asyncio.Queue[InboundMessage]] = {}
        self._automation_turn_coordinators: tuple[tuple[str, Any], ...] = ()
        self.execution_gate = SimpleNamespace(wait_for_turn_admission=self._wait_for_turn)
        self.turn_processes = _TurnProcesses()
        self.turn_delivery_factory = _DeliveryFactory()
        self.bus = _Bus()
        self.deferred: list[str] = []

    def _effective_session_key(self, msg: InboundMessage) -> str:
        return msg.session_key

    async def _wait_for_turn(self) -> None:
        return None

    async def _process_message(
        self,
        _msg: InboundMessage,
        *,
        pending_queue: asyncio.Queue[InboundMessage],
        **_kwargs: Any,
    ) -> OutboundMessage:
        await pending_queue.put(InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id="followup",
            content="leftover",
        ))
        return OutboundMessage(channel="cli", chat_id="chat", content="done")

    async def _publish_next_deferred_automation_turn(self, session_key: str) -> None:
        self.deferred.append(session_key)


@pytest.mark.asyncio
async def test_dispatch_inbound_turn_cleans_queue_and_republishes_leftovers() -> None:
    loop = _Loop()
    msg = InboundMessage(channel="cli", sender_id="user", chat_id="chat", content="start")

    await dispatch_inbound_turn(loop, msg)

    assert msg.session_key not in loop._pending_queues
    assert [item.content for item in loop.bus.published] == ["leftover"]
    assert loop.turn_processes.completed == [(f"proc:{msg.session_key}", msg.session_key, "completed")]
    assert loop.turn_delivery_factory.created_delivery.completed[0]["response"].content == "done"
    assert loop.turn_delivery_factory.created_delivery.idle_count == 1
    assert loop.deferred == [msg.session_key]
