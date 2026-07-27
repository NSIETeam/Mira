"""Stable runtime-topology contract for the Mira kernel surface."""

from __future__ import annotations

from typing import Any


def build_runtime_topology(
    *,
    adapters: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    bridges: list[dict[str, Any]],
    execution_lanes: list[dict[str, Any]],
    scheduler: dict[str, Any],
    workers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "adapters": [dict(row) for row in adapters],
        "modules": [dict(row) for row in modules],
        "bridges": [dict(row) for row in bridges],
        "execution_lanes": [dict(row) for row in execution_lanes],
        "scheduler": {
            **dict(scheduler),
            "queues": [dict(row) for row in list(scheduler.get("queues", []))],
        },
        "workers": [dict(row) for row in workers],
    }
