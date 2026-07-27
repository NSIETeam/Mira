"""Stable scheduler contract for the Mira kernel surface."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_scheduler_state() -> dict[str, Any]:
    return {
        "policy": "priority-foreground-with-background-drain",
        "preferred_lane": "interactive",
        "background_drain_requested": False,
    }


def clone_scheduler_state(state: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(state)


def request_background_drain(state: dict[str, Any]) -> dict[str, Any]:
    next_state = clone_scheduler_state(state)
    next_state["background_drain_requested"] = True
    next_state["policy"] = "background-drain-priority"
    return next_state


def prioritize_lane(state: dict[str, Any], *, lane: str) -> dict[str, Any]:
    if lane not in {"interactive", "sustained_goal", "subagent"}:
        raise ValueError(f"Unknown scheduler lane: {lane}")
    next_state = clone_scheduler_state(state)
    next_state["preferred_lane"] = lane
    next_state["policy"] = (
        "goal-lane-priority" if lane == "sustained_goal" else f"{lane}-lane-priority"
    )
    return next_state
