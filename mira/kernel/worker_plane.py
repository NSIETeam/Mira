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
