"""Mid-turn pending-message injection helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from loguru import logger

from mira.agent.tools.context import RequestContext
from mira.agent.tools.registry import ToolRegistry
from mira.bus.events import InboundMessage
from mira.runtime_context import (
    RUNTIME_CONTEXT_MESSAGE_META,
    RuntimeContextBlock,
    append_runtime_context,
)
from mira.security.workspace_access import WorkspaceScopeResolver
from mira.session.history_visibility import HIDDEN_HISTORY_META
from mira.session.manager import Session
from mira.utils.llm_runtime import LLMRuntime


@dataclass(slots=True)
class PendingInjectionDrainer:
    """Drain follow-up messages into runner-compatible user messages."""

    pending_queue: asyncio.Queue[InboundMessage] | None
    session: Session | None
    active_session_key: str | None
    runtime: LLMRuntime
    request_turn_id: str
    effective_tools: ToolRegistry
    workspace_scopes: WorkspaceScopeResolver
    build_user_content: Callable[[str, list[str] | None], Any]
    prepare_message_media: Callable[[str, list[str]], tuple[str, list[str]]]
    resolve_runtime_context: Callable[
        [RequestContext, ToolRegistry],
        Awaitable[list[RuntimeContextBlock]],
    ]
    get_running_subagents: Callable[[str], int]

    async def drain(self, *, limit: int) -> list[dict[str, Any]]:
        """Drain follow-up messages from the pending queue.

        When no messages are immediately available but subagents spawned in
        this dispatch are still running, block until at least one result arrives
        or times out. This keeps the runner loop alive so completions are
        consumed in-order rather than dispatched separately.
        """
        if self.pending_queue is None:
            return []

        items: list[dict[str, Any]] = []
        while len(items) < limit:
            try:
                items.append(await self._to_user_message(self.pending_queue.get_nowait()))
            except asyncio.QueueEmpty:
                break

        if not items and self.session is not None and self.get_running_subagents(self.session.key) > 0:
            try:
                msg = await asyncio.wait_for(self.pending_queue.get(), timeout=300)
            except TimeoutError:
                logger.warning(
                    "Timeout waiting for sub-agent completion in session {}",
                    self.session.key,
                )
                return items
            items.append(await self._to_user_message(msg))
            while len(items) < limit:
                try:
                    items.append(await self._to_user_message(self.pending_queue.get_nowait()))
                except asyncio.QueueEmpty:
                    break

        self._insert_subagent_rollup(items)
        return items

    async def _to_user_message(self, pending_msg: InboundMessage) -> dict[str, Any]:
        content = pending_msg.content
        media = pending_msg.media if pending_msg.media else None
        if media:
            content, media = self.prepare_message_media(content, media)
            media = media or None
        user_content = self.build_user_content(content, media)
        row: dict[str, Any] = {"role": "user", "content": user_content}
        metadata = pending_msg.metadata if isinstance(pending_msg.metadata, dict) else {}
        if pending_msg.channel != "system":
            row["content"] = await self._content_with_runtime_context(
                pending_msg,
                metadata,
                user_content,
            )
        self._mark_subagent_result(row, pending_msg, metadata)
        return row

    async def _content_with_runtime_context(
        self,
        pending_msg: InboundMessage,
        metadata: Mapping[str, Any],
        user_content: Any,
    ) -> Any:
        scope = self.workspace_scopes.for_turn(
            channel=pending_msg.channel,
            message_metadata=metadata,
            session_metadata=self.session.metadata if self.session is not None else None,
        )
        pending_request = RequestContext(
            channel=pending_msg.channel,
            chat_id=pending_msg.chat_id,
            message_id=metadata.get("message_id"),
            session_key=self.active_session_key,
            original_user_text=pending_msg.content,
            runtime=self.runtime,
            metadata=dict(metadata),
            sender_id=pending_msg.sender_id,
            turn_id=self.request_turn_id,
            workspace=scope.project_path,
        )
        blocks = await self.resolve_runtime_context(pending_request, self.effective_tools)
        merged_content, runtime_marker = append_runtime_context(user_content, blocks)
        if runtime_marker is not None:
            return _RuntimeMarkedContent(merged_content, runtime_marker)
        return merged_content

    @staticmethod
    def _mark_subagent_result(
        row: dict[str, Any],
        pending_msg: InboundMessage,
        metadata: Mapping[str, Any],
    ) -> None:
        if pending_msg.sender_id != "subagent" or metadata.get("injected_event") != "subagent_result":
            content = row.get("content")
            if isinstance(content, _RuntimeMarkedContent):
                row["content"] = content.content
                row["_meta"] = {RUNTIME_CONTEXT_MESSAGE_META: content.runtime_marker}
            return
        hidden_marker: dict[str, Any] = {"kind": "subagent_result"}
        task_id = metadata.get("subagent_task_id")
        if isinstance(task_id, str) and task_id:
            hidden_marker["subagent_task_id"] = task_id
            row["subagent_task_id"] = task_id
        content = row.get("content")
        if isinstance(content, _RuntimeMarkedContent):
            row["content"] = content.content
            row["_meta"] = {RUNTIME_CONTEXT_MESSAGE_META: content.runtime_marker}
        row[HIDDEN_HISTORY_META] = hidden_marker
        row["injected_event"] = "subagent_result"

    @staticmethod
    def _insert_subagent_rollup(items: list[dict[str, Any]]) -> None:
        subagent_items = [
            item for item in items
            if item.get("injected_event") == "subagent_result"
        ]
        if len(subagent_items) < 2:
            return
        lines = [
            "Structured subagent result summary:",
            f"- completed_results: {len(subagent_items)}",
        ]
        for item in subagent_items[:6]:
            task_id = str(item.get("subagent_task_id") or "unknown")
            content_text = _content_text(item.get("content"))
            if len(content_text) > 280:
                content_text = content_text[:277] + "..."
            lines.append(f"- {task_id}: {content_text}")
        items.insert(0, {
            "role": "user",
            "content": "\n".join(lines),
            HIDDEN_HISTORY_META: {"kind": "subagent_result_rollup"},
        })


@dataclass(slots=True)
class _RuntimeMarkedContent:
    content: Any
    runtime_marker: dict[str, Any]


def _content_text(content: Any) -> str:
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text") or ""))
        content_text = " ".join(part.strip() for part in text_parts if part.strip())
    else:
        content_text = str(content or "")
    return " ".join(content_text.split())
