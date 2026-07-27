"""Normalized kernel event model.

GUI code should not need to know the full provider/tool streaming schema. This
module maps nanobot's richer SDK events into a compact set of durable event
types that a desktop or browser shell can render without runtime coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nanobot.nanobot import RunResult, StreamEvent
from nanobot.session.goal_state import sustained_goal_active
from nanobot.session.turn_continuation import internal_continuation_pending

KernelEventType = Literal[
    "status",
    "message",
    "reasoning",
    "tool_call",
    "tool_result",
    "error",
]

ExecutionStatus = Literal["idle", "running", "completed", "failed"]
ExecutionLifecycleState = Literal[
    "idle",
    "foreground",
    "awaiting_input",
    "awaiting_approval",
    "background",
    "resuming",
    "completed",
    "failed",
]
KernelEventAction = Literal[
    "delta",
    "complete",
    "message",
    "trace",
    "file_edit",
    "transcription_error",
    "error",
]
KernelEventState = Literal[
    "running",
    "done",
    "failed",
    "unknown",
]

KERNEL_EVENT_TYPES: tuple[KernelEventType, ...] = (
    "status",
    "message",
    "reasoning",
    "tool_call",
    "tool_result",
    "error",
)
KERNEL_EVENT_ACTIONS: tuple[KernelEventAction, ...] = (
    "delta",
    "complete",
    "message",
    "trace",
    "file_edit",
    "transcription_error",
    "error",
)
KERNEL_EVENT_STATES: tuple[KernelEventState, ...] = (
    "running",
    "done",
    "failed",
    "unknown",
)

EXECUTION_SNAPSHOT_STATUSES: tuple[ExecutionStatus, ...] = (
    "idle",
    "running",
    "completed",
    "failed",
)
EXECUTION_LIFECYCLE_STATES: tuple[ExecutionLifecycleState, ...] = (
    "idle",
    "foreground",
    "awaiting_input",
    "awaiting_approval",
    "background",
    "resuming",
    "completed",
    "failed",
)


@dataclass(slots=True)
class KernelEvent:
    type: KernelEventType
    text: str = ""
    action: KernelEventAction | None = None
    state: KernelEventState | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "action": self.action,
            "state": self.state,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ExecutionSnapshot:
    """Stable execution-state snapshot exposed by the kernel boundary."""

    status: ExecutionStatus
    lifecycle: ExecutionLifecycleState = "idle"
    active: bool = False
    resumable: bool = False
    background: bool = False
    content: str = ""
    stop_reason: str | None = None
    error: str | None = None
    tools_used: tuple[str, ...] = ()
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "lifecycle": self.lifecycle,
            "active": self.active,
            "resumable": self.resumable,
            "background": self.background,
            "content": self.content,
            "stop_reason": self.stop_reason,
            "error": self.error,
            "tools_used": list(self.tools_used),
            "usage": dict(self.usage),
            "metadata": dict(self.metadata),
        }


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _snapshot_state_from_stop_reason(
    stop_reason: str | None,
    error: str | None,
) -> tuple[ExecutionStatus, ExecutionLifecycleState, bool]:
    normalized = (stop_reason or "").strip().lower()
    if error or normalized in {"error", "tool_error"}:
        return "failed", "failed", False
    if normalized == "max_iterations":
        return "running", "awaiting_input", True
    if normalized == "cancelled":
        return "idle", "idle", False
    if normalized == "empty_final_response":
        return "running", "awaiting_input", True
    if normalized in {"completed", ""}:
        return "completed", "completed", False
    return "completed", "completed", False


def normalize_stream_event(event: StreamEvent) -> KernelEvent:
    """Map the richer SDK event model onto a compact GUI-facing contract."""
    event_type = _stringify(getattr(event, "type", ""))
    metadata = dict(getattr(event, "metadata", {}) or {})
    payload = getattr(event, "payload", None)
    text = _stringify(getattr(event, "text", None))
    delta = _stringify(getattr(event, "delta", None))

    if event_type == "run.started":
        return KernelEvent("status", "running", None, "running", metadata)
    if event_type == "run.completed":
        return KernelEvent("status", "done", None, "done", metadata)
    if event_type == "run.failed":
        return KernelEvent("error", _stringify(payload) or "run failed", "error", "failed", metadata)
    if event_type in {"text.delta", "text.completed"}:
        action: KernelEventAction = "delta" if event_type == "text.delta" else "complete"
        return KernelEvent("message", delta or text or _stringify(payload), action, None, metadata)
    if event_type in {"reasoning.delta", "reasoning.completed"}:
        action = "delta" if event_type == "reasoning.delta" else "complete"
        return KernelEvent("reasoning", delta or text or _stringify(payload), action, None, metadata)
    if event_type == "tool.started":
        return KernelEvent(
            "tool_call",
            _stringify(payload) or metadata.get("tool_name", ""),
            "trace",
            None,
            metadata,
        )
    if event_type in {"tool.completed", "tool.failed"}:
        normalized_type: KernelEventType = "tool_result"
        if event_type == "tool.failed":
            normalized_type = "error"
        action = "error" if event_type == "tool.failed" else "complete"
        state = "failed" if event_type == "tool.failed" else "done"
        return KernelEvent(normalized_type, _stringify(payload), action, state, metadata)
    return KernelEvent("status", event_type or "unknown", None, "unknown", metadata)


def snapshot_from_run_result(result: RunResult) -> ExecutionSnapshot:
    """Create a stable execution snapshot from the SDK run result."""
    status, lifecycle, resumable = _snapshot_state_from_stop_reason(
        result.stop_reason,
        result.error,
    )
    return ExecutionSnapshot(
        status=status,
        lifecycle=lifecycle,
        active=status == "running",
        resumable=resumable,
        background=False,
        content=result.content,
        stop_reason=result.stop_reason,
        error=result.error,
        tools_used=tuple(result.tools_used),
        usage=dict(result.usage),
        metadata=dict(result.metadata),
    )


def merge_snapshot_with_session_metadata(
    snapshot: ExecutionSnapshot,
    metadata: dict[str, Any] | None,
) -> ExecutionSnapshot:
    """Project persisted session metadata onto a stable execution snapshot.

    This helper upgrades the one-shot ``RunResult``-derived snapshot with
    session-layer runtime signals that already exist in nanobot today:

    - sustained goal state
    - internal continuation pending
    - pending user-turn marker
    """
    if not metadata:
        return snapshot

    goal_active = sustained_goal_active(metadata)
    continuation_pending = internal_continuation_pending(metadata)
    pending_user_turn = bool(metadata.get("pending_user_turn"))

    lifecycle = snapshot.lifecycle
    active = snapshot.active
    resumable = snapshot.resumable

    if continuation_pending:
        lifecycle = "resuming"
        active = True
        resumable = True
    elif pending_user_turn:
        lifecycle = "awaiting_input"
        active = False
        resumable = True
    elif goal_active and snapshot.status == "running":
        lifecycle = "foreground"
        active = True
        resumable = True
    elif goal_active and snapshot.status == "completed":
        lifecycle = "completed"
        active = False
        resumable = True

    merged_metadata = dict(snapshot.metadata)
    merged_metadata.update({
        "goal_active": goal_active,
        "continuation_pending": continuation_pending,
        "pending_user_turn": pending_user_turn,
    })

    return ExecutionSnapshot(
        status=snapshot.status,
        lifecycle=lifecycle,
        active=active,
        resumable=resumable,
        background=snapshot.background,
        content=snapshot.content,
        stop_reason=snapshot.stop_reason,
        error=snapshot.error,
        tools_used=snapshot.tools_used,
        usage=dict(snapshot.usage),
        metadata=merged_metadata,
    )
