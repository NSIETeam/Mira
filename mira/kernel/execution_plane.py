"""Stable execution-lane contract for the Mira kernel surface."""

from __future__ import annotations

from typing import Any


def build_execution_lanes(
    *,
    preferred_lane: str,
    goal_active: bool,
    goal_continuing: bool,
    goal_summary: str | None = None,
) -> list[dict[str, Any]]:
    sustained_state = "active" if goal_active else "idle"
    if goal_continuing:
        sustained_state = "continuing"
    return [
        {
            "id": "interactive",
            "label": "Interactive Lane",
            "mode": "foreground",
            "state": "preferred" if preferred_lane == "interactive" else "ready",
            "summary": "Direct operator-driven execution in the active shell.",
        },
        {
            "id": "sustained_goal",
            "label": "Sustained Goal Lane",
            "mode": "background",
            "state": (
                "preferred"
                if preferred_lane == "sustained_goal" and sustained_state in {"active", "continuing"}
                else sustained_state
            ),
            "summary": goal_summary or "Long-running objective slices with internal continuation support.",
        },
        {
            "id": "subagent",
            "label": "Subagent Lane",
            "mode": "background",
            "state": "preferred" if preferred_lane == "subagent" else "available",
            "summary": "Delegated execution workers for specialized or parallel tasks.",
        },
    ]
