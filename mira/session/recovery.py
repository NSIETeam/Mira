"""Recovery helpers for interrupted agent turns."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mira.session.manager import Session, SessionManager

RUNTIME_CHECKPOINT_KEY = "runtime_checkpoint"
PENDING_USER_TURN_KEY = "pending_user_turn"


@dataclass(slots=True)
class SessionRecoveryResult:
    """Summary of recovery work applied to one session."""

    session_key: str
    runtime_checkpoint: bool = False
    pending_user_turn: bool = False

    @property
    def recovered(self) -> bool:
        return self.runtime_checkpoint or self.pending_user_turn


def recover_interrupted_sessions(
    sessions: SessionManager,
    *,
    fsync: bool = True,
) -> list[SessionRecoveryResult]:
    """Materialize interrupted turns for every persisted session."""
    results: list[SessionRecoveryResult] = []
    for info in sessions.list_sessions():
        key = info.get("key")
        if not isinstance(key, str) or not key:
            continue
        session = sessions.get_or_create(key)
        result = recover_interrupted_session(session)
        if result.recovered:
            sessions.save(session, fsync=fsync)
            results.append(result)
    return results


def recover_interrupted_session(session: Session) -> SessionRecoveryResult:
    """Close all known interrupted-turn markers in a single session."""
    result = SessionRecoveryResult(session_key=session.key)
    if restore_runtime_checkpoint(session):
        result.runtime_checkpoint = True
    if restore_pending_user_turn(session):
        result.pending_user_turn = True
    return result


def restore_runtime_checkpoint(session: Session) -> bool:
    """Materialize an unfinished runtime checkpoint into session history."""
    checkpoint = session.metadata.get(RUNTIME_CHECKPOINT_KEY)
    if not isinstance(checkpoint, dict):
        return False

    now = datetime.now()
    assistant_message = checkpoint.get("assistant_message")
    completed_tool_results = checkpoint.get("completed_tool_results") or []
    pending_tool_calls = checkpoint.get("pending_tool_calls") or []

    restored_messages: list[dict[str, Any]] = []
    if isinstance(assistant_message, dict):
        restored = dict(assistant_message)
        restored.setdefault("timestamp", now.isoformat())
        restored_messages.append(restored)
    for message in completed_tool_results:
        if isinstance(message, dict):
            restored = dict(message)
            restored.setdefault("timestamp", now.isoformat())
            restored_messages.append(restored)
    for tool_call in pending_tool_calls:
        if not isinstance(tool_call, dict):
            continue
        tool_id = tool_call.get("id")
        name = ((tool_call.get("function") or {}).get("name")) or "tool"
        restored_messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_id,
                "name": name,
                "content": "Error: Task interrupted before this tool finished.",
                "timestamp": now.isoformat(),
            }
        )

    overlap = 0
    max_overlap = min(len(session.messages), len(restored_messages))
    for size in range(max_overlap, 0, -1):
        existing = session.messages[-size:]
        restored_slice = restored_messages[:size]
        if all(
            _checkpoint_message_key(left) == _checkpoint_message_key(right)
            for left, right in zip(existing, restored_slice)
        ):
            overlap = size
            break
    session.messages.extend(restored_messages[overlap:])

    session.metadata.pop(PENDING_USER_TURN_KEY, None)
    session.metadata.pop(RUNTIME_CHECKPOINT_KEY, None)
    session.updated_at = now
    return True


def restore_pending_user_turn(session: Session) -> bool:
    """Close a turn that crashed after persisting only the user message."""
    if not session.metadata.get(PENDING_USER_TURN_KEY):
        return False

    now = datetime.now()
    if session.messages and session.messages[-1].get("role") == "user":
        session.messages.append(
            {
                "role": "assistant",
                "content": "Error: Task interrupted before a response was generated.",
                "timestamp": now.isoformat(),
            }
        )
        session.updated_at = now

    session.metadata.pop(PENDING_USER_TURN_KEY, None)
    return True


def _checkpoint_message_key(message: dict[str, Any]) -> tuple[Any, ...]:
    return (
        message.get("role"),
        message.get("content"),
        message.get("tool_call_id"),
        message.get("name"),
        message.get("tool_calls"),
        message.get("reasoning_content"),
        message.get("thinking_blocks"),
    )
