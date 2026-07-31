from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from mira.agent.pending_injections import PendingInjectionDrainer
from mira.agent.tools.registry import ToolRegistry
from mira.bus.events import InboundMessage
from mira.session.history_visibility import HIDDEN_HISTORY_META
from mira.utils.llm_runtime import LLMRuntime


@pytest.mark.asyncio
async def test_pending_injection_drainer_rolls_up_subagent_results_without_agent_loop() -> None:
    pending_queue: asyncio.Queue[InboundMessage] = asyncio.Queue()
    await pending_queue.put(InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="cli:c",
        content="first result",
        metadata={"injected_event": "subagent_result", "subagent_task_id": "sub-1"},
    ))
    await pending_queue.put(InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="cli:c",
        content="second result",
        metadata={"injected_event": "subagent_result", "subagent_task_id": "sub-2"},
    ))

    async def resolve_runtime_context(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    drainer = PendingInjectionDrainer(
        pending_queue=pending_queue,
        session=None,
        active_session_key="cli:c",
        runtime=cast(LLMRuntime, SimpleNamespace()),
        request_turn_id="turn-1",
        effective_tools=cast(ToolRegistry, SimpleNamespace()),
        workspace_scopes=cast(Any, SimpleNamespace()),
        build_user_content=lambda content, media: content if media is None else [content, *media],
        prepare_message_media=lambda content, media: (content, media),
        resolve_runtime_context=resolve_runtime_context,
        get_running_subagents=lambda _session_key: 0,
    )

    items = await drainer.drain(limit=4)

    assert items[0]["content"].startswith("Structured subagent result summary:")
    assert items[0][HIDDEN_HISTORY_META] == {"kind": "subagent_result_rollup"}
    assert [item.get("subagent_task_id") for item in items[1:]] == ["sub-1", "sub-2"]
    assert items[1][HIDDEN_HISTORY_META] == {
        "kind": "subagent_result",
        "subagent_task_id": "sub-1",
    }
    assert items[2]["injected_event"] == "subagent_result"
