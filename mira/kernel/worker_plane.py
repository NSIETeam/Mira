"""Stable background-worker contract for the Mira kernel surface."""

from __future__ import annotations

from typing import Any


def build_worker_registry() -> list[dict[str, Any]]:
    return [
        {
            "id": "interactive_worker",
            "label": "Interactive Worker",
            "lane": "interactive",
            "kind": "foreground",
            "state": "ready",
            "summary": "Primary worker bound to the active operator session.",
        },
        {
            "id": "goal_worker",
            "label": "Goal Worker",
            "lane": "sustained_goal",
            "kind": "background",
            "state": "idle",
            "summary": "Continuation-capable worker for sustained goals.",
        },
        {
            "id": "subagent_worker",
            "label": "Subagent Worker",
            "lane": "subagent",
            "kind": "background",
            "state": "available",
            "summary": "Delegated worker pool for parallel or specialized execution.",
        },
    ]


def project_worker_registry(
    *,
    preferred_lane: str,
    goal_active: bool,
    goal_continuing: bool,
) -> list[dict[str, Any]]:
    workers = build_worker_registry()
    for worker in workers:
        lane = str(worker.get("lane") or "")
        if lane == "interactive":
            worker["state"] = "preferred" if preferred_lane == "interactive" else "ready"
        elif lane == "sustained_goal":
            if goal_continuing:
                worker["state"] = "continuing"
            elif goal_active:
                worker["state"] = "active"
            elif preferred_lane == "sustained_goal":
                worker["state"] = "preferred"
        elif lane == "subagent" and preferred_lane == "subagent":
            worker["state"] = "preferred"
    return workers
