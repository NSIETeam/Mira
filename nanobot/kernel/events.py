"""Normalized kernel event model.

GUI code should not need to know the full provider/tool streaming schema. This
module maps nanobot's richer SDK events into a compact set of durable event
types that a desktop or browser shell can render without runtime coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nanobot.nanobot import StreamEvent

KernelEventType = Literal[
    "status",
    "message",
    "reasoning",
    "tool_call",
    "tool_result",
    "error",
]


@dataclass(slots=True)
class KernelEvent:
    type: KernelEventType
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def normalize_stream_event(event: StreamEvent) -> KernelEvent:
    """Map the richer SDK event model onto a compact GUI-facing contract."""
    event_type = _stringify(getattr(event, "type", ""))
    metadata = dict(getattr(event, "metadata", {}) or {})
    payload = getattr(event, "payload", None)
    text = _stringify(getattr(event, "text", None))
    delta = _stringify(getattr(event, "delta", None))

    if event_type == "run_started":
        return KernelEvent("status", "running", metadata)
    if event_type == "run_completed":
        return KernelEvent("status", "done", metadata)
    if event_type == "run_failed":
        return KernelEvent("error", _stringify(payload) or "run failed", metadata)
    if event_type in {"text_delta", "text_completed"}:
        return KernelEvent("message", delta or text or _stringify(payload), metadata)
    if event_type in {"reasoning_delta", "reasoning_completed"}:
        return KernelEvent("reasoning", delta or text or _stringify(payload), metadata)
    if event_type == "tool_started":
        return KernelEvent("tool_call", _stringify(payload) or metadata.get("tool_name", ""), metadata)
    if event_type in {"tool_completed", "tool_failed"}:
        normalized_type: KernelEventType = "tool_result"
        if event_type == "tool_failed":
            normalized_type = "error"
        return KernelEvent(normalized_type, _stringify(payload), metadata)
    return KernelEvent("status", event_type or "unknown", metadata)
