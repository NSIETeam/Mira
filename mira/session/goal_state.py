"""Session metadata helpers for explicit sustained goals."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping, MutableMapping

from mira.session.manager import SessionManager

GOAL_STATE_KEY = "goal_state"
LEGACY_GOAL_STATE_KEY = "thread_goal"
GOAL_COMMAND = "/goal"
MAX_GOAL_OBJECTIVE_CHARS = 4000
_MAX_OBJECTIVE_WS = 600


def _iso_now() -> str:
    return datetime.now().isoformat()


def _session_goal_raw(metadata: Mapping[str, Any] | None) -> Any:
    if not metadata:
        return None
    if GOAL_STATE_KEY in metadata:
        return metadata.get(GOAL_STATE_KEY)
    return metadata.get(LEGACY_GOAL_STATE_KEY)


def discard_legacy_goal_state_key(metadata: MutableMapping[str, Any]) -> bool:
    """Remove the old thread-goal key after callers have migrated to goal_state."""
    return metadata.pop(LEGACY_GOAL_STATE_KEY, None) is not None


def goal_state_raw(metadata: Mapping[str, Any] | None) -> Any:
    """Return the session goal blob under :data:`GOAL_STATE_KEY`."""
    return _session_goal_raw(metadata)


def sustained_goal_active(metadata: Mapping[str, Any] | None) -> bool:
    """True when this session has an active sustained objective."""
    goal = parse_goal_state(goal_state_raw(metadata))
    return isinstance(goal, dict) and goal.get("status") == "active"


def explicit_goal_requested(message_metadata: Mapping[str, Any] | None) -> bool:
    """True when this turn was explicitly started by the ``/goal`` command."""
    if not message_metadata:
        return False
    if message_metadata.get("goal_requested") is True:
        return True
    return str(message_metadata.get("original_command") or "").strip() == GOAL_COMMAND


def sustained_goal_turn(
    metadata: Mapping[str, Any] | None,
    *,
    message_metadata: Mapping[str, Any] | None = None,
) -> bool:
    """True when this turn should use sustained-goal runtime limits."""
    return sustained_goal_active(metadata) or explicit_goal_requested(message_metadata)


def parse_goal_state(blob: Any) -> dict[str, Any] | None:
    if blob is None:
        return None
    if isinstance(blob, dict):
        return blob
    if isinstance(blob, str):
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def annotate_goal_progress(
    metadata: MutableMapping[str, Any],
    *,
    continuation_rounds: int | None = None,
) -> bool:
    goal = parse_goal_state(_session_goal_raw(metadata))
    if not isinstance(goal, dict) or goal.get("status") != "active":
        return False
    next_goal = dict(goal)
    next_goal["last_progress_at"] = _iso_now()
    if continuation_rounds is not None:
        next_goal["continuation_rounds"] = max(0, int(continuation_rounds))
    metadata[GOAL_STATE_KEY] = next_goal
    return True


def finalize_goal_state(
    metadata: MutableMapping[str, Any],
    *,
    status: str,
    recap: str = "",
    outcome: str | None = None,
    acceptance: str | None = None,
    evidence: str | None = None,
) -> bool:
    goal = parse_goal_state(_session_goal_raw(metadata))
    if not isinstance(goal, dict):
        return False
    ended = _iso_now()
    next_goal = dict(goal)
    next_goal["status"] = status
    next_goal["ended_at"] = ended
    next_goal["last_progress_at"] = ended
    if recap.strip():
        next_goal["recap"] = recap.strip()
    if outcome and outcome.strip():
        next_goal["outcome"] = outcome.strip()
    if acceptance and acceptance.strip():
        next_goal["acceptance"] = acceptance.strip()
    if evidence and evidence.strip():
        next_goal["evidence"] = evidence.strip()
    if status == "completed":
        next_goal["completed_at"] = ended
        next_goal["verification_status"] = "verified" if (evidence or "").strip() else "claimed"
    elif status == "blocked":
        next_goal["verification_status"] = "blocked"
    elif status == "cancelled":
        next_goal["verification_status"] = "cancelled"
    metadata[GOAL_STATE_KEY] = next_goal
    return True


def goal_state_runtime_lines(metadata: Mapping[str, Any] | None) -> list[str]:
    """Lines appended inside the Runtime Context block when a goal is active."""
    if not metadata:
        return []
    goal = parse_goal_state(_session_goal_raw(metadata))
    if not isinstance(goal, dict):
        return []
    status = str(goal.get("status") or "").strip()
    objective = str(goal.get("objective") or "").strip()
    if status != "active":
        out = [f"Goal ({status or 'inactive'}):"]
        if objective:
            out.append(objective)
        for key, label in (
            ("recap", "Recap"),
            ("outcome", "Outcome"),
            ("acceptance", "Acceptance"),
            ("evidence", "Evidence"),
            ("verification_status", "Verification"),
        ):
            value = str(goal.get(key) or "").strip()
            if value:
                out.append(f"{label}: {value}")
        ended_at = str(goal.get("ended_at") or goal.get("completed_at") or "").strip()
        if ended_at:
            out.append(f"Ended: {ended_at}")
        return out
    if not objective:
        return ["Goal: active (no objective text stored)."]
    if len(objective) > MAX_GOAL_OBJECTIVE_CHARS:
        objective = objective[:MAX_GOAL_OBJECTIVE_CHARS].rstrip() + "\n… (truncated)"
    out = ["Goal (active):", objective]
    hint = str(goal.get("ui_summary") or "").strip()
    if hint:
        out.append(f"Summary: {hint}")
    rounds = goal.get("continuation_rounds")
    if isinstance(rounds, int) and rounds > 0:
        out.append(f"Continuation rounds: {rounds}")
    progress_at = str(goal.get("last_progress_at") or "").strip()
    if progress_at:
        out.append(f"Last progress: {progress_at}")
    acceptance = str(goal.get("acceptance") or "").strip()
    if acceptance:
        out.append(f"Acceptance: {acceptance}")
    return out


def goal_state_ws_blob(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """JSON-safe snapshot for WebSocket ``goal_state`` events (one chat_id per frame)."""
    goal = parse_goal_state(_session_goal_raw(metadata)) if metadata else None
    if isinstance(goal, dict) and goal.get("status") == "active":
        objective = str(goal.get("objective") or "").strip()
        if len(objective) > _MAX_OBJECTIVE_WS:
            objective = objective[:_MAX_OBJECTIVE_WS].rstrip() + "…"
        summary = str(goal.get("ui_summary") or "").strip()[:120]
        blob: dict[str, Any] = {"active": True}
        if summary:
            blob["ui_summary"] = summary
        if objective:
            blob["objective"] = objective
        rounds = goal.get("continuation_rounds")
        if isinstance(rounds, int) and rounds > 0:
            blob["continuation_rounds"] = rounds
        progress_at = str(goal.get("last_progress_at") or "").strip()
        if progress_at:
            blob["last_progress_at"] = progress_at
        acceptance = str(goal.get("acceptance") or "").strip()
        if acceptance:
            blob["acceptance"] = acceptance[:240]
        return blob
    if isinstance(goal, dict):
        blob: dict[str, Any] = {"active": False}
        for key in ("status", "recap", "outcome", "evidence", "verification_status"):
            value = str(goal.get(key) or "").strip()
            if value:
                blob[key] = value[:240] if key in {"recap", "outcome", "evidence"} else value
        return blob
    return {"active": False}


def runner_wall_llm_timeout_s(
    sessions: SessionManager,
    session_key: str | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    message_metadata: Mapping[str, Any] | None = None,
) -> float | None:
    """Wall-clock cap for :class:`~mira.agent.runner.AgentRunner` when streaming an LLM.

    Returns ``0.0`` to disable ``asyncio.wait_for`` around the request when this is a
    sustained-goal turn; ``None`` means use ``mira_LLM_TIMEOUT_S``. Pass in-memory
    ``metadata`` when the caller already holds :attr:`~mira.session.manager.Session.metadata`
    for this turn.
    """
    meta: Mapping[str, Any] | None = metadata
    if meta is None and session_key:
        meta = sessions.get_or_create(session_key).metadata
    return 0.0 if sustained_goal_turn(meta, message_metadata=message_metadata) else None
