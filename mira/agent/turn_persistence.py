"""Session-history persistence helpers for agent turns."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mira.bus.events import InboundMessage
from mira.runtime_context import (
    RUNTIME_CONTEXT_HISTORY_META,
    RUNTIME_CONTEXT_MESSAGE_META,
)
from mira.session.manager import Session
from mira.utils.helpers import image_placeholder_text
from mira.utils.helpers import truncate_text as truncate_text_fn
from mira.utils.logging import session_logger


def sanitize_persisted_blocks(
    content: list[dict[str, Any]],
    *,
    max_tool_result_chars: int,
    should_truncate_text: bool = False,
) -> list[dict[str, Any]]:
    """Strip volatile multimodal payloads before writing session history."""
    filtered: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            filtered.append(block)
            continue

        if block.get("type") == "image_url" and block.get("image_url", {}).get(
            "url", ""
        ).startswith("data:image/"):
            path = (block.get("_meta") or {}).get("path", "")
            filtered.append({"type": "text", "text": image_placeholder_text(path)})
            continue

        if block.get("type") == "text" and isinstance(block.get("text"), str):
            text = block["text"]
            if should_truncate_text and len(text) > max_tool_result_chars:
                text = truncate_text_fn(text, max_tool_result_chars)
            filtered.append({**block, "text": text})
            continue

        filtered.append(block)

    return filtered


def save_turn_messages(
    session: Session,
    messages: list[dict[str, Any]],
    skip: int,
    *,
    max_tool_result_chars: int,
    turn_latency_ms: int | None = None,
) -> None:
    """Save new-turn messages into session, truncating large tool results."""
    declared_tool_call_ids = {
        str(tc["id"])
        for m in session.messages
        if m.get("role") == "assistant"
        for tc in m.get("tool_calls") or []
        if isinstance(tc, dict) and tc.get("id")
    }
    fulfilled_tool_call_ids = {
        str(m["tool_call_id"])
        for m in session.messages
        if m.get("role") == "tool" and m.get("tool_call_id")
    }
    last_assistant_idx: int | None = None
    for m in messages[skip:]:
        entry = dict(m)
        internal_meta = entry.pop("_meta", None)
        runtime_context_meta = (
            internal_meta.get(RUNTIME_CONTEXT_MESSAGE_META)
            if isinstance(internal_meta, dict)
            else None
        )
        role, content = entry.get("role"), entry.get("content")
        if role == "assistant" and not content and not entry.get("tool_calls"):
            continue  # skip empty assistant messages; they poison session context
        if role == "tool":
            tool_call_id = entry.get("tool_call_id")
            tool_call_id_str = str(tool_call_id) if tool_call_id else ""
            if (
                not tool_call_id_str
                or tool_call_id_str not in declared_tool_call_ids
                or tool_call_id_str in fulfilled_tool_call_ids
            ):
                # Undeclared tool results corrupt future provider requests.
                session_logger(session.key).warning(
                    "Dropping invalid tool result {} from session {} during persistence",
                    tool_call_id_str or "(missing id)",
                    session.key,
                )
                continue
            fulfilled_tool_call_ids.add(tool_call_id_str)
            if isinstance(content, str) and len(content) > max_tool_result_chars:
                entry["content"] = truncate_text_fn(content, max_tool_result_chars)
            elif isinstance(content, list):
                filtered = sanitize_persisted_blocks(
                    content,
                    max_tool_result_chars=max_tool_result_chars,
                    should_truncate_text=True,
                )
                if not filtered:
                    # Preserve the tool_call/result pair after block filtering.
                    filtered = [{"type": "text", "text": "[tool result omitted during persistence]"}]
                entry["content"] = filtered
        elif role == "user":
            if isinstance(content, list):
                filtered = sanitize_persisted_blocks(
                    content,
                    max_tool_result_chars=max_tool_result_chars,
                )
                if not filtered:
                    continue
                entry["content"] = filtered
            if isinstance(runtime_context_meta, dict):
                entry[RUNTIME_CONTEXT_HISTORY_META] = runtime_context_meta
        entry.setdefault("timestamp", datetime.now().isoformat())
        session.messages.append(entry)
        if role == "assistant":
            last_assistant_idx = len(session.messages) - 1
            declared_tool_call_ids.update(
                str(tc["id"])
                for tc in entry.get("tool_calls") or []
                if isinstance(tc, dict) and tc.get("id")
            )
    if turn_latency_ms is not None and last_assistant_idx is not None:
        session.messages[last_assistant_idx]["latency_ms"] = int(turn_latency_ms)
    session.updated_at = datetime.now()


def persist_subagent_followup(session: Session, msg: InboundMessage) -> bool:
    """Persist subagent follow-ups before prompt assembly so history stays durable.

    Returns True if a new entry was appended; False if the follow-up was
    deduped (same ``subagent_task_id`` already in session) or carries no
    content worth persisting.
    """
    if not msg.content:
        return False
    task_id = msg.metadata.get("subagent_task_id") if isinstance(msg.metadata, dict) else None
    if task_id and any(
        m.get("injected_event") == "subagent_result" and m.get("subagent_task_id") == task_id
        for m in session.messages
    ):
        return False
    session.add_message(
        "assistant",
        msg.content,
        sender_id=msg.sender_id,
        injected_event="subagent_result",
        subagent_task_id=task_id,
    )
    return True
