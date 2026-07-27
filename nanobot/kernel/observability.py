"""Stable observability contract for the Mira kernel surface."""

from __future__ import annotations

from typing import Any

KERNEL_EVENT_LOG_LIMIT = 24


def build_diagnostics_snapshot(
    *,
    active_adapter: str | None,
    module_count: int,
    bridge_count: int,
    dispatch_queue_depth: int = 0,
    dispatch_queue_state: str = "ready",
    dispatch_handoff_lane: str | None = None,
    fault_level: str,
    execution_gate: str,
    maintenance_mode: bool,
    supervisor: str = "userspace-kernel-loop",
) -> dict[str, Any]:
    return {
        "supervisor": supervisor,
        "snapshot": {
            "active_adapter": active_adapter,
            "module_count": module_count,
            "bridge_count": bridge_count,
            "dispatch_queue_depth": dispatch_queue_depth,
            "dispatch_queue_state": dispatch_queue_state,
            "dispatch_handoff_lane": dispatch_handoff_lane,
            "fault_level": fault_level,
            "execution_gate": execution_gate,
            "maintenance_mode": maintenance_mode,
        },
    }


def append_kernel_event(
    event_log: list[dict[str, Any]],
    *,
    action: str,
    state: str,
    message: str,
) -> list[dict[str, Any]]:
    row = {
        "id": f"{len(event_log) + 1}",
        "action": action,
        "state": state,
        "message": message,
    }
    return [row, *event_log][:KERNEL_EVENT_LOG_LIMIT]
