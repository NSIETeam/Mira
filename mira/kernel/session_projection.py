"""Runtime event projection for ``KernelApp``.

This module keeps session/goal/model event projection out of the main kernel
facade. The app still owns state storage; the projector owns how runtime events
mutate that state and append operator-visible kernel events.
"""

from __future__ import annotations

from typing import Any

from mira.bus.runtime_events import (
    GoalStateChanged,
    RuntimeModelChanged,
    SessionTurnStarted,
    TurnCompleted,
    TurnRunStatusChanged,
)
from mira.session.goal_state import goal_state_ws_blob


class KernelSessionProjector:
    """Project runtime bus events into KernelApp session state."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def handle_session_turn_started(self, event: SessionTurnStarted) -> None:
        app = self._app
        session_key = event.context.session_key
        app._active_session_key = session_key
        app._session_status[session_key] = "queued"
        app._record_kernel_event(
            "session_turn_started",
            state="running",
            message=f"session {session_key} admitted to kernel",
            session_key=session_key,
            event_type="session",
        )

    def handle_run_status_changed(self, event: TurnRunStatusChanged) -> None:
        app = self._app
        session_key = event.context.session_key
        app._active_session_key = session_key
        app._session_status[session_key] = event.status
        if event.status == "running":
            from mira.kernel.scheduler import prioritize_lane

            app._scheduler_state = prioritize_lane(app._scheduler_state, lane="interactive")
        app._record_kernel_event(
            "turn_run_status_changed",
            state=event.status,
            message=f"session {session_key} status -> {event.status}",
            session_key=session_key,
            event_type="turn",
        )

    def handle_turn_completed(self, event: TurnCompleted) -> None:
        app = self._app
        session_key = event.context.session_key
        app._active_session_key = session_key
        app._session_status[session_key] = "idle"
        app._session_latency[session_key] = event.latency_ms
        runtime = event.runtime
        app._session_runtime[session_key] = (
            {}
            if runtime is None
            else {
                "model": getattr(runtime, "model", None),
                "model_preset": getattr(runtime, "model_preset", None),
                "context_window_tokens": getattr(runtime, "context_window_tokens", None),
            }
        )
        checkpoints = app._loop_runtime_var("session_checkpoints", {})
        if isinstance(checkpoints, dict):
            checkpoints.pop(session_key, None)
        app._checkpoint_signatures.pop(session_key, None)
        app._subagent_signatures.pop(session_key, None)
        app._record_kernel_event(
            "turn_completed",
            state="ok",
            message=f"session {session_key} completed",
            session_key=session_key,
            event_type="turn",
            latency_ms=event.latency_ms,
        )

    def handle_goal_state_changed(self, event: GoalStateChanged) -> None:
        app = self._app
        session_key = event.context.session_key
        app._active_session_key = session_key
        app._session_metadata[session_key] = dict(event.session_metadata or {})
        goal_blob = goal_state_ws_blob(event.session_metadata)
        app._record_kernel_event(
            "goal_state_changed",
            state="active" if goal_blob.get("active") else "idle",
            message=str(goal_blob.get("ui_summary") or goal_blob.get("objective") or "goal state updated"),
            session_key=session_key,
            event_type="goal",
        )

    def handle_runtime_model_changed(self, event: RuntimeModelChanged) -> None:
        self._app._record_kernel_event(
            "runtime_model_changed",
            state="ready",
            message=f"runtime model -> {event.model}",
        )
